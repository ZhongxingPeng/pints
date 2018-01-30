#
# Quick diagnostic plots.
#
# This file is part of PINTS.
#  Copyright (c) 2017, University of Oxford.
#  For licensing information, see the LICENSE file distributed with the PINTS
#  software package.
#
from __future__ import absolute_import, division
from __future__ import print_function, unicode_literals
import warnings
import numpy as np
import scipy.stats as stats


def trace(chain, *args):
    """
    Takes one or more markov chains as input and creates and returns a plot
    showing histograms and traces for each chain.

    Arguments:

    `chain`
        A markov chain of shape `(samples, dimension)`, where `samples` is the
        number of samples in the chain and `dimension` is the number of
        parameters.
    `*args`
        Additional chains can be added after the initial argument.

    Returns a `matplotlib` figure object and axes handle.
    """
    import matplotlib.pyplot as plt

    bins = 40
    alpha = 0.5
    n_sample, n_param = chain.shape

    # Set up figure, plot first chain
    fig, axes = plt.subplots(n_param, 2, figsize=(12, 2 * n_param))
    for i in range(n_param):
        # Add histogram subplot
        axes[i, 0].set_xlabel('Parameter ' + str(i + 1))
        axes[i, 0].set_ylabel('Frequency')
        axes[i, 0].hist(chain[:, i], bins=bins, alpha=0.5, label='Chain 1')

        # Add trace subplot
        axes[i, 1].set_xlabel('Iteration')
        axes[i, 1].set_ylabel('Parameter ' + str(i + 1))
        axes[i, 1].plot(chain[:, i], alpha=alpha)

    # Plot additional chains
    if args:
        for i_chain, chain in enumerate(args):
            if chain.shape[1] != n_param:
                raise ValueError(
                    'All chains must have the same number of parameters.')
            for i in range(n_param):
                axes[i, 0].hist(chain[:, i], bins=bins, alpha=0.5,
                                label='Chain ' + str(2 + i_chain))
                axes[i, 1].plot(chain[:, i], alpha=alpha)
        axes[0, 0].legend()

    plt.tight_layout()
    return fig, axes


def autocorrelation(chain, max_lags=100):
    """
    Creates and returns an autocorrelation plot for a given markov `chain`.

    Arguments:

    `chain`
        A markov chain of shape `(samples, dimension)`, where `samples` is the
        number of samples in the chain and `dimension` is the number of
        parameters.
    `max_lags`
        (Optional) The maximum autocorrelation lag to plot.

    Returns a `matplotlib` figure object and axes handle.
    """
    import matplotlib.pyplot as plt

    n_sample, n_param = chain.shape

    fig, axes = plt.subplots(n_param, 1, sharex=True, figsize=(6, 2 * n_param))
    for i in range(n_param):
        axes[i].acorr(chain[:, i] - np.mean(chain[:, i]), maxlags=max_lags)
        axes[i].set_xlim(-0.5, max_lags + 0.5)
        axes[i].legend(['Parameter ' + str(1 + i)], loc='upper right')

    # Add x-label to final plot only
    axes[i].set_xlabel('Lag')

    # Add vertical y-label to middle plot
    # fig.text(0.04, 0.5, 'Autocorrelation', va='center', rotation='vertical')
    axes[int(i / 2)].set_ylabel('Autocorrelation')

    plt.tight_layout()
    return fig, axes


def series(chain, problem, thinning=None):
    """
    Creates and returns a plot of predicted time series for a given markov
    `chain` and a single-series `problem`.

    Because this method runs simulations, it can take a considerable time to
    run.

    Arguments:

    `chain`
        A markov chain of shape `(samples, dimension)`, where `samples` is the
        number of samples in the chain and `dimension` is the number of
        parameters.
    `problem`
        A :class:`pints.SingleSeriesProblem` of a dimension equal to or greater
        than the `dimension` of the markov chain. Any extra parameters present
        in the chain but not accepted by the SingleSeriesProblem (for example
        parameters added by a noise model) will be ignored.
    `thinning`
        (Optional) An integer greater than zero. If specified, only every
        n-th sample (with `n = thinning`) in the chain will be used. If left at
        the default value `None`, a value will be chosen so that 200 to 400
        predictions are shown.

    Returns a `matplotlib` figure object and axes handle.
    """
    import matplotlib.pyplot as plt

    n_sample, n_param = chain.shape

    # Get problem dimension
    dimension = problem.dimension()

    # Get thinning rate
    if thinning is None:
        thinning = max(1, int(n_sample / 200))
    else:
        thinning = int(thinning)
        if thinning < 1:
            raise ValueError(
                'Thinning rate must be `None` or an integer greater than'
                ' zero.')

    # Get times
    times = problem.times()

    # Evaluate the model for all parameter sets in the chain
    i = 0
    predicted_values = []
    for params in chain[::thinning, :dimension]:
        predicted_values.append(problem.evaluate(params))
        i += 1
    predicted_values = np.array(predicted_values)
    mean_values = np.mean(predicted_values, axis=0)

    # Guess appropriate alpha (0.05 worked for 1000 plots)
    alpha = max(0.05 * (1000 / (n_sample / thinning)), 0.5)

    # Plot prediction
    fig, axes = plt.subplots(1, 1, figsize=(6, 4))
    plt.xlabel('Time')
    plt.ylabel('Value')
    plt.plot(
        times, problem.values(), 'x', color='#7f7f7f', ms=6.5, alpha=0.5,
        label='Original data')
    plt.plot(
        times, predicted_values[0], color='#1f77b4', label='Inferred series')
    for v in predicted_values[1:]:
        plt.plot(times, v, color='#1f77b4', alpha=alpha)
    plt.plot(times, mean_values, 'k:', lw=2, label='Mean of inferred series')
    plt.legend()

    return fig, axes


