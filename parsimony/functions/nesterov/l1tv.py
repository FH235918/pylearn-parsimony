# -*- coding: utf-8 -*-
"""
The :mod:`parsimony.functions.nesterov.L1TV` module contains the loss function
for the L1 + TV penalty, smoothed together using Nesterov's technique.

Created on Mon Feb  3 17:04:14 2014

Copyright (c) 2013-2014, CEA/DSV/I2BM/Neurospin. All rights reserved.

@author:  Tommy Löfstedt, Vincent Guillemot, Edouard Duchesnay and
          Fouad Hadj-Selem
@email:   lofstedt.tommy@gmail.com, edouard.duchesnay@cea.fr
@license: BSD 3-clause.
"""
import math

import scipy.sparse as sparse
import numpy as np

#from .properties import NesterovFunction
from .. import properties
import parsimony.utils.consts as consts
import parsimony.utils.maths as maths
import parsimony.utils as utils
import tv
import l1

__all__ = ["L1TV",
           "linear_operator_from_mask", "A_from_mask",
           "linear_operator_from_shape", "A_from_shape"]


class L1TV(properties.NesterovFunction,
           properties.Penalty,
           properties.Eigenvalues):
    """The proximal operator of the smoothed sum of the TV and L1 functions

        f(beta) = (l1 * L1(beta) + tv * TV(beta))_mu,

    where (...)_mu means that what's within parentheses is smoothed.
    """
    def __init__(self, l1, tv, A=None, mu=0.0, penalty_start=0):
        """
        Parameters
        ----------
        l1 : Non-negative float. The Lagrange multiplier, or regularisation
                constant, of the smoothed L1 part of the function.

        tv : Non-negative float. The Lagrange multiplier, or regularisation
                constant, of the smoothed total variation part of the function.

        A : A list or tuple with 4 elements of (usually sparse) arrays. The
                linear operator for the smoothed L1+TV. The first element must
                be the linear operator for L1 and the following three for TV.
                May not be None.

        mu : Non-negative float. The regularisation constant for the smoothing.

        penalty_start : Non-negative integer. The number of columns, variables
                etc., to exempt from penalisation. Equivalently, the first
                index to be penalised. Default is 0, all columns are included.
        """
        self.g = float(tv)

        # WARNING: Number of non-zero rows may differ from p.
        self._p = A[0].shape[1]
        A = [l1 * A[0],
             tv * A[1],
             tv * A[2],
             tv * A[3]]

        super(L1TV, self).__init__(l1, A=A, mu=mu, penalty_start=penalty_start)

        self.reset()

    def reset(self):

        self._lambda_max = None

    def f(self, beta):
        """ Function value.
        """
        if self.l < consts.TOLERANCE and self.g < consts.TOLERANCE:
            return 0.0

        if self.penalty_start > 0:
            beta_ = beta[self.penalty_start:, :]
        else:
            beta_ = beta

        # lambda and gamma are in A.
        A = self.A()
        return maths.norm1(A[0].dot(beta_)) + \
               np.sum(np.sqrt(A[1].dot(beta_) ** 2.0 +
                              A[2].dot(beta_) ** 2.0 +
                              A[3].dot(beta_) ** 2.0))

    def fmu(self, beta, mu=None):
        """Returns the smoothed function value.

        Parameters:
        ----------
        beta : Numpy array. The weight vector.

        mu : Non-negative float. The regularisation constant for the smoothing.
        """
        if mu is None:
            mu = self.get_mu()

        alpha = self.alpha(beta)
        alpha_sqsum = 0.0
        for a in alpha:
            alpha_sqsum += np.sum(a ** 2.0)

        Aa = self.Aa(alpha)

        return np.dot(beta.T, Aa)[0, 0] - (mu / 2.0) * alpha_sqsum

    def phi(self, alpha, beta):
        """ Function value with known alpha.

        From the interface "NesterovFunction".
        """
        if self.l < consts.TOLERANCE and self.g < consts.TOLERANCE:
            return 0.0

        Aa = self.Aa(alpha)

        alpha_sqsum = 0.0
        for a in alpha:
            alpha_sqsum += np.sum(a ** 2.0)

        if self.penalty_start > 0:
            beta_ = beta[self.penalty_start:, :]
        else:
            beta_ = beta

        return np.dot(beta_.T, Aa)[0, 0] - (self.mu / 2.0) * alpha_sqsum

    def lambda_max(self):
        """ Largest eigenvalue of the corresponding covariance matrix.

        From the interface "Eigenvalues".
        """
        # Note that we can save the state here since lmax(A) does not change.
        if len(self._A) == 4 and self._A[2].nnz == 0 and self._A[3].nnz == 0:
#        if len(self._shape) == 3 \
#            and self._shape[0] == 1 and self._shape[1] == 1:
            # TODO: Instead of p, this should really be the number of non-zero
            # rows of A.
            p = self._A[1].shape[0]
            lmaxTV = 2.0 * (1.0 - math.cos(float(p - 1) * math.pi
                                           / float(p)))
            self._lambda_max = lmaxTV * self.g ** 2.0 + self.l ** 2.0

        elif self._lambda_max is None:

            from parsimony.algorithms.nipals import FastSparseSVD

            A = sparse.vstack(self.A()[1:])
            # TODO: Add max_iter here!!
            v = FastSparseSVD().run(A)  # , max_iter=max_iter)
            us = A.dot(v)
            self._lambda_max = np.sum(us ** 2.0) + self.l ** 2.0

        return self._lambda_max

