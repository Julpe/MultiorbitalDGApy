from copy import deepcopy

import numpy as np
from scipy import optimize as opt

import config
from local_n_point import LocalNPoint
from matsubara_frequencies import MFHelper
from n_point_base import IAmNonLocal
from self_energy import SelfEnergy


def get_total_fill(mu: float, ek: np.ndarray, sigma_mat: np.ndarray, beta: float, smom0: np.ndarray) -> float:
    """
    Returns the total filling. Helper method for root finding of mu.
    """
    n_bands = sigma_mat.shape[-2]
    eye_bands = np.eye(n_bands, n_bands)
    iv = 1j * MFHelper.vn(sigma_mat.shape[-1] // 2, beta)
    iv_bands = iv[None, None, :] * eye_bands[..., None]
    mu_bands = mu * eye_bands
    hloc = np.mean(ek, axis=(0, 1, 2))

    mat = iv_bands + mu_bands[..., None] - hloc[..., None] - smom0[..., None]
    g_model_mat = np.linalg.inv(mat.transpose(2, 0, 1)).transpose(1, 2, 0)

    ek = ek.reshape(np.prod(ek.shape[:3]), n_bands, n_bands)  # sigma will always enter with shape (k,o1,o2,v)
    mat = iv_bands[None, ...] + mu_bands[None, ..., None] - ek[..., None] - sigma_mat
    g_full_mat = np.linalg.inv(mat.transpose(0, 3, 1, 2)).transpose(0, 2, 3, 1)
    g_loc_mat = np.mean(g_full_mat, axis=0)

    eigenvals, eigenvecs = np.linalg.eig(beta * (hloc.real + smom0 - mu_bands))
    rho_diag = np.where(eigenvals > 0, np.exp(-eigenvals) / (1 + np.exp(-eigenvals)), 1 / (1 + np.exp(eigenvals)))
    rho_diag = np.einsum("...i,ij->...ij", rho_diag, np.eye(n_bands))

    rho_loc = eigenvecs @ rho_diag @ np.linalg.inv(eigenvecs)
    occ = rho_loc + np.sum(g_loc_mat.real - g_model_mat.real, axis=-1) / beta
    return 2.0 * np.trace(occ).real


def root_fun(
    mu: float, target_filling: float, ek: np.ndarray, sigma_mat: np.ndarray, beta: float, smom0: np.ndarray
) -> float:
    """
    Function to minimize in order to find a new mu via Newton's method.
    """
    return get_total_fill(mu, ek, sigma_mat, beta, smom0) - target_filling


def update_mu(
    mu0: float, target_filling: float, ek: np.ndarray, sigma_mat: np.ndarray, beta: float, smom0: np.ndarray
) -> float:
    """
    Updates the chemical potential to match the target filling.
    """
    mu = mu0
    try:
        mu = opt.newton(root_fun, mu, args=(target_filling, ek, sigma_mat, beta, smom0), tol=1e-6)
    except RuntimeError:
        config.logger.log_debug("Root finding for chemical potential failed, using old chemical potential.")

    if np.abs(mu.imag) < 1e-8:
        mu = mu.real
    else:
        raise ValueError("Chemical Potential must be real.")
    return mu


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
        has_compressed_q_dimension: bool = False,
    ):
        LocalNPoint.__init__(self, mat, 2, 0, 1, full_niv_range=full_niv_range)
        IAmNonLocal.__init__(self, mat, config.lattice.nk, has_compressed_q_dimension)
        self._sigma = sigma
        self._ek = ek

        if sigma is not None and ek is not None and calc_filling:
            self.mat = self._get_gloc_mat()
            # config.sys.n, config.sys.occ = self._get_fill()
            config.sys.n, config.sys.occ, config.sys.occ_k = self._get_fill_nonlocal()

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
        """
        Returns the number of bands.
        """
        return self.original_shape[1] if self.has_compressed_q_dimension else self.original_shape[3]

    @property
    def ek(self) -> np.ndarray:
        """
        Returns the band dispersion.
        """
        return self._ek

    def get_g_full_from_gloc(self) -> "GreensFunction":
        """
        Returns the full k-dependent Green's function.
        """
        return GreensFunction(self._get_gfull_mat(), self._sigma, self._ek, True, False)

    @staticmethod
    def get_g_full(siw: SelfEnergy, mu: float, ek: np.ndarray):
        """
        Returns the full k-dependent Green's function.
        """
        eye_bands = np.eye(siw.n_bands, siw.n_bands)
        iv = 1j * MFHelper.vn(siw.niv, config.sys.beta)
        iv_bands = iv[None, None, :] * eye_bands[..., None]
        mu_bands = mu * eye_bands[:, :, None]
        mat = (
            iv_bands[None, None, None, ...]
            + mu_bands[None, None, None, ...]
            - ek[..., None]
            - siw.decompress_q_dimension().mat
        )
        mat = np.linalg.inv(mat.transpose(0, 1, 2, 5, 3, 4)).transpose(0, 1, 2, 4, 5, 3)
        return GreensFunction(mat, siw, ek, siw.full_niv_range, False, False)

    @staticmethod
    def create_g_loc(siw: SelfEnergy, ek: np.ndarray, calc_filling: bool = True) -> "GreensFunction":
        """
        Returns a local Green's function object from a given self-energy and band dispersion.
        """
        return GreensFunction(np.empty_like(siw.mat), siw, ek, siw.full_niv_range, calc_filling)

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
        .. math:: G_{ab}^k -> G_{ba}^k
        """
        return self.permute_orbitals("ab->ba")

    def get_g_wv(self, wn: np.ndarray, niv_cut: int) -> np.ndarray:
        """
        Returns G_{ab}^{v-w}, shape is [o1,o2,w,v].
        """
        niv_cut_range = np.arange(-niv_cut, niv_cut)
        return self.mat[..., self.niv + niv_cut_range[None, :] - wn[:, None]]

    def get_g_qk_single_q(self, q: tuple, wn: np.ndarray, niv_cut: int) -> np.ndarray:
        """
        Returns G_{ab}^{k-q} for a single q point, shape is [k,o1,o2,w,v].
        """
        shifted_mat = self.shift_k_by_q(q)
        niv = shifted_mat.shape[-1] // 2
        niv_cut_range = np.arange(-niv_cut, niv_cut)
        shifted_mat = shifted_mat[..., niv + niv_cut_range[None, :] - wn[:, None]]
        return shifted_mat.reshape(config.lattice.k_grid.nk_tot, *shifted_mat.shape[3:])

    def _get_fill_nonlocal(self) -> tuple[float, np.ndarray, np.ndarray]:
        """
        Returns the total filling, the k-mean of the occupation and the occupation.
        """
        mat = self._get_gfull_mat()
        g_model = self._get_g_model_q_mat()
        smom0 = self._sigma.smom[0][None, None, None, ...]
        mu_bands: np.ndarray = config.sys.mu * np.eye(self.n_bands)[None, None, None, ...]

        eigenvals, eigenvecs = np.linalg.eig(config.sys.beta * (self._ek.real + smom0 - mu_bands))
        eigenvals = eigenvals.reshape((self.nq_tot, self.n_bands))
        eigenvecs = eigenvecs.reshape((self.nq_tot, self.n_bands, self.n_bands))

        rho_diag_k = np.where(eigenvals > 0, np.exp(-eigenvals) / (1 + np.exp(-eigenvals)), 1 / (1 + np.exp(eigenvals)))
        rho_diag_k = np.einsum("...i,ij->...ij", rho_diag_k, np.eye(self.n_bands))

        rho_k = (eigenvecs @ rho_diag_k @ np.linalg.inv(eigenvecs)).reshape((*self.nq, self.n_bands, self.n_bands))
        occ_k = rho_k + np.sum(mat.real - g_model.real, axis=-1) / config.sys.beta

        occ_mean = np.mean(occ_k, axis=(0, 1, 2))
        n_el = 2.0 * np.trace(occ_mean).real
        return n_el, occ_mean, occ_k

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
        mat = iv_bands + mu_bands - hloc[..., None] - smom0[..., None]
        return np.linalg.inv(mat.transpose(2, 0, 1)).transpose(1, 2, 0)

    def _get_g_model_q_mat(self):
        iv_bands, mu_bands = self._get_g_params_local()
        smom0 = self._sigma.smom[0][None, None, None, ...]
        mat = iv_bands[None, None, None] + mu_bands[None, None, None] - self._ek[..., None] - smom0[..., None]
        return np.linalg.inv(mat.transpose(0, 1, 2, 5, 3, 4)).transpose(0, 1, 2, 4, 5, 3)

    def _get_g_params_local(self):
        eye_bands = np.eye(self.n_bands, self.n_bands)
        iv = 1j * MFHelper.vn(self.niv, config.sys.beta)
        iv_bands = iv[None, None, :] * eye_bands[..., None]
        mu_bands = config.sys.mu * eye_bands[:, :, None]
        return iv_bands, mu_bands
