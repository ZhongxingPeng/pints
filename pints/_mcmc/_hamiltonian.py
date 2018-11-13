#
# Hamiltonian MCMC method
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


class HamiltonianMCMC(pints.SingleChainMCMC):
    """
    *Extends:* :class:`SingleChainMCMC`

    Implements Hamiltonian Monte Carlo as described in [1].

    Uses a physical analogy of a particle moving across a landscape under
    Hamiltonian dynamics to aid efficient exploration of parameter space.
    Introduces an auxilary variable -- the momentum (``p_i``) of a particle
    moving in dimension ``i`` of negative log posterior space -- which
    supplements the position (``q_i``) of the particle in parameter space. The
    particle's motion is dictated by solutions to Hamilton's equations,

        dq_i/dt =   partial_d H/partial_d p_i,
        dp_i/dt = - partial_d H/partial_d q_i.

    The Hamiltonian is given by,

        H(q,p) =       U(q)       +        KE(p)
               = -log(p(q|X)p(q)) + Sigma_i=1^d p_i^2/2m_i,

    where ``d`` is the dimensionality of model and ``m_i`` is the 'mass' given
    to each particle (often chosen to be 1 as default).

    To numerically integrate Hamilton's equations, it is essential to use a
    sympletic discretisation routine, of which the most typical approach is
    the leapfrog method,

        p_i(t + epsilon) = p_i(t) + epsilon dp_i(t)/dt
                         = p_i(t) - epsilon partial_d U(q)/d_q_i,
        q_i(t + epsilon) = q_i(t) + epsilon dq_i(t)/dt
                         = q_i(t) + epsilon p_i(t) / m_i.

    [1] MCMC using Hamiltonian dynamics
    Radford M. Neal, Chapter 5 of the Handbook of Markov Chain Monte
    Carlo by Steve Brooks, Andrew Gelman, Galin Jones, and Xiao-Li Meng.

    """
    def __init__(self, x0, sigma0=None):
        super(HamiltonianMCMC, self).__init__(x0, sigma0)

        # Set initial state
        self._running = False
        self._ready_for_tell = False

        # Current point in the Markov chain
        self._current = None            # Aka current_q in the chapter
        self._current_log_pdf = None    # Aka U(current_q)
        self._current_gradient = None
        self._current_momentum = None   # Aka current_p

        # Current point in the leapfrog iterations
        self._momentum = None       # Aka p in the chapter
        self._position = None       # Aka q in the chapter
        self._gradient = None       # Aka grad_U(q) in the chapter

        # Iterations, acceptance monitoring, and leapfrog iterations
        self._mcmc_iteration = 0
        self._mcmc_acceptance = 0
        self._frog_iteration = 0

        # Default number of leapfrog iterations
        self._n_frog_iterations = 20

        # Default integration step size for leapfrog algorithm
        self._step_size = 0.2

        # Default masses
        self._mass = np.ones(self._dimension)

        # Divergence checking

        # Create a vector of divergent iterations
        #self._divergent = np.asarray([], dtype='int')

        # Default threshold for Hamiltonian divergences
        # (currently set to match Stan)
        #self._hamiltonian_threshold = 10**3

    def ask(self):
        """ See :meth:`SingleChainMCMC.ask()`. """
        # Check ask/tell pattern
        if self._ready_for_tell:
            raise RuntimeError('Ask() called when expecting call to tell().')

        # Initialise on first call
        if not self._running:
            self._running = True

        # Notes:
        #  Ask is responsible for updating the position, which is the point
        #   returned to the user
        #  Tell is then responsible for updating the momentum, which uses the
        #   gradient at this new point
        #  The MCMC step happens in tell, and does not require any new
        #   information (it uses the log_pdf and gradient of the final point
        #   in the leapfrog run).

        # Very first iteration
        if self._current is None:

            # Ask for the pdf and gradient of x0
            self._ready_for_tell = True
            return np.array(self._x0, copy=True)

        # First iteration of a run of leapfrog iterations
        if self._frog_iteration == 0:

            # Sample random momentum for current point
            self._current_momentum = np.random.multivariate_normal(
                np.zeros(self._dimension), self._sigma0)

            # First leapfrog position is the current sample in the chain
            self._position = np.array(self._current, copy=True)
            self._gradient = np.array(self._current_gradient, copy=True)
            self._momentum = np.array(self._current_momentum, copy=True)

            # Perform a half-step before starting iteration 0 below
            self._momentum -= self._step_size * self._gradient * 0.5

        # Perform a leapfrog step for the position
        self._position += self._step_size * self._gradient

        # Ask for the pdf and gradient of the current leapfrog position
        # Using this, the leapfrog step for the momentum is performed in tell()
        self._ready_for_tell = True
        return np.array(self._position, copy=True)

    def leapfrog_steps(self):
        """
        Returns the number of leapfrog steps to carry out for each iteration.
        """
        return self._n_frog_iterations

    def leapfrog_step_size(self):
        """
        Returns the step size for the leapfrog algorithm.
        """
        return self._step_size

    def _log_init(self, logger):
        """ See :meth:`Loggable._log_init()`. """
        logger.add_int('iMCMC')
        logger.add_int('iFrog')
        logger.add_float('Accept.')

    def _log_write(self, logger):
        """ See :meth:`Loggable._log_write()`. """
        logger.log(self._mcmc_iteration)
        logger.log(self._frog_iteration)
        logger.log(self._mcmc_acceptance)

    def name(self):
        """ See :meth:`pints.MCMCSampler.name()`. """
        return 'Hamiltonian MCMC'

    def needs_sensitivities(self):
        """ See :meth:`pints.MCMCSampler.needs_sensitivities()`. """
        return True

    def set_leapfrog_steps(self, steps):
        """
        Sets the number of leapfrog steps to carry out for each iteration.
        """
        steps = int(steps)
        if steps < 1:
            raise ValueError('Number of steps must exceed 0.')
        self._n_frog_iterations = steps

    def set_leapfrog_step_size(self, step_size):
        """
        Sets the step size for the leapfrog algorithm.
        """
        step_size = float(step_size)
        if step_size <= 0:
            raise ValueError(
                'Step size for leapfrog algorithm must be greater than zero.')
        self._step_size = step_size

    def tell(self, reply):
        """ See :meth:`pints.SingleChainMCMC.tell()`. """
        if not self._ready_for_tell:
            raise RuntimeError('Tell called before proposal was set.')
        self._ready_for_tell = False

        # Unpack reply
        log_pdf, gradient = reply
        log_pdf = float(log_pdf)
        assert(gradient.shape == (self._dimension, ))

        # Very first call
        if self._current is None:

            # Check first point is somewhere sensible
            if not np.isfinite(log_pdf):
                raise ValueError(
                    'Initial point for MCMC must have finite logpdf.')

            # Set current sample, logpdf, and gradient
            self._current = self._x0
            self._current_log_pdf = log_pdf
            self._current_gradient = gradient

            # Increase iteration count
            self._mcmc_iteration += 1

            # Mark current as read-only, so it can be safely returned
            self._current.setflags(write=False)

            # Return first point in chain
            return self._current

        # Set gradient of current leapfrog position
        self._gradient = gradient

        # Update the leapfrog iteration count
        self._frog_iteration += 1

        # Not the last iteration? Then perform a leapfrog step and return
        if self._frog_iteration < self._n_frog_iterations:
            self._momentum -= self._step_size * self._gradient

            # Return None to indicate there is no new sample for the chain
            return None

        # Final leapfrog iteration: only do half a step
        self._momentum -= self._step_size * self._gradient * 0.5

        # Leapfrog iterations finished! Perform MCMC step

        # Negate momentum to make the proposal symmetric
        self._momentum = -self._momentum

        # Evaluate potential and kinetic energies at start and end of
        # leapfrog trajectory
        current_U = self._current_log_pdf
        current_K = np.sum(self._current_momentum**2 / (2 * self._mass))
        proposed_U = log_pdf
        proposed_K = np.sum(self._momentum**2 / (2 * self._mass))

        # Check for divergent iterations by testing whether the
        # Hamiltonian difference is above a threshold
        #div = fx + proposed_K - (self._current_log_pdf + current_K)
        #if div > self._hamiltonian_threshold:
        #   self._divergent = np.append(self._divergent, self._iterations)

        # Accept/reject
        accept = 0
        r = np.exp(current_U - proposed_U + current_K - proposed_K)
        if np.random.uniform(0, 1) < r:
            # Accept
            accept = 1
            self._current = self._position
            self._current_logpdf = log_pdf
            self._current_gradient = gradient

            # Mark current as read-only, so it can be safely returned
            self._current.setflags(write=False)

        # Reset leapfrog mechanism
        self._momentum = self._position = self._gradient = None
        self._frog_iteration = 0

        # Update MCMC iteration count
        self._mcmc_iteration += 1

        # Update acceptance rate (only used for output!)
        self._mcmc_acceptance = (
            (self._mcmc_iteration * self._mcmc_acceptance + accept) /
            (self._mcmc_iteration + 1))

        # Return current position as next sample in the chain
        return self._current

