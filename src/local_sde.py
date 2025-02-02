import config

from interaction import LocalInteraction
from local_four_point import LocalFourPoint
from local_greens_function import LocalGreensFunction
from local_self_energy import LocalSelfEnergy
from local_three_point import LocalThreePoint
from matsubara_frequencies import MFHelper, FrequencyShift
from memory_helper import MemoryHelper
from n_point_base import *


def create_gamma_r(gchi_r: LocalFourPoint, gchi0: LocalFourPoint, u_loc: LocalInteraction) -> LocalFourPoint:
    """
    Returns the irreducible vertex gamma_r = (gchi_r)^(-1) - (gchi0)^(-1)
    """
    gamma_loc = config.sys.beta**2 * (~gchi_r - ~(gchi0.cut_niv(config.box.niv)))
    gamma_hh = gamma_loc.concatenate_local_u(u_loc.as_channel(gchi_r.channel, config.sys.beta), config.box.niv_full)
    gamma_copy = deepcopy(gamma_hh)
    gamma_copy[
        ...,
        gamma_hh.niv - config.box.niv : gamma_hh.niv + config.box.niv,
        gamma_hh.niv - config.box.niv : gamma_hh.niv + config.box.niv,
    ] = 0.0

    gamma_lh = (
        gamma_copy[..., gamma_copy.niv - config.box.niv : gamma_copy.niv + config.box.niv, :]
        .transpose(4, 0, 1, 5, 2, 3, 6)
        .reshape(2 * gchi_r.niw + 1, gchi_r.n_bands**2 * 2 * gchi_r.niv, gchi_r.n_bands**2 * 2 * gchi0.niv)
    )
    gamma_hl = (
        gamma_copy[..., :, gamma_copy.niv - config.box.niv : gamma_copy.niv + config.box.niv]
        .transpose(4, 0, 1, 5, 2, 3, 6)
        .reshape(2 * gchi_r.niw + 1, gchi_r.n_bands**2 * 2 * gchi0.niv, gchi_r.n_bands**2 * 2 * gchi_r.niv)
    )
    inner = (
        (~(gamma_copy + config.sys.beta**2 * (~gchi0)))
        .mat.transpose(4, 0, 1, 5, 2, 3, 6)
        .reshape(2 * gchi_r.niw + 1, gchi0.n_bands**2 * 2 * gchi0.niv, gchi_r.n_bands**2 * 2 * gchi0.niv)
    )
    correction = gamma_lh @ inner @ gamma_hl
    compound_index_shape = (gchi_r.n_bands, gchi_r.n_bands, 2 * gchi_r.niv)

    correction = correction.reshape((2 * gchi_r.niw + 1,) + compound_index_shape * 2).transpose(1, 2, 4, 5, 0, 3, 6)

    gamma_hh[
        ...,
        gamma_hh.niv - config.box.niv : gamma_hh.niv + config.box.niv,
        gamma_hh.niv - config.box.niv : gamma_hh.niv + config.box.niv,
    ] = (
        gamma_loc.mat + correction
    )
    return gamma_hh


def create_gamma_0(u_loc: LocalInteraction) -> LocalInteraction:
    """
    Returns the zero-th order vertex gamma_0 = U_{abcd} - U_{abdc}.
    """
    return u_loc - u_loc.permute_orbitals("abcd->adcb")


def create_generalized_chi(g2: LocalFourPoint, g_loc: LocalGreensFunction) -> LocalFourPoint:
    """
    Returns the generalized susceptibility gchi_{r;lmm'l'}^{wvv'}:1/eV^3 = beta:1/eV * (G2_{r;lmm'l'}^{wvv'}:1/eV^2 - 2 * G_{ll'}^{v} G_{m'm}^{v}:1/eV^2 delta_dens delta_w0)
    """
    chi = config.sys.beta * g2

    if g2.channel == Channel.DENS:
        wn = MFHelper.wn(g2.niw)
        chi0_mat = _get_ggv_mat(g_loc, niv_slice=g2.niv)[:, :, :, :, np.newaxis, ...]
        chi[:, :, :, :, wn == 0, ...] -= 2.0 * chi0_mat

    return chi


