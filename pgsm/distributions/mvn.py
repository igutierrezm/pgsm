from __future__ import division

import numpy as np

from pgsm.math_utils import cholesky_update, log_gamma, outer_product


class MultivariateNormalSufficientStatistics(object):

    def __init__(self, X):
        X = np.atleast_2d(X)
        self.N = X.shape[0]
        self.X = np.zeros(X.shape[1], dtype=np.float64)
        for n in range(self.N):
            self.X += X[n]
        self.S = np.dot(X.T, X)

    def copy(self):
        copy = MultivariateNormalSufficientStatistics.__new__(MultivariateNormalSufficientStatistics)
        copy.N = self.N
        copy.X = self.X.copy()
        copy.S = self.S.copy()
        return copy

    def decrement(self, x):
        self.N -= 1
        self.X -= x
        self.S -= outer_product(x, x)

    def increment(self, x):
        self.N += 1
        self.X += x
        self.S += outer_product(x, x)


class MultivariateNormalPriors(object):

    def __init__(self, dim):
        self.dim = dim

        self.nu = dim + 2
        self.r = 1
        self.S = np.eye(dim)
        self.u = np.zeros(dim)
        self.log_det_S = np.linalg.slogdet(self.S)[1]


class MultivariateNormalParameters(object):

    def __init__(self, priors, ss):
        self.priors = priors
        self.ss = ss
        self._update_nu()
        self._update_r()
        self._update_u()
        self._update_S_chol()

    @property
    def log_det_S(self):
        return 2 * np.sum(np.log(np.diag(self.S_chol)))

    @property
    def S(self):
        return np.dot(self.S_chol, np.conj(self.S_chol.T))

    def copy(self):
        copy = MultivariateNormalParameters.__new__(MultivariateNormalParameters)
        copy.priors = self.priors
        copy.ss = self.ss.copy()
        copy.nu = self.nu
        copy.r = self.r
        copy.u = self.u.copy()
        copy.S_chol = self.S_chol.copy()
        return copy

    def decrement(self, x):
        self.S_chol = cholesky_update(self.S_chol, np.sqrt(self.r) * self.u, 1)
        self.ss.decrement(x)
        self._update_nu()
        self._update_r()
        self._update_u()
        self.S_chol = cholesky_update(self.S_chol, x, -1)
        self.S_chol = cholesky_update(self.S_chol, np.sqrt(self.r) * self.u, -1)

    def increment(self, x):
        self.S_chol = cholesky_update(self.S_chol, np.sqrt(self.r) * self.u, 1)
        self.ss.increment(x)
        self._update_nu()
        self._update_r()
        self._update_u()
        self.S_chol = cholesky_update(self.S_chol, x, 1)
        self.S_chol = cholesky_update(self.S_chol, np.sqrt(self.r) * self.u, -1)

    def _update_nu(self):
        self.nu = self.priors.nu + self.ss.N

    def _update_r(self):
        self.r = self.priors.r + self.ss.N

    def _update_u(self):
        self.u = ((self.priors.r * self.priors.u) + self.ss.X) / self.r

    def _update_S_chol(self):
        S = self.priors.S + self.ss.S + \
            self.priors.r * outer_product(self.priors.u, self.priors.u) - \
            self.r * outer_product(self.u, self.u)
        self.S_chol = np.linalg.cholesky(S)


class MultivariateNormal(object):

    def __init__(self, priors):
        self.priors = priors

    def create_params(self, x):
        ss = MultivariateNormalSufficientStatistics(x)
        return MultivariateNormalParameters(self.priors, ss)

    def log_marginal_likelihood(self, params):
        D = self.priors.dim
        N = params.ss.N
        d = np.arange(1, D + 1)
        return -0.5 * N * D * np.log(np.pi) + \
            0.5 * D * (np.log(self.priors.r) - np.log(params.r)) + \
            0.5 * (self.priors.nu * self.priors.log_det_S - params.nu * params.log_det_S) + \
            np.sum(log_gamma(0.5 * (params.nu + 1 - d)) - log_gamma(0.5 * (self.priors.nu + 1 - d)))