def pairwise(chain, kde=False, opacity=None, true_values=None):
    """
    Takes a markov chain and creates a set of pairwise scatterplots for all
    parameters (p1 versus p2, p1 versus p3, p2 versus p3, etc.).

    The returned plot is in a 'matrix' form, with histograms of each individual
    parameter on the diagonal, and scatter plots of parameters `i` and `j` on
    each entry `(i, j)` below the diagonal.

    Arguments:

    `chain`
        A markov chain of shape `(samples, dimension)`, where `samples` is the
        number of samples in the chain and `dimension` is the number of
        parameters.
    `kde`
        Set to `True` to use kernel-density estimation for the histograms and
        scatter plots.
    `opacity`
        When `kde=False`, this value can be used to manually set the opacity of
        the points in the scatter plots.
    `true_values`
        If true values of parameters are known, they can be passed in for
        plotting.

    Returns a `matplotlib` figure object and axes handle.
    """
    import matplotlib.pyplot as plt

    # Check chain size
    n_sample, n_param = chain.shape

    # Check true values
    if true_values is not None:
        if len(true_values) != n_param:
            raise ValueError(
                'Length of `true_values` must be same as number of parameters')

    # Create figure
    fig_size = (3 * n_param, 3 * n_param)
    fig, axes = plt.subplots(n_param, n_param, figsize=fig_size)

    bins = 25
    for i in range(n_param):
        for j in range(n_param):
            if i == j:

                # Diagonal: Plot a histogram
                xmin, xmax = np.min(chain[:, i]), np.max(chain[:, i])
                xbins = np.linspace(xmin, xmax, bins)
                axes[i, j].set_xlim(xmin, xmax)
                axes[i, j].hist(chain[:, i], bins=xbins, normed=True)

                # Add kde plot
                if kde:
                    x = np.linspace(xmin, xmax, 100)
                    axes[i, j].plot(x, stats.gaussian_kde(chain[:, i])(x))

                # Add true values
                if true_values is not None:
                    ymin_tv, ymax_tv = axes[i, j].get_ylim()
                    axes[i, j].plot(
                        [true_values[i], true_values[i]],
                        [0.0, ymax_tv],
                        '--', c='k')

            elif i < j:
                # Top-right: no plot
                axes[i, j].axis('off')

            else:
                # Lower-left: Plot the samples as density map
                xmin, xmax = np.min(chain[:, j]), np.max(chain[:, j])
                ymin, ymax = np.min(chain[:, i]), np.max(chain[:, i])
                axes[i, j].set_xlim(xmin, xmax)
                axes[i, j].set_ylim(ymin, ymax)

                if not kde:
                    # Create scatter plot

                    # Determine point opacity
                    num_points = len(chain[:, i])
                    if opacity is None:
                        if num_points < 10:
                            opacity = 1.0
                        else:
                            opacity = 1.0 / np.log10(num_points)

                    # Scatter points
                    axes[i, j].scatter(
                        chain[:, j], chain[:, i], alpha=opacity, s=0.1)

                    # Add true values if given
                    if true_values is not None:
                        axes[i, j].plot(
                            [true_values[j], true_values[j]], [ymin, ymax],
                            '--', c='k')
                        axes[i, j].plot(
                            [xmin, xmax], [true_values[i], true_values[i]],
                            '--', c='k')
                else:
                    # Create a KDE-based plot

                    # Plot values
                    values = np.vstack([chain[:, j], chain[:, i]])
                    axes[i, j].imshow(
                        np.rot90(values), cmap=plt.cm.Blues,
                        extent=[xmin, xmax, ymin, ymax])

                    # Create grid
                    xx, yy = np.mgrid[xmin:xmax:100j, ymin:ymax:100j]
                    positions = np.vstack([xx.ravel(), yy.ravel()])

                    # Get kernel density estimate and plot contours
                    kernel = stats.gaussian_kde(values)
                    f = np.reshape(kernel(positions).T, xx.shape)
                    axes[i, j].contourf(xx, yy, f, cmap='Blues')
                    axes[i, j].contour(xx, yy, f, colors='k')

                    # Add true values if given
                    if true_values is not None:
                        axes[i, j].plot(
                            [true_values[j], true_values[j]],
                            [ymin, ymax],
                            '--', c='k')
                        axes[i, j].plot(
                            [xmin, xmax],
                            [true_values[i], true_values[i]],
                            '--', c='k')

                    # Force equal aspect ratio
                    # See: https://stackoverflow.com/questions/7965743
                    im = axes[i, j].get_images()
                    ex = im[0].get_extent()
                    # Matplotlib raises a warning here (on 2.7 at least)
                    # We can't do anything about it, so no other option than
                    # to suppress it at this stage...
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore', UnicodeWarning)
                        axes[i, j].set_aspect(
                            abs((ex[1] - ex[0]) / (ex[3] - ex[2])))

            # Set tick labels
            if i < n_param - 1:
                # Only show x tick labels for the last row
                axes[i, j].set_xticklabels([])
            else:
                # Rotate the x tick labels to fit in the plot
                for tl in axes[i, j].get_xticklabels():
                    tl.set_rotation(45)

            if j > 0:
                # Only show y tick labels for the first column
                axes[i, j].set_yticklabels([])

        # Set axis labels
        axes[-1, i].set_xlabel('Parameter %d' % (i + 1))
        if i == 0:
            # The first one is not a parameter
            axes[i, 0].set_ylabel('Frequency')
        else:
            axes[i, 0].set_ylabel('Parameter %d' % (i + 1))

    return fig, axes