def _get_ggv_mat(g_loc: LocalGreensFunction, niv_slice: int = -1) -> np.ndarray:
    """
    Returns G_{ll'}^{v}:1/eV * G_{m'm}^{v}:1/eV
    """
    if niv_slice == -1:
        niv_slice = g_loc.niv
    g_loc_slice_mat = g_loc.mat[..., g_loc.niv - niv_slice : g_loc.niv + niv_slice]
    g_left_mat = g_loc_slice_mat[:, None, None, :, :, None] * np.eye(g_loc.n_bands)[None, :, :, None, None, None]
    g_right_mat = (
        np.swapaxes(g_loc_slice_mat, 0, 1)[None, :, :, None, None, :]
        * np.eye(g_loc.n_bands)[:, None, None, :, None, None]
    )
    return g_left_mat * g_right_mat


def create_generalized_chi0(
    g_loc: LocalGreensFunction, frequency_shift: FrequencyShift = FrequencyShift.MINUS
) -> LocalFourPoint:
    """
    Returns the generalized bare susceptibility gchi0_{lmm'l'}^{wvv}:1/eV^3 = -beta:1/eV * G_{ll'}^{v}:1/eV * G_{m'm}^{v-w}:1/eV
    """
    gchi0_mat = np.empty((g_loc.n_bands,) * 4 + (2 * config.box.niw + 1, 2 * config.box.niv_full), dtype=np.complex128)

    wn = MFHelper.wn(config.box.niw)
    for index, current_wn in enumerate(wn):
        iws, iws2 = MFHelper.get_frequency_shift(current_wn, frequency_shift)

        # this is basically the same as _get_ggv_mat, but I don't know how to avoid the code duplication in a smart way
        g_left_mat = (
            g_loc.mat[..., g_loc.niv - config.box.niv_full + iws : g_loc.niv + config.box.niv_full + iws][
                :, None, None, :, :
            ]
            * np.eye(g_loc.n_bands)[None, :, :, None, None]
        )
        g_right_mat = (
            np.swapaxes(g_loc.mat, 0, 1)[
                ..., g_loc.niv - config.box.niv_full + iws2 : g_loc.niv + config.box.niv_full + iws2
            ][None, :, :, None, :]
            * np.eye(g_loc.n_bands)[:, None, None, :, None]
        )

        gchi0_mat[..., index, :] = -config.sys.beta * g_left_mat * g_right_mat

    return LocalFourPoint(gchi0_mat, Channel.NONE, 1, 1)


def create_auxiliary_chi(gamma_r: LocalFourPoint, gchi_0: LocalFourPoint, u_loc: LocalInteraction) -> LocalFourPoint:
    """
    Returns the auxiliary susceptibility gchi_aux_{r;lmm'l'} = ((gchi_{0;lmm'l'})^(-1) + gamma_{r;lmm'l'}-(u_{lmm'l'} - u_{ll'm'm})/beta^2)^(-1). See Eq. (3.68) in Paul Worm's thesis.
    """
    gamma_0 = create_gamma_0(u_loc)
    return ~(~gchi_0 + (gamma_r - gamma_0) / config.sys.beta**2)


def create_physical_chi(gchi_r: LocalFourPoint) -> LocalFourPoint:
    """
    Returns the physical susceptibility chi_phys_{r;ll'}^{w} = 1/beta^2 [sum_v sum_{mm'} gchi_{r;lmm'l'}]. See Eq. (3.51) in Paul Worm's thesis.
    """
    return gchi_r.contract_legs(config.sys.beta)


def create_vrg(gchi_aux: LocalFourPoint, gchi0: LocalFourPoint) -> LocalThreePoint:
    """
    Returns the three-leg vertex vrg = beta * (gchi0)^(-1) * (sum_v gchi_aux). sum_v is performed over the fermionic
    frequency dimensions and includes a factor 1/beta. See Eq. (3.71) in Paul Worm's thesis.
    """
    gchi_aux_sum = gchi_aux.sum_over_fermionic_dimensions(config.sys.beta, axis=(-1,))
    vrg_mat = (
        config.sys.beta * ((~gchi0) @ gchi_aux_sum).compress_last_two_frequency_dimensions_to_single_dimension().mat
    )
    return LocalThreePoint(vrg_mat, gchi_aux.channel, 1, 1, gchi_aux.full_niw_range, gchi_aux.full_niv_range)


