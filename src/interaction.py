import numpy as np

import config
from n_point_base import *


class LocalInteraction(IHaveMat, IHaveChannel):
    r"""
    Class for local interactions
    .. math:: U_{abcd}.
    """

    def __init__(self, mat: np.ndarray, channel: SpinChannel = SpinChannel.NONE):
        IHaveMat.__init__(self, mat)
        IHaveChannel.__init__(self, channel)

    @property
    def n_bands(self) -> int:
        return self.original_shape[0]

    def permute_orbitals(self, permutation: str = "abcd->abcd") -> "LocalInteraction":
        """
        Permutes the orbitals of the object. The permutation string must be given in the einsum notation.
        """
        split = permutation.split("->")
        if len(split) != 2 or len(split[0]) != 4 or len(split[1]) != 4:
            raise ValueError("Invalid permutation.")

        if split[0] == split[1]:
            return self

        return LocalInteraction(np.einsum(permutation, self.mat, optimize=True), self.channel)

    def as_channel(self, channel: SpinChannel) -> "LocalInteraction":
        """
        Returns the spin combination for a given channel.
        """
        copy = deepcopy(self)

        if copy.channel == channel:
            return copy
        elif copy.channel != channel.NONE:
            raise ValueError(f"Cannot transform interaction from channel {copy.channel} to {channel}.")

        copy._channel = channel
        perm: str = "abcd->adcb"
        if channel == SpinChannel.DENS:
            return 2 * copy - copy.permute_orbitals(perm)
        elif channel == SpinChannel.MAGN:
            return -copy.permute_orbitals(perm)
        elif channel == SpinChannel.SING:
            return copy + copy.permute_orbitals(perm)
        elif channel == SpinChannel.TRIP:
            return copy - copy.permute_orbitals(perm)
        else:
            raise ValueError(f"Channel {channel} not supported.")

    def add(self, other) -> "LocalInteraction":
        """
        Adds two local interactions.
        """
        if not isinstance(other, (LocalInteraction, np.ndarray)):
            raise ValueError(f"Operation {type(self)} +/- {type(other)} not supported.")

        if isinstance(other, np.ndarray):
            return NonLocalInteraction(self.mat + other, self.channel)

        return LocalInteraction(
            self.mat + other.mat, self.channel if self.channel != SpinChannel.NONE else other.channel
        )

    def sub(self, other):
        """
        Subtracts two local interactions.
        """
        return self.add(-other)

    def __add__(self, other) -> "LocalInteraction":
        """
        Adds two local interactions.
        """
        return self.add(other)

    def __sub__(self, other) -> "LocalInteraction":
        """
        Subtracts two local interactions.
        """
        return self.sub(other)


class NonLocalInteraction(LocalInteraction, IAmNonLocal):
    r"""
    Class for non-local interactions
    .. math:: V_{abcd}^{q}.
    """

    def __init__(
        self,
        mat: np.ndarray,
        channel: SpinChannel = SpinChannel.NONE,
    ):
        LocalInteraction.__init__(self, mat, channel)
        IAmNonLocal.__init__(self, mat, config.lattice.nq)

    @property
    def n_bands(self) -> int:
        return self.original_shape[1] if self.has_compressed_q_dimension else self.original_shape[3]

    def permute_orbitals(self, permutation: str = "abcd->abcd") -> "NonLocalInteraction":
        """
        Permutes the orbitals of the object. The permutation string must be given in the einsum notation.
        """
        split = permutation.split("->")
        if len(split) != 2 or len(split[0]) != 4 or len(split[1]) != 4:
            raise ValueError("Invalid permutation.")

        if split[0] == split[1]:
            return self

        permutation = f"...{split[0]}->...{split[1]}"
        return NonLocalInteraction(np.einsum(permutation, self.mat, optimize=True), self.channel)

    def as_channel(self, channel: SpinChannel) -> "LocalInteraction":
        """
        Returns the spin combination for a given channel. Note that we only have the non-local ph contribution
        in the ladder DGA equations and the phbar contribution to the spin channels vanishes.
        """
        copy = deepcopy(self)

        if copy.channel == channel:
            return copy
        elif copy.channel != channel.NONE:
            raise ValueError(f"Cannot transform interaction from channel {copy.channel} to {channel}.")

        copy._channel = channel
        if channel == SpinChannel.DENS:
            return 2 * copy
        elif channel == SpinChannel.MAGN:
            return 0 * copy
        elif channel == SpinChannel.SING:
            return copy
        elif channel == SpinChannel.TRIP:
            return copy
        else:
            raise ValueError(f"Channel {channel} not supported.")

    def add(self, other) -> "NonLocalInteraction":
        """
        Adds two (non-)local interactions.
        """
        if not isinstance(other, (LocalInteraction, NonLocalInteraction, np.ndarray)):
            raise ValueError(f"Operation {type(self)} +/- {type(other)} not supported.")

        if isinstance(other, np.ndarray):
            return NonLocalInteraction(self.mat + other, self.channel)

        if isinstance(other, LocalInteraction):
            other = other.mat[None, ...] if self.has_compressed_q_dimension else other.mat[None, None, None, ...]

        return NonLocalInteraction(
            self.mat + other.mat,
            self.channel if self.channel != SpinChannel.NONE else other.channel,
        )

    def sub(self, other):
        """
        Subtracts two (non-)local interactions.
        """
        return self.add(-other)

    def __add__(self, other) -> "NonLocalInteraction":
        """
        Adds two (non-)local interactions.
        """
        return self.add(other)

    def __sub__(self, other) -> "NonLocalInteraction":
        """
        Subtracts two (non-)local interactions.
        """
        return self.sub(other)
