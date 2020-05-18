#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=no-member

""" Functions for performing variational inference on hidden states 

__author__: Conor Heins, Alexander Tschantz, Brennan Klein
"""

import itertools
import numpy as np
import torch
from scipy import special
from inferactively.core import utils, softmax, spm_dot, spm_wnorm, spm_cross
from inferactively.core.algos import run_fpi

FPI = "FPI"
VMP = "VMP"
MMP = "MMP"
BP = "BP"
EP = "EP"
CV = "CV"


def update_posterior_states(A, obs, prior=None, return_numpy=True, method=FPI, **kwargs):
    """ 
    Update marginal posterior over hidden states using variational inference
        Can optionally set message passing algorithm used for inference
    
    Parameters
    ----------
    - 'A' [numpy nd.array (matrix or tensor or array-of-arrays) or Categorical]:
        Observation likelihood of the generative model, mapping from hidden states to observations
        Used to invert generative model to obtain marginal likelihood over hidden states, given the observation
    - 'obs' [numpy 1D array, array of arrays (with 1D numpy array entries), int or tuple]:
        The observation (generated by the environment). If single modality, this can be a 1D array 
        (one-hot vector representation) or an int (observation index)
        If multi-modality, this can be an array of arrays (whose entries are 1D one-hot vectors) or a tuple (of observation indices)
    - 'prior' [numpy 1D array, array of arrays (with 1D numpy array entries), Categorical, or None]:
        Prior beliefs about hidden states, to be integrated with the marginal likelihood to obtain a posterior distribution. 
        If None, prior is set to be equal to a flat categorical distribution (at the level of the individual inference functions).
        (optional)
    - 'return_numpy' [bool]:
        True/False flag to determine whether the posterior is returned as a numpy array or a Categorical
    - 'method' [str]:
        Algorithm used to perform the variational inference. 
        Options: 'FPI' - Fixed point iteration 
                    - http://www.cs.cmu.edu/~guestrin/Class/10708/recitations/r9/VI-view.pdf, slides 13- 18
                    - http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.137.221&rep=rep1&type=pdf, slides 24 - 38
                 'VMP  - Variational message passing (not implemented)
                 'MMP' - Marginal message passing (not implemented)
                 'BP'  - Belief propagation (not implemented)
                 'EP'  - Expectation propagation (not implemented)
                 'CV'  - CLuster variation method (not implemented)
    - **kwargs: 
        List of keyword/parameter arguments corresponding to parameter values for the respective variational inference algorithm

    Returns
    ----------
    - 'qs' [numpy 1D array, array of arrays (with 1D numpy array entries), or Categorical]:
        Marginal posterior beliefs over hidden states 
    """

    # safe convert to numpy
    A = utils.to_numpy(A)

    # collect model dimensions
    if utils.is_arr_of_arr(A):
        n_factors = A[0].ndim - 1
        n_states = list(A[0].shape[1:])
        n_modalities = len(A)
        n_observations = []
        for m in range(n_modalities):
            n_observations.append(A[m].shape[0])
    else:
        n_factors = A.ndim - 1
        n_states = list(A.shape[1:])
        n_modalities = 1
        n_observations = [A.shape[0]]

    obs = process_observations(obs, n_modalities, n_observations)
    if prior is not None:
        prior = process_priors(prior, n_factors)

    if method is FPI:
        qs = run_fpi(A, obs, n_observations, n_states, prior, **kwargs)
    elif method is VMP:
        raise NotImplementedError(f"{VMP} is not implemented")
    elif method is MMP:
        raise NotImplementedError(f"{MMP} is not implemented")
    elif method is BP:
        raise NotImplementedError(f"{BP} is not implemented")
    elif method is EP:
        raise NotImplementedError(f"{EP} is not implemented")
    elif method is CV:
        raise NotImplementedError(f"{CV} is not implemented")
    else:
        raise ValueError(f"{method} is not implemented")

    if return_numpy:
        return qs
    else:
        return utils.to_categorical(qs)


def process_observations(obs, n_modalities, n_observations):
    """
    Helper function for formatting observations    

        Observations can either be `Categorical`, `int` (converted to one-hot)
        or `tuple` (obs for each modality)
    
    @TODO maybe provide error messaging about observation format
    """
    if utils.is_distribution(obs):
        obs = utils.to_numpy(obs)
        if n_modalities == 1:
            obs = obs.squeeze()
        else:
            for m in range(n_modalities):
                obs[m] = obs[m].squeeze()

    if isinstance(obs, (int, np.integer)):
        obs = np.eye(n_observations[0])[obs]

    if isinstance(obs, tuple):
        obs_arr_arr = np.empty(n_modalities, dtype=object)
        for m in range(n_modalities):
            obs_arr_arr[m] = np.eye(n_observations[m])[obs[m]]
        obs = obs_arr_arr

    return obs


def process_priors(prior, n_factors):
    """
    Helper function for formatting observations  
    
    @TODO
    """
    if utils.is_distribution(prior):
        prior_arr = np.empty(n_factors, dtype=object)
        if n_factors == 1:
            prior_arr[0] = prior.values.squeeze()
        else:
            for factor in range(n_factors):
                prior_arr[factor] = prior[factor].values.squeeze()
        prior = prior_arr

    elif not utils.is_arr_of_arr(prior):
        prior = utils.to_arr_of_arr(prior)

    return prior


def print_inference_methods():
    print(f"Avaliable Inference methods: {FPI}")