#    """ Linear operator of the Nesterov function.
#
#    From the interface "NesterovFunction".
#    """
#    def A(self):
#
#        return self._A

#    """ Computes A^\T\alpha.
#
#    From the interface "NesterovFunction".
#    """
#    def Aa(self, alpha):
#
#        A = self.A()
#        Aa = A[0].T.dot(alpha[0])
#        for i in xrange(1, len(A)):
#            Aa += A[i].T.dot(alpha[i])
#
#        return Aa

    def lA(self):
        """ Linear operator of the Nesterov function multiplied by the
        corresponding Lagrange multipliers.

        Note that in this case, the A matrices are already multiplied by the
        Lagrange multipliers.
        """
        A = self.A()

        return A

    def alpha(self, beta):
        """ Dual variable of the Nesterov function.

        From the interface "NesterovFunction". Overloaded since we need to do
        more than the default.
        """
        A = self.A()

        if self.penalty_start > 0:
            beta_ = beta[self.penalty_start:, :]
        else:
            beta_ = beta

        a = [0] * len(A)
        a[0] = (1.0 / self.mu) * A[0].dot(beta_)
        a[1] = (1.0 / self.mu) * A[1].dot(beta_)
        a[2] = (1.0 / self.mu) * A[2].dot(beta_)
        a[3] = (1.0 / self.mu) * A[3].dot(beta_)
        # Remember: lambda and gamma are already in the A matrices.

        return self.project(a)

    def project(self, a):
        """ Projection onto the compact space of the Nesterov function.

        From the interface "NesterovFunction".
        """
        # L1
        al1 = a[0]
        anorm_l1 = np.abs(al1)
        i_l1 = anorm_l1 > 1.0
        anorm_l1_i = anorm_l1[i_l1]
        al1[i_l1] = np.divide(al1[i_l1], anorm_l1_i)

        # TV
        ax = a[1]
        ay = a[2]
        az = a[3]
        anorm_tv = ax ** 2.0 + ay ** 2.0 + az ** 2.0
        i_tv = anorm_tv > 1.0

        anorm_tv_i = anorm_tv[i_tv] ** 0.5  # Square root taken here. Faster.
        ax[i_tv] = np.divide(ax[i_tv], anorm_tv_i)
        ay[i_tv] = np.divide(ay[i_tv], anorm_tv_i)
        az[i_tv] = np.divide(az[i_tv], anorm_tv_i)

        return [al1, ax, ay, az]

    def estimate_mu(self, beta):
        """Computes a "good" value of mu with respect to the given beta.

        From the interface "NesterovFunction".
        """
        raise NotImplementedError("We do not use this here!")

    def M(self):
        """ The maximum value of the regularisation of the dual variable. We
        have

            M = max_{alpha in K} 0.5*|alpha|²_2.

        From the interface "NesterovFunction".
        """
        A = self.A()

        # A[0] is L1, A[1-3] is TV.
        return (A[0].shape[0] / 2.0) \
             + (A[1].shape[0] / 2.0)


@utils.deprecated("linear_operator_from_mask")
def A_from_mask(*args, **kwargs):

    return linear_operator_from_mask(*args, **kwargs)


# TODO: Do we need to take the number of variables here?
# Why not use np.prod(shape) + penalty_start instead and save a parameter?
def linear_operator_from_mask(mask, num_variables, penalty_start=0):
    """Generates the linear operator for the total variation Nesterov function
    from a mask for a 3D image.

    Parameters
    ----------
    mask : Numpy array. The mask. The mask does not involve any intercept
            variables.

    num_variables : Positive integer. The total number of variables, including
            the intercept variable(s).

    penalty_start : Non-negative integer. The number of variables to exempt
            from penalisation. Equivalently, the first index to be penalised.
            Default is 0, all variables are included.
    """
    Atv, _ = tv.A_from_mask(mask)
    Al1 = l1.A_from_variables(num_variables, penalty_start=penalty_start)

    return Al1[0], Atv[0], Atv[1], Atv[2]


@utils.deprecated("linear_operator_from_shape")
def A_from_shape(*args, **kwargs):

    return linear_operator_from_shape(*args, **kwargs)


# TODO: Do we need to take the number of variables here?
# Why not use np.prod(shape) + penalty_start instead and save a parameter?
def linear_operator_from_shape(shape, num_variables, penalty_start=0):
    """Generates the linear operator for the total variation Nesterov function
    from the shape of a 3D image.

    Parameters
    ----------
    shape : List or tuple with 1, 2 or 3 elements. The shape of the 1D, 2D or
            3D image. shape has the form (Z, Y, X), where Z is the number of
            "layers", Y is the number of rows and X is the number of columns.
            The shape does not involve any intercept variables.

    num_variables : Positive integer. The total number of variables, including
            the intercept variable(s).

    penalty_start : Non-negative integer. The number of variables to exempt
            from penalisation. Equivalently, the first index to be penalised.
            Default is 0, all variables are included.
    """
    Atv, _ = tv.A_from_shape(shape)
    Al1 = l1.A_from_variables(num_variables, penalty_start=penalty_start)

    return Al1[0], Atv[0], Atv[1], Atv[2]