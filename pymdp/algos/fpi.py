#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=no-member

""" Functions for performing variational inference on hidden states 

__author__: Conor Heins, Beren Millidge, Alexander Tschantz, Brennan Klein
"""

import numpy as np
from pymdp.maths import spm_dot, get_joint_likelihood, softmax, calc_free_energy, spm_log_single, spm_log_obj_array
from pymdp.utils import to_arr_of_arr, obj_array_uniform
from itertools import chain

def run_vanilla_fpi(A, obs, num_obs, num_states, prior=None, num_iter=10, dF=1.0, dF_tol=0.001):
    """
    Update marginal posterior beliefs over hidden states using mean-field variational inference, via
    fixed point iteration. 

    Parameters
    ----------
    A: ``numpy.ndarray`` of dtype object
        Sensory likelihood mapping or 'observation model', mapping from hidden states to observations. Each element ``A[m]`` of
        stores an ``np.ndarray`` multidimensional array for observation modality ``m``, whose entries ``A[m][i, j, k, ...]`` store 
        the probability of observation level ``i`` given hidden state levels ``j, k, ...``
    obs: numpy 1D array or numpy ndarray of dtype object
        The observation (generated by the environment). If single modality, this should be a 1D ``np.ndarray``
        (one-hot vector representation). If multi-modality, this should be ``np.ndarray`` of dtype object whose entries are 1D one-hot vectors.
    num_obs: list of ints
        List of dimensionalities of each observation modality
    num_states: list of ints
        List of dimensionalities of each observation modality
    prior: numpy ndarray of dtype object, default None
        Prior over hidden states. If absent, prior is set to be the log uniform distribution over hidden states (identical to the 
        initialisation of the posterior)
    num_iter: int, default 10
        Number of variational fixed-point iterations to run until convergence.
    dF: float, default 1.0
        Initial free energy gradient (dF/dt) before updating in the course of gradient descent.
    dF_tol: float, default 0.001
        Threshold value of the time derivative of the variational free energy (dF/dt), to be checked at 
        each iteration. If dF <= dF_tol, the iterations are halted pre-emptively and the final 
        marginal posterior belief(s) is(are) returned
  
    Returns
    ----------
    qs: numpy 1D array, numpy ndarray of dtype object, optional
        Marginal posterior beliefs over hidden states at current timepoint
    """

    # get model dimensions
    n_modalities = len(num_observations)
    n_factors = len(num_states)

    """
    =========== Step 1 ===========
        Loop over the observation modalities and use assumption of independence 
        among observation modalitiesto multiply each modality-specific likelihood 
        onto a single joint likelihood over hidden factors [size num_states]
    """

    likelihood = get_joint_likelihood(A, obs, num_states)

    likelihood = spm_log_single(likelihood)

    """
    =========== Step 2 ===========
        Create a flat posterior (and prior if necessary)
    """

    qs = np.empty(n_factors, dtype=object)
    for factor in range(n_factors):
        qs[factor] = np.ones(num_states[factor]) / num_states[factor]

    """
    If prior is not provided, initialise prior to be identical to posterior 
    (namely, a flat categorical distribution). Take the logarithm of it (required for 
    FPI algorithm below).
    """
    if prior is None:
        prior = obj_array_uniform(num_states)
        
    prior = spm_log_obj_array(prior) # log the prior


    """
    =========== Step 3 ===========
        Initialize initial free energy
    """
    prev_vfe = calc_free_energy(qs, prior, n_factors)

    """
    =========== Step 4 ===========
        If we have a single factor, we can just add prior and likelihood because there is a unique FE minimum that can reached instantaneously,
        otherwise we run fixed point iteration
    """

    if n_factors == 1:

        qL = spm_dot(likelihood, qs, [0])

        return to_arr_of_arr(softmax(qL + prior[0]))

    else:
        """
        =========== Step 5 ===========
        Run the FPI scheme
        """

        curr_iter = 0
        while curr_iter < num_iter and dF >= dF_tol:
            # Initialise variational free energy
            vfe = 0

            # arg_list = [likelihood, list(range(n_factors))]
            # arg_list = arg_list + list(chain(*([qs_i,[i]] for i, qs_i in enumerate(qs)))) + [list(range(n_factors))]
            # LL_tensor = np.einsum(*arg_list)

            qs_all = qs[0]
            for factor in range(n_factors-1):
                qs_all = qs_all[...,None]*qs[factor+1]
            LL_tensor = likelihood * qs_all

            for factor, qs_i in enumerate(qs):
                # qL = np.einsum(LL_tensor, list(range(n_factors)), 1.0/qs_i, [factor], [factor])
                qL = np.einsum(LL_tensor, list(range(n_factors)), [factor])/qs_i
                qs[factor] = softmax(qL + prior[factor])

            # List of orders in which marginal posteriors are sequentially multiplied into the joint likelihood:
            # First order loops over factors starting at index = 0, second order goes in reverse
            # factor_orders = [range(n_factors), range((n_factors - 1), -1, -1)]

            # iteratively marginalize out each posterior marginal from the joint log-likelihood
            # except for the one associated with a given factor
            # for factor_order in factor_orders:
            #     for factor in factor_order:
            #         qL = spm_dot(likelihood, qs, [factor])
            #         qs[factor] = softmax(qL + prior[factor])

            # calculate new free energy
            vfe = calc_free_energy(qs, prior, n_factors, likelihood)

            # stopping condition - time derivative of free energy
            dF = np.abs(prev_vfe - vfe)
            prev_vfe = vfe

            curr_iter += 1

        return qs


