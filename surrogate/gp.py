"""Gaussian-process regression in numpy/scipy (no scikit-learn), for small CFD data sets.

Kernel on inputs x scaled to the variable range (x - x_base) / (hi - lo):

    k(x, x') = s_lin^2 * x.x'                      (linear trend, Bayesian linear regression)
             + s_f^2 * Matern52(|x - x'| / l_d)    (ARD, one length per variable)
             + s_n^2 * delta                       (CFD noise, fixed from repeat cases)

plus a constant offset with a broad prior (s_c = 10 x data sd), i.e. an estimated mean level
rather than a fixed one, so the prediction between data points does not sag towards the
average of an unbalanced sample. Length scales are at least 0.3 of a variable's range: an
aero effect is not expected to wiggle faster than that, and shorter scales only fit CFD
noise between near-duplicate cases. The linear term lets a variable with a single
data point carry a slope while the prior keeps unexplored variables near the baseline
with a growing variance. The noise is fixed, not fitted: it comes from the remeshing-noise
cases (base-like designs), so the GP does not chase CFD scatter.
Hyperparameters (s_lin, s_f, l_d) maximise the log marginal likelihood (L-BFGS-B, restarts).
"""
import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize

SQ5 = np.sqrt(5.0)


def matern52(X1, X2, ell):
    d = np.sqrt(np.maximum((((X1[:, None, :] - X2[None, :, :]) / ell) ** 2).sum(-1), 0.0))
    return (1 + SQ5 * d + 5.0 / 3.0 * d * d) * np.exp(-SQ5 * d)


class GP:
    def __init__(self, noise_sd, ell_bounds=(0.3, 20.0), restarts=8, seed=0):
        self.noise_sd = float(noise_sd)
        self.c2 = 0.0
        self.ell_bounds = ell_bounds
        self.restarts = restarts
        self.rng = np.random.default_rng(seed)

    # theta = log [s_lin, s_f, l_1 .. l_d]
    def _unpack(self, th):
        e = np.exp(th)
        return e[0], e[1], e[2:]

    def _K(self, X1, X2, th):
        s_lin, s_f, ell = self._unpack(th)
        return self.c2 + s_lin ** 2 * X1 @ X2.T + s_f ** 2 * matern52(X1, X2, ell)

    def _nll(self, th):
        K = self._K(self.X, self.X, th) + (self.noise_sd ** 2 + 1e-10) * np.eye(len(self.X))
        try:
            c = cho_factor(K, lower=True)
        except np.linalg.LinAlgError:
            return 1e10
        a = cho_solve(c, self.r)
        return 0.5 * self.r @ a + np.log(np.diag(c[0])).sum() + 0.5 * len(self.r) * np.log(2 * np.pi)

    def fit(self, X, y, theta=None):
        self.X, self.y = np.asarray(X, float), np.asarray(y, float)
        self.mu0 = self.y.mean()
        self.r = self.y - self.mu0
        d = self.X.shape[1]
        sy = max(self.r.std(), self.noise_sd)
        self.c2 = (10.0 * sy) ** 2
        lo =np.r_[np.log(1e-3 * sy), np.log(1e-3 * sy), np.full(d, np.log(self.ell_bounds[0]))]
        hi = np.r_[np.log(1e2 * sy), np.log(1e2 * sy), np.full(d, np.log(self.ell_bounds[1]))]
        if theta is None:
            best = None
            for k in range(self.restarts):
                x0 = (np.r_[np.log(sy), np.log(sy), np.zeros(d)] if k == 0
                      else self.rng.uniform(lo, hi))
                res = minimize(self._nll, x0, method="L-BFGS-B", bounds=list(zip(lo, hi)))
                if best is None or res.fun < best.fun:
                    best = res
            theta = best.x
        self.theta = np.asarray(theta, float)
        K = self._K(self.X, self.X, self.theta) + (self.noise_sd ** 2 + 1e-10) * np.eye(len(self.X))
        self.chol = cho_factor(K, lower=True)
        self.alpha = cho_solve(self.chol, self.r)
        self.Kinv = cho_solve(self.chol, np.eye(len(self.X)))
        return self

    def predict(self, Xs, noise=False):
        """Mean and standard deviation of the latent function (noise=False) or of a new CFD run."""
        Xs = np.atleast_2d(np.asarray(Xs, float))
        ks = self._K(Xs, self.X, self.theta)
        mu = self.mu0 + ks @ self.alpha
        kss = np.diag(self._K(Xs, Xs, self.theta))
        var = kss - np.einsum("ij,jk,ik->i", ks, self.Kinv, ks)
        if noise:
            var = var + self.noise_sd ** 2
        return mu, np.sqrt(np.maximum(var, 0.0))

    def loo(self):
        """Closed-form leave-one-out (hyperparameters kept): mean and sd of each left-out CFD value."""
        d = np.diag(self.Kinv)
        return self.y - self.alpha / d, np.sqrt(1.0 / d)

    def params(self):
        s_lin, s_f, ell = self._unpack(self.theta)
        return dict(s_lin=float(s_lin), s_f=float(s_f), ell=[float(v) for v in ell], c2=self.c2,
                    noise_sd=self.noise_sd, mu0=float(self.mu0), nll=float(self._nll(self.theta)))
