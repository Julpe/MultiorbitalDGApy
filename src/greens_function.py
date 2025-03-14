from copy import deepcopy

import numpy as np

import config
from local_n_point import LocalNPoint
from matsubara_frequencies import MFHelper
from n_point_base import IAmNonLocal
from self_energy import SelfEnergy


class GreensFunction(LocalNPoint, IAmNonLocal):
    """
    Represents a Green's function.
    """

    def __init__(
        self,
        mat: np.ndarray,
        sigma: SelfEnergy = None,
        ek: np.ndarray = None,
        full_niv_range: bool = True,
        calc_filling: bool = True,
    ):
        LocalNPoint.__init__(self, mat, 2, 0, 1, full_niv_range=full_niv_range)
        IAmNonLocal.__init__(self, mat, config.lattice.nk)
        self._sigma = sigma
        self._ek = ek

        if sigma is not None and ek is not None and calc_filling:
            self.mat = self._get_gloc_mat()
            config.sys.n, config.sys.occ = self._get_fill()

    @property
    def e_kin(self):
        """
        Returns the kinetic energy of the system, see Eq (22) in G. Rohringer & A. Toschi PHYSICAL REVIEW B 94, 125144 (2016).
        """
        ekin = 2 / config.sys.beta * np.sum(np.mean(self._ek[..., None] * self.mat, axis=(0, 1, 2)))
        assert np.abs(ekin.imag) < 1e-8, "Kinetic energy must be real."
        return ekin.real

    @property
    def n_bands(self) -> int:
        return self.original_shape[1] if self.has_compressed_q_dimension else self.original_shape[3]

    def get_g_full(self) -> "GreensFunction":
        return GreensFunction(self._get_gfull_mat(), self._sigma, self._ek, True, False)

    @staticmethod
    def create_g_loc(siw: SelfEnergy, ek: np.ndarray) -> "GreensFunction":
        """
        Returns a local Green's function object from a given self-energy and band dispersion.
        """
        return GreensFunction(np.empty_like(siw.mat), siw, ek, siw.full_niv_range)

    def permute_orbitals(self, permutation: str = "ab->ab"):
        """
        Permutes the orbitals of the Green's function object. The permutation string must be given in the einsum notation.
        """
        split = permutation.split("->")
        if len(split) != 2 or len(split[0]) != 2 or len(split[1]) != 2:
            raise ValueError("Invalid permutation.")

        if split[0] == split[1]:
            return self

        permutation = (
            f"i{split[0]}...->i{split[1]}..."
            if self.has_compressed_q_dimension
            else f"ijk{split[0]}...->ijk{split[1]}..."
        )

        copy = deepcopy(self)
        copy.mat = np.einsum(permutation, copy.mat, optimize=True)
        return copy

    def transpose_orbitals(self):
        r"""
        Transposes the orbitals of the Green's function object.
        .. math:: G_{ab}^\nu -> G_{ba}^\nu
        """
        return self.permute_orbitals("ab->ba")

    def _get_fill(self) -> (float, np.ndarray):
        """
        Returns the total filling and the filling of each band.
        """
        mat = self._get_gloc_mat()
        g_model = self._get_g_model_mat()
        hloc: np.ndarray = np.mean(self._ek, axis=(0, 1, 2))
        smom0, _ = self._sigma.smom
        mu_bands: np.ndarray = config.sys.mu * np.eye(self.n_bands)

        eigenvals, eigenvecs = np.linalg.eig(config.sys.beta * (hloc.real + smom0 - mu_bands))
        rho_loc_diag = np.zeros((self.n_bands, self.n_bands), dtype=np.complex64)
        for i in range(self.n_bands):
            if eigenvals[i] > 0:
                rho_loc_diag[i, i] = np.exp(-eigenvals[i]) / (1 + np.exp(-eigenvals[i]))
            else:
                rho_loc_diag[i, i] = 1 / (1 + np.exp(eigenvals[i]))

        rho_loc = eigenvecs @ rho_loc_diag @ np.linalg.inv(eigenvecs)
        occ = rho_loc + np.sum(mat.real - g_model.real, axis=-1) / config.sys.beta
        n_el = 2.0 * np.trace(occ).real
        return n_el, occ

    def _get_fill_nonlocal(self) -> (float, np.ndarray):
        """
        Returns the total filling and the filling of each band k-dependent.
        TODO: FIX THIS OR ATLEAST TRY TO
        """
        mat = self._get_gfull_mat()
        g_model = self._get_g_model_mat()
        smom0, _ = self._sigma.smom[None, None, None, ...]
        mu_bands: np.ndarray = config.sys.mu * np.eye(self.n_bands)[None, None, None, ...]

        eigenvals, eigenvecs = np.linalg.eig(config.sys.beta * (self._ek.real + smom0 - mu_bands))
        rho_diag = np.zeros((*self.nq, self.n_bands, self.n_bands), dtype=np.complex64)

    def _get_gfull_mat(self):
        iv_bands, mu_bands = self._get_g_params_local()
        iv_bands = iv_bands[None, None, None, ...]
        mu_bands = mu_bands[None, None, None, ...]

        sigma_mat = self._sigma.mat
        if len(self._sigma.mat.shape) == 3:  # (o1,o1,v)
            sigma_mat = sigma_mat[None, None, None, ...]
        mat = iv_bands + mu_bands - self._ek[..., None] - sigma_mat
        return np.linalg.inv(mat.transpose(0, 1, 2, 5, 3, 4)).transpose(0, 1, 2, 4, 5, 3)

    def _get_gloc_mat(self):
        return np.mean(self._get_gfull_mat(), axis=(0, 1, 2))

    def _get_g_model_mat(self):
        iv_bands, mu_bands = self._get_g_params_local()
        hloc: np.ndarray = np.mean(self._ek, axis=(0, 1, 2))
        smom0, _ = self._sigma.smom
        mat = iv_bands + mu_bands - hloc[..., None] - smom0[..., np.newaxis]
        return np.linalg.inv(mat.transpose(2, 0, 1)).transpose(1, 2, 0)

    def _get_g_params_local(self):
        eye_bands = np.eye(self.n_bands, self.n_bands)
        iv = 1j * MFHelper.vn(self.niv, config.sys.beta)
        iv_bands = iv[None, None, :] * eye_bands[..., None]
        mu_bands = config.sys.mu * eye_bands[:, :, None]
        return iv_bands, mu_bands
