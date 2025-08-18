import itertools as it
from copy import deepcopy

import numpy as np

import scdga.config as config
from scdga.local_n_point import LocalNPoint
from scdga.matsubara_frequencies import MFHelper
from scdga.n_point_base import IAmNonLocal


class SelfEnergy(LocalNPoint, IAmNonLocal):
    """
    Represents the self-energy. Will automatically map to full niv range if full_niv_range is set to False.
    """

    def __init__(
        self,
        mat: np.ndarray,
        nk: tuple[int, int, int] = (1, 1, 1),
        full_niv_range: bool = True,
        has_compressed_q_dimension: bool = False,
        estimate_niv_core: bool = False,
    ):
        LocalNPoint.__init__(self, mat, 2, 0, 1, full_niv_range=full_niv_range)
        IAmNonLocal.__init__(self, mat, nk, has_compressed_q_dimension=has_compressed_q_dimension)
        # TODO: check if this is a reasonable value. I'd suggest it depends on the input data size.
        self._niv_core_min = 20

        if not full_niv_range:
            self.to_full_niv_range()

        self._smom0, self._smom1 = self.fit_smom()
        self._niv_core = self._estimate_niv_core() if estimate_niv_core else self.niv

    @property
    def smom(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Returns the first two local momenta of the self-energy.
        """
        return self._smom0, self._smom1

    @property
    def n_bands(self) -> int:
        """
        Returns the number of bands.
        """
        return self.original_shape[1] if self.has_compressed_q_dimension else self.original_shape[3]

    def fit_smom(self):
        """
        Fits the first two local momenta of the self-energy.
        """
        compress = False
        if self.has_compressed_q_dimension:
            compress = True
            self.decompress_q_dimension()

        mat_half_v = np.mean(self.mat[..., self.niv :], axis=(0, 1, 2))
        iv = 1j * MFHelper.vn(self.niv, config.sys.beta, return_only_positive=True)

        n_freq_fit = int(0.2 * self.niv)
        if n_freq_fit < 4:
            n_freq_fit = 4

        iwfit = iv[self.niv - n_freq_fit :][None, None, :]  # * np.eye(self.n_bands)[:, :, None]
        fitdata = mat_half_v[..., self.niv - n_freq_fit :]

        mom0 = np.mean(fitdata.real, axis=-1)
        mom1 = np.mean(fitdata.imag * iwfit.imag, axis=-1)

        if compress:
            self.compress_q_dimension()
        return mom0, mom1

    def create_with_asympt_up_to_core(self) -> "SelfEnergy":
        """
        Concatenates the core and the asymptotic tail of the self-energy from the 'estimated' core region to the actual
        specified core region (in settings).
        """
        copy = deepcopy(self)
        asympt = copy._get_asympt(niv=copy.niv)

        if copy._niv_core == copy.niv:
            return copy
        if asympt.niv == 0:
            return copy

        copy = copy.cut_niv(copy._niv_core)
        copy.mat = np.concatenate(
            (asympt.mat[..., : asympt.niv - copy.niv], copy.mat, asympt.mat[..., asympt.niv + copy.niv :]), axis=-1
        )
        return copy

    def append_asympt(self, niv: int):
        """
        Adds the asymptotic tail to the self-energy up to niv.
        """
        copy = deepcopy(self)
        asympt = copy._get_asympt(niv)
        if niv <= copy.niv:
            return copy
        copy.mat = np.concatenate(
            (asympt.mat[..., : asympt.niv - copy.niv], copy.mat, asympt.mat[..., asympt.niv + copy.niv :]), axis=-1
        )
        return copy

    def __add__(self, other):
        """
        Adds two SelfEnergy objects.
        """
        return self.add(other)

    def __sub__(self, other):
        """
        Subtracts two SelfEnergy objects.
        """
        return self.sub(other)

    def add(self, other) -> "SelfEnergy":
        """
        Adds two SelfEnergy objects.
        """
        if not isinstance(other, (SelfEnergy, np.ndarray)):
            raise ValueError(f"Can not add {type(other)} to {type(self)}.")

        if isinstance(other, np.ndarray):
            return SelfEnergy(self.mat + other, self.nq, self.full_niv_range, self.has_compressed_q_dimension, False)

        other = self._align_q_dimensions_for_operations(other)
        return SelfEnergy(self.mat + other.mat, self.nq, self.full_niv_range, self.has_compressed_q_dimension, False)

    def sub(self, other) -> "SelfEnergy":
        """
        Subtracts two SelfEnergy objects.
        """
        return self.add(-other)

    def concatenate_self_energies(self, other: "SelfEnergy") -> "SelfEnergy":
        """
        Concats the self-energy with the other self-energy up to other.niv.
        """
        if self.niv > other.niv:
            raise ValueError("Can not concatenate with a self-energy that has less frequencies.")
        niv_diff = other.niv - self.niv

        self.compress_q_dimension()
        other = other.compress_q_dimension()

        other_mat = np.tile(other.mat, (self.nq_tot, 1, 1, 1)) if other.nq_tot == 1 else other.mat
        result_mat = np.concatenate(
            (other_mat[..., :niv_diff], self.mat, other_mat[..., niv_diff + 2 * self.niv :]), axis=-1
        )
        return SelfEnergy(result_mat, self.nq, self.full_niv_range, self.has_compressed_q_dimension, False)

    def fit_polynomial(self, n_fit: int = 4, degree: int = 3, niv_core: int = 0) -> "SelfEnergy":
        """
        Fits a polynomial of a given degree to the self-energy.
        """
        copy = deepcopy(self)

        if n_fit == 0:
            return copy

        if n_fit > copy.niv or n_fit < 0:
            n_fit = niv_core + 200

        copy = copy.compress_q_dimension().to_half_niv_range()
        vn_fit = MFHelper.vn(n_fit, return_only_positive=True)
        vn_full = MFHelper.vn(2 * copy.niv, return_only_positive=True)
        poly_mat = np.zeros_like(copy.mat)
        fit_mat = copy.cut_niv(n_fit).mat

        for k in range(copy.nq_tot):
            for o1 in range(copy.n_bands):
                for o2 in range(copy.n_bands):
                    poly = np.polyfit(vn_fit, fit_mat[k, o1, o2, ...], degree)
                    poly_mat[k, o1, o2, :] = np.polyval(poly, vn_full)

        return SelfEnergy(poly_mat, copy.nq, copy.full_niv_range, copy.has_compressed_q_dimension, False)

    def rotate_orbitals(self, theta: float = np.pi):
        r"""
        Rotates the orbitals of the four-point object around the angle :math:`\theta`. :math:`\theta` must be given in
        radians and the number of orbitals needs to be 2.
        """
        copy = deepcopy(self)

        if theta == 0:
            return copy

        if self.n_bands != 2:
            raise ValueError("Rotating the orbitals is only allowed for objects that have two bands.")

        r = np.array([[np.cos(theta), np.sin(theta)], [-np.sin(theta), np.cos(theta)]])

        einsum_str = "ip,qj,xpq...->xij..." if self.has_compressed_q_dimension else "ip,qj,xyzpq...->xyzij..."
        copy.mat = np.einsum(einsum_str, r.T, r, copy.mat, optimize=True)
        return copy

    def _estimate_niv_core(self, err: float = 1e-5):
        """
        Check when the real and the imaginary part are within an error margin of the asymptotic.
        """
        asympt = self._get_asympt(niv=self.niv, n_min=0)

        max_ind_real = 0
        max_ind_imag = 0

        for i, j in it.product(range(self.n_bands), repeat=2):
            k_mean = np.mean(self.mat[:, :, :, i, j, :], axis=(0, 1, 2))
            asympt_mean = np.mean(asympt.mat[:, :, :, i, j, :], axis=(0, 1, 2))
            ind_real = np.argmax(np.abs(k_mean.real - asympt_mean.real) < err)
            ind_imag = np.argmax(np.abs(k_mean.imag - asympt_mean.imag) < err)

            max_ind_real = max(max_ind_real, ind_real)
            max_ind_imag = max(max_ind_imag, ind_imag)

        niv_core = max(max_ind_real, max_ind_imag)
        if niv_core < self._niv_core_min:
            return self._niv_core_min
        return niv_core

    def _get_asympt(self, niv: int, n_min: int = None) -> "SelfEnergy":
        """
        Returns purely the asymptotic behaviour of the self-energy for the given frequency range.
        Not intended to be used as its own but intended to be padded to the self-energy as an asymptotic tail.
        """
        if n_min is None:
            n_min = self.niv
        iv_asympt = 1j * MFHelper.vn(niv, config.sys.beta, shift=n_min)[None, None, ...]
        asympt = (self._smom0[..., None] - 1.0 / iv_asympt * self._smom1[..., None])[None, None, None, ...] * np.ones(
            self.nq
        )[..., None, None, None]
        return SelfEnergy(asympt, self.nq)
