#
# Differential evolution MCMC
#
# This file is part of PINTS.
#  Copyright (c) 2017-2018, University of Oxford.
#  For licensing information, see the LICENSE file distributed with the PINTS
#  software package.
#
from __future__ import absolute_import, division
from __future__ import print_function, unicode_literals
import pints
import numpy as np
import logging


class DifferentialEvolutionMCMC(pints.MultiChainMCMC):
    """
    Uses differential evolution MCMC as described in [1] to do posterior
    sampling from the posterior.

    In each step of the algorithm ``n`` chains are evolved using the evolution
    equation::

        x_proposed = x[i,r] + gamma * (X[i,r1] - x[i,r2]) + epsilon

    where ``r1`` and ``r2`` are random chain indices chosen (without
    replacement) from the ``n`` available chains, which must not equal ``i`` or
    each other, where ``i`` indicates the current time  step, and
    ``epsilon ~ N(0,b)`` where ``d`` is the dimensionality of the parameter
    vector.

    If ``x_proposed / x[i,r] > u ~ U(0,1)``, then
    ``x[i+1,r] = x_proposed``; otherwise, ``x[i+1,r] = x[i]``.

    *Extends:* :class:`MultiChainMCMC`

    [1] "A Markov Chain Monte Carlo version of the genetic algorithm
    Differential Evolution: easy Bayesian computing for real parameter spaces"
    Cajo J. F. Ter Braak (2006) Statistical Computing
    """

    def __init__(self, chains, x0, sigma0=None):
        super(DifferentialEvolutionMCMC, self).__init__(chains, x0, sigma0)

        # Need at least 3 chains
        if self._chains < 3:
            raise ValueError('Need at least 3 chains.')

        # Warn user against using too few chains
        if self._chains < 1.5 * self._dimension:
            log = logging.getLogger(__name__)
            log.warning('This method should be run with n_chains >= '+
                         '1.5 * n_parameters')

        # Set initial state
        self._running = False

        # Current points and proposed points
        self._current = None
        self._current_logpdf = None
        self._proposed = None

        #
        # Default settings
        #

        # Gamma
        self._gamma = 2.38 / np.sqrt(2 * self._dimension)
        
        # Gamma switch to 1 every (below) steps to help find
        # modes
        self._gamma_switch_rate = 10

        # Error scale width
        self._b = 0.001

        # Normal error vs uniform
        self._normal_error = True

        # Relative scaling
        self._relative_scaling = True

    def ask(self):
        """ See :meth:`pints.MultiChainMCMC.ask()`. """
        # Initialise on first call
        if not self._running:
            self._initialise()
        
        # set gamma to 1
        if self._iter_count % self._gamma_switch_rate == 0:
            self._gamma = 1
        self._iter_count += 1

        # Propose new points
        if self._proposed is None:
            self._proposed = np.zeros(self._current.shape)
            for j in range(self._chains):
                if self._normal_error:
                    error = np.random.normal(0, self._b_star, self._mu.shape)
                else:
                    error = np.random.uniform(-self._b_star, self._b_star, self._mu.shape)
                r1, r2 = r_draw(j, self._chains)
                self._proposed[j] = (
                    self._current[j]
                    + self._gamma * (self._current[r1] - self._current[r2])
                    + error
                )

            # reset gamma
            self._gamma = 2.38 / np.sqrt(2 * self._dimension)
            
            # Set as read only
            self._proposed.setflags(write=False)

        # Return proposed points
        return self._proposed
    
    def set_normal_error(self, normal_error):
        """
        If true sets the error process to be a normal
        error, N(0, b*); if false, it uses a uniform error
        U(-b*, b*); where b* = b if absolute scaling used
        and b* = mu * b if relative used instead
        """
        normal_error = bool(normal_error)
        self._normal_error = normal_error

    def _initialise(self):
        """
        Initialises the routine before the first iteration.
        """
        if self._running:
            raise RuntimeError('Already initialised.')

        # Propose x0 as first points
        self._current = None
        self._current_log_pdfs = None
        self._proposed = self._x0

        # Set mu
        # TODO: Should this be a user setting?
        self._mu = np.mean(self._x0, axis=0)

        # Use relative or absolute scaling of error process
        if self._relative_scaling:
            self._b_star = self._mu * self._b
        else:
            self._b_star = np.repeat(self._b, self._dimension)

        # Gamma set to 1 counter
        self._iter_count = 0

        # Update sampler state
        self._running = True

    def set_gamma_switch_rate(self, gamma_switch_rate):
        """
        Sets the number of steps between iterations where
        gamma is set to 1 (then reset immediately afterwards)
        """
        if gamma_switch_rate < 1:
            raise ValueError('The interval number of steps between ' +
                              ' gamma=1 iterations must exceed 1.')
        if not isinstance(gamma_switch_rate, int):
            raise ValueError('The interval number of steps between ' +
                              ' gamma=1 iterations must be an integer.')
        self._gamma_switch_rate = gamma_switch_rate
    
    def set_relative_scaling(self, relative_scaling):
        """
        Sets whether to use an error process whose standard deviation
        scales relatively (scale = self._mu * self_b) or absolutely
        (scale = self._b in all dimensions)
        """
        relative_scaling = bool(relative_scaling)
        self._relative_scaling = relative_scaling
        self._initialise()

    def name(self):
        """ See :meth:`pints.MCMCSampler.name()`. """
        return 'Differential Evolution MCMC'

    def tell(self, proposed_log_pdfs):
        """ See :meth:`pints.MultiChainMCMC.tell()`. """
        # Check if we had a proposal
        if self._proposed is None:
            raise RuntimeError('Tell called before proposal was set.')

        # Ensure proposed_log_pdfs are numpy array
        proposed_log_pdfs = np.array(proposed_log_pdfs)

        # First points?
        if self._current is None:
            if not np.all(np.isfinite(proposed_log_pdfs)):
                raise ValueError(
                    'Initial points for MCMC must have finite logpdf.')

            # Accept
            self._current = self._proposed
            self._current_log_pdfs = proposed_log_pdfs

            # Clear proposal
            self._proposed = None

            # Return first samples for chains
            return self._current

        # Perform iteration
        next = np.array(self._current, copy=True)
        next_log_pdfs = np.array(self._current_log_pdfs, copy=True)

        # Sample uniform numbers
        u = np.log(np.random.uniform(size=self._chains))

        # Get chains to be updated
        i = u < (proposed_log_pdfs - self._current_log_pdfs)

        # Update
        next[i] = self._proposed[i]
        next_log_pdfs[i] = proposed_log_pdfs[i]
        self._current = next
        self._current_log_pdfs = next_log_pdfs

        # Clear proposal
        self._proposed = None

        # Return samples to add to chains
        self._current.setflags(write=False)
        return self._current

    def set_scale_coefficient(self, b):
        """
        Sets the scale coefficient ``b`` of error process used in updating
        the position of each chain.
        """
        b = float(b)
        if b < 0:
            raise ValueError('Scale coefficient must be non-negative.')
        self._b = b

    def set_gamma(self, gamma):
        """
        Sets the coefficient ``gamma`` used in updating the position of each
        chain.
        """
        gamma = float(gamma)
        if gamma < 0:
            raise ValueError('Gamma must be non-negative.')
        self._gamma = gamma

    def n_hyper_parameters(self):
        """ See :meth:`TunableMethod.n_hyper_parameters()`. """
        return 4

    def set_hyper_parameters(self, x):
        """
        The hyper-parameter vector is ``[gamma, normal_scale_coefficient]``.

        See :meth:`TunableMethod.set_hyper_parameters()`.
        """
        self.set_gamma(x[0])
        self.set_scale_coefficient(x[1])
        self.set_gamma_switch_rate(x[2])
        self.set_normal_error(x[3])


def r_draw(i, num_chains):
    # TODO: Needs a docstring!
    r1, r2 = np.random.choice(num_chains, 2, replace=False)
    while(r1 == i or r2 == i or r1 == r2):
        r1, r2 = np.random.choice(num_chains, 2, replace=False)
    return r1, r2
