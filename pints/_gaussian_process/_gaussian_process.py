# This file is part of PINTS.
#  Copyright (c) 2017-2019, University of Oxford.
#  For licensing information, see the LICENSE file distributed with the PINTS
#  software package.
#
from __future__ import absolute_import, division
from __future__ import print_function, unicode_literals
import numpy as np
import pints

from gaussian_process import GaussianProcess2


class GaussianProcessLogLikelihood(pints.LogPDF):
    """
    """

    def __init__(self, gaussian_process):
        super(GaussianProcessLogLikelihood, self).__init__()
        self._gaussian_process = gaussian_process

    def __call__(self, x):
        self._gaussian_process.set_lengthscale(x[:-1])
        self._gaussian_process.set_noise(x[-1])
        likelihood = self._gaussian_process.likelihood()
        return likelihood

    def evaluateS1(self, x):
        """
        returns the partial derivatives of the function with respect to the parameters.

        """
        self._gaussian_process.set_lengthscale(x[:-1])
        self._gaussian_process.set_noise(x[-1])
        gradient = np.empty_like(x)
        likelihood = 0
        self._gaussian_process.likelihoodS1(likelihood, gradient)
        return likelihood, gradient

    def n_parameters(self):
        """ See :meth:`ErrorMeasure.n_parameters()`. """
        return self._gaussian_process.n_parameters()


class GaussianProcess(pints.LogPDF):
    """
    Represents the natural logarithm of a (not necessarily normalised)
    probability density function (PDF), obtained from fitting a gaussian process.

    Arguments:

    ``samples``
        A sequence of samples in parameter space. Is a numpy array with shape
        ``(n, d)`` where ``n`` is the requested number of samples, and ``d`` is
        the number of parameters

    ``pdf_values``
        The value of the PDF at the location of the samples


    *Extends:* :class:`LogPDF`
    """

    def __init__(self, samples, pdf_values):
        super(GaussianProcess, self).__init__()

        # currently only supports dimension 2
        if samples.shape[1] != 2:
            raise NotImplementedError(
                'GaussianProcess currently only supports 2d'
            )

        self._gaussian_process = GaussianProcess2()
        self._gaussian_process.set_data(samples, pdf_values)

        score = GaussianProcessLogLikelihood(self._gaussian_process)

        sample_range = np.ptp(samples, axis=0)
        value_range = np.ptp(pdf_values)
        hyper_min = np.zeros(self.n_parameters())
        hyper_max = 30000*np.concatenate((sample_range,[1]))
        boundaries = pints.RectangularBoundaries(hyper_min, hyper_max)

        x0 = 0.1*(hyper_min + hyper_max)
        print(x0)
        sigma0 = 0.9*(hyper_max - hyper_min)

        opt = pints.OptimisationController(
            score,
            x0,
            sigma0,
            boundaries,
            method=pints.PSO
        )
        #opt.optimiser().set_alpha(1.01*np.min(sigma0))

        found_parameters, found_value = opt.run()
        print('found parameters ',found_parameters)
        print(hyper_max)
        print(hyper_min)
        self._gaussian_process.set_lengthscale(found_parameters[:-1])
        self._gaussian_process.set_noise(found_parameters[-1])

    def __call__(self, x):
        raise NotImplementedError

    def evaluateS1(self, x):
        raise NotImplementedError

    def n_parameters(self):
        """
        Returns the dimension of the space this :class:`LogPDF` is defined
        over.
        """
        return self._gaussian_process.n_parameters()
