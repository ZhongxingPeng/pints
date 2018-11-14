#
# Logistic model.
#
# This file is part of PINTS.
#  Copyright (c) 2017-2018, University of Oxford.
#  For licensing information, see the LICENSE file distributed with the PINTS
#  software package.
#
from __future__ import absolute_import, division
from __future__ import print_function, unicode_literals
import numpy as np
import pints


class LogisticModel(pints.ForwardModelS1, pints.ToyModel):

    """
    Logistic model of population growth [1].

    .. math::
        f(t) &= \\frac{k}{1+(k/p_0 - 1)*\exp(-r t)} \\\\
        \\frac{\\partial f(t)}{\\partial r} &=
                                \\frac{k t (k / p_0 - 1) \exp(-r t)}
                                      {((k/p_0-1) \exp(-r t) + 1)^2} \\\\
        \\frac{\\partial f(t)}{ \\partial k} &= \\frac{k \exp(-r t)}
                                          {p_0 ((k/p_0-1)\exp(-r t) + 1)^2}
                                         + \\frac{1}{(k/p_0 - 1)\exp(-r t) + 1}

    Has two parameters: A growth rate :math:`r` and a carrying capacity
    :math:`k`. The initial population size :math:`f(0) = p_0` can be set using
    the (optional) named constructor arg ``initial_population_size``

    [1] https://en.wikipedia.org/wiki/Population_growth
    """

    def __init__(self, initial_population_size=2):
        super(LogisticModel, self).__init__()
        self._p0 = float(initial_population_size)
        if self._p0 < 0:
            raise ValueError('Population size cannot be negative.')

    def n_parameters(self):
        """ See :meth:`pints.ForwardModel.n_parameters()`. """
        return 2

    def simulate(self, parameters, times):
        """ See :meth:`pints.ForwardModel.simulate()`. """
        return self._simulate(parameters, times, False)

    def simulateS1(self, parameters, times):
        """ See :meth:`pints.ForwardModelS1.simulateS1()`. """
        return self._simulate(parameters, times, True)

    def _simulate(self, parameters, times, sensitivities):
        r, k = [float(x) for x in parameters]
        times = np.asarray(times)
        if np.any(times < 0):
            raise ValueError('Negative times are not allowed.')
        if self._p0 == 0 or k < 0:
            if sensitivities:
                return np.zeros(times.shape), np.zeros((len(times), len(parameters)))
            else:
                return np.zeros(times.shape)

        exp = np.exp(-r * times)
        c = (k / self._p0 - 1)

        values = k / (1 + c * exp)

        if sensitivities:
            dvalues_dp = np.empty((len(times), len(parameters)))
            dvalues_dp[:, 0] = k * times * c * exp / (c * exp + 1)**2
            dvalues_dp[:, 1] = -k * exp / \
                (self._p0 * (c * exp + 1)**2) + 1 / (c * exp + 1)
            return values, dvalues_dp
        else:
            return values

    def suggested_parameters(self):
        """ See :meth:`pints.ToyModel.suggested_parameters()`. """

        return np.array([0.1, 50])

    def suggested_times(self):
        """ See :meth:`pints.ToyModel.suggested_times()`. """

        return np.linspace(0, 100, 100)
