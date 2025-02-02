import brillouin_zone as bz
from n_point_base import *
import config


class LocalInteraction(IHaveMat, IHaveChannel):
    def __init__(self, mat: np.ndarray, channel: Channel = Channel.NONE):
        IHaveMat.__init__(self, mat)
        IHaveChannel.__init__(self, channel)

    @property
    def n_bands(self) -> int:
        return self.mat.shape[0]

    def permute_orbitals(self, permutation: str = "ijkl->ijkl") -> "LocalInteraction":
        return LocalInteraction(np.einsum(permutation, self.mat), self.channel)

    def as_channel(self, channel: Channel, beta: float) -> "LocalInteraction":
        if channel == Channel.DENS:
            return 1.0 / beta**2 * (2 * self - self.permute_orbitals("abcd->adcb"))
        elif channel == Channel.MAGN:
            return -1.0 / beta**2 * self.permute_orbitals("abcd->adcb")
        elif channel == Channel.SING:
            return 1.0 / beta**2 * (self + self.permute_orbitals("abcd->adcb"))
        elif channel == Channel.TRIP:
            return 1.0 / beta**2 * (self - self.permute_orbitals("abcd->adcb"))
        else:
            raise ValueError(f"Channel {channel} not supported.")

    def __add__(self, other) -> "LocalInteraction":
        if not isinstance(other, LocalInteraction):
            raise ValueError(f"Addition {type(self)} + {type(other)} not supported.")
        return LocalInteraction(self.mat + other.mat, self.channel)

    def __sub__(self, other) -> "LocalInteraction":
        if not isinstance(other, LocalInteraction):
            raise ValueError(f"Subtraction {type(self)} - {type(other)} not supported.")
        return LocalInteraction(self.mat - other.mat, self.channel)


class NonLocalInteraction(LocalInteraction, IAmNonLocal):
    def __init__(
        self,
        mat: np.ndarray,
        ur_r_grid: np.ndarray,
        ur_r_weights: np.ndarray,
        channel: Channel = Channel.NONE,
    ):
        LocalInteraction.__init__(self, mat, channel)
        IAmNonLocal.__init__(self, config.lattice.nq, config.lattice.nk, 1, 2)
        self._ur_r_grid = ur_r_grid
        self._ur_r_weights = ur_r_weights

    def get_uq(self, q_grid: bz.KGrid) -> "NonLocalInteraction":
        uq = self._convham_4_orbs(q_grid.kmesh.reshape(3, -1))
        n_bands = uq.shape[-1]
        return NonLocalInteraction(uq.reshape(*q_grid.nk + (n_bands,) * 4), self._ur_r_grid, self._ur_r_weights)

    def permute_orbitals(self, permutation: str = "ijkl->ijkl") -> "NonLocalInteraction":
        split = permutation.split("->")
        if len(split) != 2 or len(split[0]) != 4 or len(split[1]) != 4:
            raise ValueError("Invalid permutation.")

        permutation = f"...{split[0]}->...{split[1]}"
        return NonLocalInteraction(np.einsum(permutation, self.mat), self._ur_r_grid, self._ur_r_weights, self.channel)

    def _convham_4_orbs(self, k_mesh: np.ndarray) -> np.ndarray:
        fft_grid = np.exp(1j * np.matmul(self._ur_r_grid, k_mesh)) / self._ur_r_weights[:, None, None, None, None]
        return np.transpose(np.sum(fft_grid * self.mat[..., None], axis=0), axes=(4, 0, 1, 2, 3))

    def __add__(self, other: "NonLocalInteraction") -> "NonLocalInteraction":
        if not isinstance(other, NonLocalInteraction):
            raise ValueError(f"Addition {type(self)} + {type(other)} not supported.")
        if self.channel != other.channel:
            raise ValueError(f"Channels {self.channel} and {other.channel} don't match.")
        return NonLocalInteraction(self.mat + other.mat, self._ur_r_grid, self._ur_r_weights, self.channel)

    def __sub__(self, other: "NonLocalInteraction") -> "NonLocalInteraction":
        if not isinstance(other, NonLocalInteraction):
            raise ValueError(f"Subtraction {type(self)} - {type(other)} not supported.")
        if self.channel != other.channel:
            raise ValueError(f"Channels {self.channel} and {other.channel} don't match.")
        return NonLocalInteraction(self.mat - other.mat, self._ur_r_grid, self._ur_r_weights, self.channel)
