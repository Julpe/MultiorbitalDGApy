from enum import Enum

import numpy as np
from multimethod import multimethod


class FrequencyShift(Enum):
    MINUS: str = "minus"
    PLUS: str = "plus"
    CENTER: str = "center"
    NONE: str = "none"


class MFHelper:
    @multimethod
    @staticmethod
    def wn(niw: int, shift: int = 0, return_only_positive: bool = False) -> np.ndarray:
        """
        Returns integer numbers in the interval [-niw, niw]. Additionally, a shift to niw can be applied.
        If return_only_positive is set to True, only positive integers in the interval [0, niw] are returned.
        """
        if return_only_positive:
            return np.arange(shift, niw + shift + 1)
        return np.arange(-niw + shift, niw + shift + 1)

    @multimethod
    @staticmethod
    def wn(niw: int, beta: float, shift: int = 0, return_only_positive: bool = False) -> np.ndarray:
        r"""
        Returns (real) bosonic matsubara frequencies in the interval :math:`[-2\mathrm{niw}*\pi/\beta,+2\mathrm{niw}*\pi/\beta]`.
        Additionally, a shift to niw can be applied. If return_only_positive is set to True, only positive real
        frequencies in the interval [0, 2\mathrm{niw}*\pi/\beta] are returned.
        """
        return np.pi / beta * 2 * MFHelper.wn(niw, shift, return_only_positive)

    @multimethod
    @staticmethod
    def vn(niv: int, shift: int = 0, return_only_positive: bool = False) -> np.ndarray:
        """
        Returns integer numbers in the half-open interval [-niv, niv). Additionally, a shift to niv can be applied.
        If return_only_positive is set to True, only positive integers in the interval [0, niv) are returned.
        """
        if return_only_positive:
            return np.arange(shift, niv + shift)
        return np.arange(-niv + shift, niv + shift)

    @multimethod
    @staticmethod
    def vn(niv: int, beta: float, shift: int = 0, return_only_positive: bool = False) -> np.ndarray:
        r"""
        Returns (real) fermionic matsubara frequencies in the half-open interval
        :math:`[-2(\mathrm{niv}+1)*\pi/\beta,+2(\mathrm{niv}+1)*\pi/\beta)`.
        Additionally, a shift to niv can be applied. If return_only_positive is set to True, only positive real
        frequencies in the interval [0, 2(\mathrm{niv}+1)*\pi/\beta) are returned.
        """
        return np.pi / beta * (2 * MFHelper.vn(niv, shift, return_only_positive) + 1)

    @staticmethod
    def get_frequencies_for_ph_to_pp_channel_conversion(
        niw: int, niv: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        r"""
        Returns the new frequencies :math:`(w', v_1', v_2')` for the conversion of ph to pp notation.
        :math:`F_{pp}[w,v_1,v_2] = F_{ph}[w',v_1',v_2']` where :math:`(w,v_1,v_2) -> (w',v_1',v_2') = (v_1 + v_2 - w, v_1, v_2)`
        """
        niw_pp, niv_pp = niw // 3, min(niw // 3, niv // 3)
        iw, iv, ivp = MFHelper._get_frequencies_for_channel_conversion(niw_pp, niv_pp)
        return niw_pp + iv + ivp - iw, niv_pp + iv, niv_pp + ivp

    @staticmethod
    def get_frequencies_for_ph_to_ph_bar_channel_conversion(
        niw: int, niv: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        r"""
        Returns the new frequencies :math:`(w', v_1', v_2')` for the conversion of ph to ph_bar notation.
        :math:`F_ph_bar[...] = F_ph[w',v_1',v_2']` where :math:`(w,v_1,v_2) -> (w',v_1',v_2') = (v_2-v_1, v_2-w, v_2)`
        """
        niw, niv = niw // 2, min(niw // 2, niv // 2)
        iw, iv, ivp = MFHelper._get_frequencies_for_channel_conversion(niw, niv)
        return niw + ivp - iv, niv + ivp - iw, niv + ivp

    @staticmethod
    def _get_frequencies_for_channel_conversion(niw: int, niv: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Helper method which returns three frequency arrays for the conversion of frequency notation.
        """
        wn, vn = MFHelper.wn(niw), MFHelper.vn(niv)
        return wn[:, None, None], vn[None, :, None], vn[None, None, :]