def _run_vanilla_fpi_faster(A, obs, n_observations, n_states, prior=None, num_iter=10, dF=1.0, dF_tol=0.001):
    """
    Update marginal posterior beliefs about hidden states
    using a new version of variational fixed point iteration (FPI). 
    @NOTE (Conor, 26.02.2020):
    This method uses a faster algorithm than the traditional 'spm_dot' approach. Instead of
    separately computing a conditional joint log likelihood of an outcome, under the
    posterior probabilities of a certain marginal, instead all marginals are multiplied into one 
    joint tensor that gives the joint likelihood of an observation under all hidden states, 
    that is then sequentially (and *parallelizably*) marginalized out to get each marginal posterior. 
    This method is less RAM-intensive, admits heavy parallelization, and runs (about 2x) faster.
    @NOTE (Conor, 28.02.2020):
    After further testing, discovered interesting differences between this version and the 
    original version. It appears that the
    original version (simple 'run_vanilla_fpi') shows mean-field biases or 'explaining away' 
    effects, whereas this version spreads probabilities more 'fairly' among possibilities.
    To summarize: it actually matters what order you do the summing across the joint likelihood tensor. 
    In this verison, all marginals are multiplied into the likelihood tensor before summing out, 
    whereas in the previous version, marginals are recursively multiplied and summed out.
    @NOTE (Conor, 24.04.2020): I would expect that the factor_order approach used above would help 
    ameliorate the effects of the mean-field bias. I would also expect that the use of a factor_order 
    below is unnnecessary, since the marginalisation w.r.t. each factor is done only after all marginals 
    are multiplied into the larger tensor.

    Parameters
    ----------
    - 'A' [numpy nd.array (matrix or tensor or array-of-arrays)]:
        Observation likelihood of the generative model, mapping from hidden states to observations. 
        Used to invert generative model to obtain marginal likelihood over hidden states, 
        given the observation
    - 'obs' [numpy 1D array or array of arrays (with 1D numpy array entries)]:
        The observation (generated by the environment). If single modality, this can be a 1D array 
        (one-hot vector representation). If multi-modality, this can be an array of arrays 
        (whose entries are 1D one-hot vectors).
    - 'n_observations' [int or list of ints]
    - 'n_states' [int or list of ints]
    - 'prior' [numpy 1D array, array of arrays (with 1D numpy array entries) or None]:
        Prior beliefs of the agent, to be integrated with the marginal likelihood to obtain posterior. 
        If absent, prior is set to be a uniform distribution over hidden states 
        (identical to the initialisation of the posterior)
    -'num_iter' [int]:
        Number of variational fixed-point iterations to run.
    -'dF' [float]:
        Starting free energy gradient (dF/dt) before updating in the course of gradient descent.
    -'dF_tol' [float]:
        Threshold value of the gradient of the variational free energy (dF/dt), 
        to be checked at each iteration. If dF <= dF_tol, the iterations are halted pre-emptively 
        and the final marginal posterior belief(s) is(are) returned
    Returns
    ----------
    -'qs' [numpy 1D array or array of arrays (with 1D numpy array entries):
        Marginal posterior beliefs over hidden states (single- or multi-factor) achieved 
        via variational fixed point iteration (mean-field)
    """

    # get model dimensions
    n_modalities = len(n_observations)
    n_factors = len(n_states)

    """
    =========== Step 1 ===========
        Loop over the observation modalities and use assumption of independence 
        among observation modalities to multiply each modality-specific likelihood 
        onto a single joint likelihood over hidden factors [size n_states]
    """

    # likelihood = np.ones(tuple(n_states))

    # if n_modalities is 1:
    #     likelihood *= spm_dot(A, obs, obs_mode=True)
    # else:
    #     for modality in range(n_modalities):
    #         likelihood *= spm_dot(A[modality], obs[modality], obs_mode=True)
    likelihood = get_joint_likelihood(A, obs, n_states)
    likelihood = np.log(likelihood + 1e-16)

    """
    =========== Step 2 ===========
        Create a flat posterior (and prior if necessary)
    """

    qs = np.empty(n_factors, dtype=object)
    for factor in range(n_factors):
        qs[factor] = np.ones(n_states[factor]) / n_states[factor]

    """
    If prior is not provided, initialise prior to be identical to posterior 
    (namely, a flat categorical distribution). Take the logarithm of it 
    (required for FPI algorithm below).
    """
    if prior is None:
        prior = np.empty(n_factors, dtype=object)
        for factor in range(n_factors):
            prior[factor] = np.log(np.ones(n_states[factor]) / n_states[factor] + 1e-16)

    """
    =========== Step 3 ===========
        Initialize initial free energy
    """
    prev_vfe = calc_free_energy(qs, prior, n_factors)

    """
    =========== Step 4 ===========
        If we have a single factor, we can just add prior and likelihood,
        otherwise we run FPI
    """

    if n_factors == 1:
        qL = spm_dot(likelihood, qs, [0])
        return softmax(qL + prior[0])

    else:
        """
        =========== Step 5 ===========
        Run the revised fixed-point iteration scheme
        """

        curr_iter = 0

        while curr_iter < num_iter and dF >= dF_tol:
            # Initialise variational free energy
            vfe = 0

            # List of orders in which marginal posteriors are sequentially 
            # multiplied into the joint likelihood: First order loops over 
            # factors starting at index = 0, second order goes in reverse
            factor_orders = [range(n_factors), range((n_factors - 1), -1, -1)]

            for factor_order in factor_orders:
                # reset the log likelihood
                L = likelihood.copy()

                # multiply each marginal onto a growing single joint distribution
                for factor in factor_order:
                    s = np.ones(np.ndim(L), dtype=int)
                    s[factor] = len(qs[factor])
                    L *= qs[factor].reshape(tuple(s))

                # now loop over factors again, and this time divide out the 
                # appropriate marginal before summing out.
                # !!! KEY DIFFERENCE BETWEEN THIS AND 'VANILLA' FPI, 
                # WHERE THE ORDER OF THE MARGINALIZATION MATTERS !!!
                for f in factor_order:
                    s = np.ones(np.ndim(L), dtype=int)
                    s[factor] = len(qs[factor])  # type: ignore

                    # divide out the factor we multiplied into X already
                    temp = L * (1.0 / qs[factor]).reshape(tuple(s))  # type: ignore
                    dims2sum = tuple(np.where(np.arange(n_factors) != f)[0])
                    qL = np.sum(temp, dims2sum)

                    temp = L * (1.0 / qs[factor]).reshape(tuple(s))  # type: ignore
                    qs[factor] = softmax(qL + prior[factor])  # type: ignore

            # calculate new free energy
            vfe = calc_free_energy(qs, prior, n_factors, likelihood)

            # stopping condition - time derivative of free energy
            dF = np.abs(prev_vfe - vfe)
            prev_vfe = vfe

            curr_iter += 1

        return qs
