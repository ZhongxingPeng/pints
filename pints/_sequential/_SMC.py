#
# Sequential Monte Carlo following Del Moral et al. 2006
#
# This file is part of PINTS.
#  Copyright (c) 2017-2019, University of Oxford.
#  For licensing information, see the LICENSE file distributed with the PINTS
#  software package.
#
from __future__ import absolute_import, division
from __future__ import print_function, unicode_literals

import pints
import numpy as np
from scipy.special import logsumexp


class SMC(pints.SMCSampler):
    """
    Samples from a density using sequential Monte Carlo sampling [1], although
    allows multiple MCMC steps per temperature, if desired.

    Algorithm 3.1.1 using equation (31) for ``w_tilde``.

    [1] "Sequential Monte Carlo Samplers", Del Moral et al. 2006,
    Journal of the Royal Statistical Society. Series B.
    """
    def __init__(self, log_prior, sigma0=None):
        super(SMC, self).__init__(log_prior, sigma0)

        # ESS threshold (default from Del Moral et al.)
        self._ess_threshold = None

        # Keep track of last/current ess
        self._last_ess = None

        # Determines whether to resample particles at end of
        # steps 2 and 3 from Del Moral et al. (2006)
        self._resample_end_2_3 = True

        # Current samples, their log pdfs, and weights
        self._samples = None
        self._log_pdfs = None
        self._weights = None

        # Proposed samples
        self._proposals = None

        # Internal mcmc chains
        self._method = pints.AdaptiveCovarianceMCMC
        self._chains = None

        # Iterations: i_temp (outer loop) and i_mcmc (inner loop)
        self._i_temp = 1
        self._i_mcmc = 0
        self._finished = False

    def ask(self):
        """ See :meth:`SMCSampler.ask()`. """

        # Check ask/tell pattern
        if self._proposals is not None:
            raise RuntimeError('Ask called when expecting tell.')

        # Too many steps?
        if self._i_temp >= len(self._schedule):
            raise RuntimeError('Too many iterations in SMC!')

        # We're up and running now
        self._running = True

        # Initialise
        if self._samples is None:

            # Set default ESS if not user specified
            if self._ess_threshold is None:
                self._ess_threshold = self._n_particles / 2
            elif self._ess_threshold > self._n_particles:
                raise RuntimeError(
                    'ESS threshold must be lower than or equal to number of'
                    ' particles. Set to ' + str(self._ess_threshold) +
                    ', expecting <= ' + str(self._n_particles))

            # Sample from the prior
            self._proposals = self._log_prior.sample(self._n_particles)
            self._proposals.setflags(write=False)

            # Create and configure chains
            self._chains = [
                self._method(p, self._sigma0) for p in self._proposals]
            if self._chains[0].needs_initial_phase():
                for chain in self._chains:
                    chain.set_initial_phase(False)

            # Get LogPDF of initial samples via ask/tell
            return self._proposals

        # Get beta, using next temperature
        beta = self._schedule[self._i_temp]

        # If ESS < threshold then resample to avoid degeneracies
        if self._last_ess < self._ess_threshold:
            self._resample()

        # Update chains with log pdfs tempered with current beta
        for j, sample in enumerate(self._samples):
            self._chains[j].replace(sample, self._temper(
                self._log_pdfs[j], self._log_prior(sample), beta))

        # Get proposals from MCMC and return
        self._proposals = np.array([chain.ask() for chain in self._chains])
        self._proposals.setflags(write=False)

        return self._proposals

    def ess(self):
        """
        Returns ess from last run of SMC.
        """
        return self._last_ess

    def name(self):
        """ See :meth:`SMCSampler.name()`. """
        return 'Sequential Monte Carlo'

    def tell(self, log_pdfs):
        """ See :meth:`SMCSampler.ask()`. """

        # Check ask/tell pattern
        if self._proposals is None:
            raise RuntimeError('Tell called when expecting ask.')

        # First step?
        if self._samples is None:

            # Store current samples and logpdfs
            # (Copy proposals to remove read-only property: but the reference
            #  is still outside so users could now modify them...)
            self._samples = np.copy(self._proposals)
            self._log_pdfs = np.array(log_pdfs, copy=True)

            # Update all the chains with their initial log pdf
            for i, f in enumerate(self._log_pdfs):
                self._chains[i].ask()
                self._chains[i].tell(f)

            # Set weights based on next temperature
            beta = self._schedule[1]
            priors = np.array([self._log_prior(x) for x in self._samples])
            self._weights = beta * (self._log_pdfs - priors)
            self._weights = np.exp(self._weights - logsumexp(self._weights))

            # Update ess
            self._last_ess = 1 / np.sum(self._weights**2)

            # Store copy of proposals to return
            to_return = self._proposals

            # Clear proposals
            self._proposals = None

            # Return current samples
            return to_return

        # Normal iteration
        beta = self._schedule[self._i_temp]

        # Update MCMC chains with tempered log pdf values
        for j, proposed in enumerate(self._proposals):
            updated = self._chains[j].tell(
                self._temper(log_pdfs[j], self._log_prior(proposed), beta))

            if np.all(updated == proposed):  # TODO: use accepted()
                self._samples[j] = proposed
                self._log_pdfs[j] = log_pdfs[j]

        # Clear proposals
        self._proposals = None

        # Run more mcmc steps before continuing?
        self._i_mcmc += 1
        if self._i_mcmc < self._n_mcmc_steps:
            return None

        # Reset mcmc steps
        self._i_mcmc = 0

        # Update weights
        for j, w in enumerate(self._weights):
            self._weights[j] = np.log(w) + self._w_tilde(
                self._log_pdfs[j],
                self._log_prior(self._samples[j]),
                self._schedule[self._i_temp - 1],
                self._schedule[self._i_temp])
        self._weights = np.exp(self._weights - logsumexp(self._weights))

        # Store ess, before resampling
        self._last_ess = 1 / np.sum(self._weights**2)

        # Conditional resampling step
        if self._resample_end_2_3:
            self._resample()

        # Update temperature step
        self._i_temp += 1

        # Return copy of current samples
        return np.copy(self._samples)

    def set_ess_threshold(self, ess_threshold):
        """
        Sets the threshold effective sample size (ESS).
        Use ``None`` to reset it to a default value.
        """
        if ess_threshold is None:
            self._ess_threshold = None
            return

        ess_threshold = int(ess_threshold)
        if ess_threshold <= 0:
            raise ValueError('ESS must be greater than zero.')
        if ess_threshold > self._n_particles:
            raise ValueError(
                'ESS threshold must be lower than or equal to number of'
                ' particles.')
        self._ess_threshold = ess_threshold

    def set_resample_end_2_3(self, resample_end_2_3):
        """
        Determines whether a resampling step is performed at end of steps 2 and
        3 in Del Moral et al. Algorithm 3.1.1.
        """
        self._resample_end_2_3 = bool(resample_end_2_3)

    def weights(self):
        """
        Returns weights from last run of SMC.
        """
        if self._weights is None:
            return None
        return np.copy(self._weights)

    def _log_init(self, logger):
        """ See :meth:`Loggable._log_init()`. """
        logger.add_float('Temperature')
        logger.add_float('ESS')

    def _log_write(self, logger):
        """ See :meth:`Loggable._log_write()`. """
        # Called after tell() has updated i_temp!
        logger.log(1 - self._schedule[self._i_temp - 1])
        logger.log(self.ess())

    def _resample(self):
        """
        Resamples (and updates the weights and log_pdfs) according to the
        weights vector from the multinomial distribution.
        """
        selected = np.random.multinomial(self._n_particles, self._weights)
        new_samples = np.zeros((self._n_particles, self._n_parameters))
        new_log_pdfs = np.zeros(self._n_particles)
        lo = hi = 0
        for i, n_selected in enumerate(selected):
            if n_selected:
                hi += n_selected
                new_samples[lo:hi, :] = self._samples[i]
                new_log_pdfs[lo:hi] = self._log_pdfs[i]
                lo = hi
        self._samples = new_samples
        self._log_pdfs = new_log_pdfs

        #TODO: Can this go?
        if np.count_nonzero(new_samples == 0) > 0:  # pragma: no cover
            raise RuntimeError('Zero elements appearing in samples matrix.')

        # Update weights
        self._weights = np.repeat(1 / self._n_particles, self._n_particles)

    def _temper(self, fx, f_prior, beta):
        """
        Returns beta * fx + (1-beta) * f_prior
        """
        return beta * fx + (1 - beta) * f_prior

    def _w_tilde(self, fx_old, f_prior_old, beta_old, beta_new):
        """
        Calculates the log unnormalised incremental weight as per eq. (31) in
        Del Moral.
        """
        return (
            self._temper(fx_old, f_prior_old, beta_new)
            - self._temper(fx_old, f_prior_old, beta_old)
        )