def get_self_energy(
    vrg_dens: LocalThreePoint,
    gchi_dens: LocalFourPoint,
    g_loc: LocalGreensFunction,
    u_loc: LocalInteraction,
) -> LocalSelfEnergy:
    """
    Performs the local self-energy calculation using the Schwinger-Dyson equation, see Paul Worm's thesis, Eq. (3.70) and Anna Galler's Thesis, P. 76 ff.
    """
    n_bands = vrg_dens.n_bands

    # 1=i, 2=j, 3=k, 4=l, 7=o, 8=p
    g_1 = MFHelper.wn_slices_gen(g_loc.mat, vrg_dens.niv, vrg_dens.niw)
    deltas = np.einsum("io,lp->iolp", np.eye(n_bands), np.eye(n_bands))

    gchi_dens = gchi_dens.sum_over_fermionic_dimensions(config.sys.beta, axis=(-1, -2))

    gamma_0_dens = create_gamma_0(u_loc)
    inner_sum = np.einsum("abcd,ilbawv,dcpow->ilpowv", gamma_0_dens.mat, vrg_dens.mat, gchi_dens.mat)
    inner = deltas[..., np.newaxis, np.newaxis] - vrg_dens.mat + inner_sum

    self_energy_mat = 1.0 / config.sys.beta * np.einsum("kjop,ilpowv,lkwv->ijv", u_loc.mat, inner, g_1)

    u_loc_hartree = 2 * u_loc - u_loc.permute_orbitals("abcd->adcb")
    hartree = np.einsum("abcd,dc->ab", u_loc_hartree.mat, config.sys.occ)
    hartree_dmft = np.einsum("abcd,dc->ab", u_loc_hartree.mat, config.sys.occ_dmft)

    self_energy_mat += hartree_dmft[..., np.newaxis]

    return LocalSelfEnergy(self_energy_mat)


def perform_local_schwinger_dyson(
    g_loc: LocalGreensFunction, g2_dens: LocalFourPoint, g2_magn: LocalFourPoint, u_loc: LocalInteraction
) -> (LocalSelfEnergy, LocalFourPoint, LocalFourPoint):
    """
    Performs the local Schwinger-Dyson equation calculation for the local self-energy.
    Includes the calculation of the three-leg vertices, (auxiliary/bare/physical) susceptibilities and the irreducible vertices.
    """
    gchi_dens = create_generalized_chi(g2_dens, g_loc)
    MemoryHelper.delete(g2_dens)
    gchi_magn = create_generalized_chi(g2_magn, g_loc)
    MemoryHelper.delete(g2_magn)

    if config.output.do_plotting:
        gchi_dens.plot(omega=0, name=f"Gchi_dens", output_dir=config.output.output_path)
        gchi_magn.plot(omega=0, name=f"Gchi_magn", output_dir=config.output.output_path)

    gchi0 = create_generalized_chi0(g_loc)

    gamma_dens = create_gamma_r(gchi_dens, gchi0, u_loc)
    gchi_aux_dens = create_auxiliary_chi(gamma_dens, gchi0, u_loc)
    vrg_dens = create_vrg(gchi_aux_dens, gchi0)
    MemoryHelper.delete(gchi_aux_dens)

    gamma_magn = create_gamma_r(gchi_magn, gchi0, u_loc)
    gchi_aux_magn = create_auxiliary_chi(gamma_magn, gchi0, u_loc)
    vrg_magn = create_vrg(gchi_aux_magn, gchi0)
    MemoryHelper.delete(gchi0, gchi_aux_magn)

    sigma = get_self_energy(vrg_dens, gchi_dens, g_loc, u_loc)

    chi_dens_physical = create_physical_chi(gchi_dens)
    MemoryHelper.delete(gchi_dens)
    chi_magn_physical = create_physical_chi(gchi_magn)
    MemoryHelper.delete(gchi_magn)

    return gamma_dens, gamma_magn, chi_dens_physical, chi_magn_physical, vrg_dens, vrg_magn, sigma
