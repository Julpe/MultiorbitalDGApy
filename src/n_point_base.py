from abc import ABC
from copy import deepcopy
from enum import Enum

import numpy as np


class Channel(Enum):
    DENS: str = "dens"
    MAGN: str = "magn"
    NONE: str = "none"


class IHaveChannel(ABC):
    """
    Abstract interface for classes that have a channel attribute.
    """

    def __init__(self, channel: Channel = Channel.NONE):
        self._channel = channel

    @property
    def channel(self) -> Channel:
        return self._channel


class IHaveMat(ABC):
    """
    Abstract interface for classes that have a mat attribute. Adds a couple of convenience methods for matrix operations.
    """

    def __init__(self, mat: np.ndarray):
        self._mat = mat.astype(np.complex64)
        self._original_shape = self.mat.shape

    @property
    def mat(self) -> np.ndarray:
        return self._mat

    @mat.setter
    def mat(self, value: np.ndarray) -> None:
        self._mat = value

    @mat.deleter
    def mat(self) -> None:
        del self._mat

    @property
    def current_shape(self) -> tuple:
        """
        Keeps track of the current shape of the underlying matrix.
        """
        return self._mat.shape

    @property
    def original_shape(self) -> tuple:
        """
        Keeps track of the previous shape of the underlying matrix before the reshaping process. E.g., it is needed when
        reshaping it to compound indices the original shape would have been lost otherwise.
        """
        return self._original_shape

    @original_shape.setter
    def original_shape(self, value) -> None:
        self._original_shape = value

    def __mul__(self, other) -> "IHaveMat":
        if not isinstance(other, int | float | complex):
            raise ValueError("Multiplication/division only supported with numbers.")

        copy = deepcopy(self)
        copy.mat *= other
        return copy

    def __rmul__(self, other) -> "IHaveMat":
        return self.__mul__(other)

    def __neg__(self) -> "IHaveMat":
        return self.__mul__(-1.0)

    def __truediv__(self, other) -> "IHaveMat":
        return self.__mul__(1.0 / other)

    def __getitem__(self, item):
        return self.mat[item]

    def __setitem__(self, key, value):
        self.mat[key] = value


class IAmNonLocal(ABC):
    """
    Abstract interface for objects that are momentum dependent.
    """

    def __init__(
        self, nq: tuple[int, int, int], nk: tuple[int, int, int], num_q_dimensions: int, num_k_dimensions: int
    ):
        self._nq = nq
        self._nk = nk

        assert num_q_dimensions in (0, 1), "Only 0 or 1 q momentum dimensions are supported."
        self._num_q_dimensions = num_q_dimensions

        assert num_k_dimensions in (0, 1, 2), "0 - 2 k momentum dimensions are supported."
        self._num_k_dimensions = num_k_dimensions

    @property
    def nq(self) -> tuple[int, int, int]:
        return self._nq

    @property
    def nq_tot(self) -> int:
        return np.prod(self.nq).astype(int)

    @property
    def nk(self) -> tuple[int, int, int]:
        return self._nk

    @property
    def nk_tot(self) -> int:
        return np.prod(self.nk).astype(int)

    @property
    def num_q_dimensions(self) -> int:
        return self._num_q_dimensions

    @property
    def num_k_dimensions(self) -> int:
        return self._num_k_dimensions