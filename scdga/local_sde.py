import scdga.config as config
from scdga.bubble_gen import BubbleGenerator
from scdga.debug_util import count_nonzero_orbital_entries
from scdga.greens_function import GreensFunction
from scdga.interaction import LocalInteraction
from scdga.local_four_point import LocalFourPoint
from scdga.matsubara_frequencies import MFHelper
from scdga.n_point_base import *
from scdga.self_energy import SelfEnergy


def create_generalized_chi(g2: LocalFourPoint, g_loc: GreensFunction) -> LocalFourPoint:
    r"""
    Returns the generalized susceptibility
    .. math:: \chi_{r;lmm'l'}^{wvv'} = \beta (G_{r;lmm'l'}^{(2);wvv'} - 2 \delta_{rd} \delta_{w0} G_{ll'}^{v} G_{m'm}^{v'})
    """
    chi = config.sys.beta * g2

    if g2.channel == SpinChannel.DENS and g2.frequency_notation == FrequencyNotation.PH:
        wn = MFHelper.wn(config.box.niw_core)
        ggv_mat = _get_ggv_mat(g_loc, niv_slice=config.box.niv_core)[:, :, :, :, None, ...]
        chi[:, :, :, :, wn == 0, ...] -= 2.0 * config.sys.beta * ggv_mat

    return chi


def _get_ggv_mat(g_loc: GreensFunction, niv_slice: int = -1) -> np.ndarray:
    r"""
    Returns the product of two Green's functions
    .. math:: B_{0;lmm'l'}^{vv'} = G_{lm}^{v} G_{m'l'}^{v'}.
    """
    if niv_slice == -1:
        niv_slice = g_loc.niv
    g_loc_slice_mat = g_loc.mat[..., g_loc.niv - niv_slice : g_loc.niv + niv_slice]
    return g_loc_slice_mat[:, :, None, None, :, None] * g_loc_slice_mat[None, None, :, :, None, :]


def create_gamma_r(gchi_r: LocalFourPoint, gchi0_inv: LocalFourPoint) -> LocalFourPoint:
    r"""
    Returns the irreducible vertex
    .. math:: \Gamma_{r;lmm'l'}^{wvv'} = \beta^2 * [(\chi_{r;lmm'l'}^{wvv'})^{-1} - (\chi_{0;lmm'l'}^{wv})^{-1}]
    """
    return config.sys.beta**2 * (gchi_r.invert() - gchi0_inv)


def create_gamma_r_with_shell_correction(
    gchi_r: LocalFourPoint, gchi0: LocalFourPoint, u_loc: LocalInteraction
) -> LocalFourPoint:
    """
    Calculates the irreducible vertex with the shell correction as described
    by Motoharu Kitatani et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d.
    More specifically equations A.4 to A.8. Has an additional factor of beta^2 compared to Paul Worm's code.
    """
    chi_tilde_shell = (gchi0.invert() + 1.0 / config.sys.beta**2 * u_loc.as_channel(gchi_r.channel)).invert()
    chi_tilde_core_inv = chi_tilde_shell.cut_niv(config.box.niv_core).invert()

    count_nonzero_orbital_entries(gchi_r.invert(), "gchi_r inv")
    count_nonzero_orbital_entries(chi_tilde_core_inv, "chi_tilde_core_inv")
    count_nonzero_orbital_entries(gchi_r.invert() - chi_tilde_core_inv, "difference")

    gchi_r.invert().save(output_dir=config.output.output_path, name=f"gchi_{gchi_r.channel.value}_inverted")
    chi_tilde_core_inv.extend_vn_to_diagonal().save(output_dir=config.output.output_path, name=f"chi_tilde_core_inv")

    return config.sys.beta**2 * (gchi_r.invert() - chi_tilde_core_inv) + u_loc.as_channel(gchi_r.channel)


def create_auxiliary_chi(gamma_r: LocalFourPoint, gchi0_inv: LocalFourPoint, u_loc: LocalInteraction) -> LocalFourPoint:
    r"""
    Returns the auxiliary susceptibility
    .. math:: \chi^{*;wvv'}_{r;lmm'l'} = ((\chi_{0;lmm'l'}^{wv})^{-1} + (\Gamma_{r;lmm'l'}^{wvv'}-U_{r;lmm'l'})/\beta^2)^{-1}.
    See Eq. (3.68) in Paul Worm's thesis.
    """
    return (gchi0_inv + (gamma_r - u_loc.as_channel(gamma_r.channel)) / config.sys.beta**2).invert()


def create_generalized_chi_with_shell_correction(
    gchi_aux_sum: LocalFourPoint, gchi0: LocalFourPoint, u_loc: LocalInteraction
) -> LocalFourPoint:
    """
    Calculates the generalized susceptibility with the shell correction as described by
    Motoharu Kitatani et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d. Eq. A.15
    """
    gchi0_full_sum = 1.0 / config.sys.beta * gchi0.sum_over_all_vn(config.sys.beta)
    gchi0_core_sum = 1.0 / config.sys.beta * gchi0.cut_niv(config.box.niv_core).sum_over_all_vn(config.sys.beta)
    return ((gchi_aux_sum + gchi0_full_sum - gchi0_core_sum).invert() + u_loc.as_channel(gchi_aux_sum.channel)).invert()


def create_full_vertex_from_gamma(gamma_r, gchi0, u_loc):
    """
    Returns the full vertex in the niv_full region. F = Gamma [1 + X_0 Gamma]^(-1)
    """
    gamma_urange = gamma_r.pad_with_u(u_loc.as_channel(gamma_r.channel), config.box.niv_full)
    return (
        gamma_urange
        @ (LocalFourPoint.identity_like(gamma_urange) + 1.0 / config.sys.beta**2 * gchi0 @ gamma_urange).invert()
    )


def create_full_vertex(gchi_r: LocalFourPoint, gchi0_inv: LocalFourPoint) -> LocalFourPoint:
    r"""
    Returns the full vertex
    .. math:: F_{r;abcd}^{wvv'} = -\beta^2 * (\chi_{0;abcd}^{-1} - \chi_{0;abef}^{-1} \chi_{r;fehg} \chi_{0;ghcd}^{-1})
    See Eq. (3.64) in Paul Worm's thesis.
    """
    return config.sys.beta**2 * (gchi0_inv - gchi0_inv @ gchi_r @ gchi0_inv)


def create_vrg(gchi_aux: LocalFourPoint, gchi0_inv: LocalFourPoint) -> LocalFourPoint:
    r"""
    Returns the three-leg vertex
    .. math:: \gamma_{r;lmm'l'}^{wv} = \beta * (\chi^{wvv}_{0;lmab})^{-1} * (\sum_{v'} \chi^{*;wvv'}_{r;bam'l'}).
    See Eq. (3.71) in Paul Worm's thesis.
    """
    gchi_aux_sum = gchi_aux.sum_over_vn(config.sys.beta, axis=(-1,))
    return config.sys.beta * (gchi0_inv @ gchi_aux_sum)


def create_vertex_functions(
    g2_r: LocalFourPoint,
    gchi0: LocalFourPoint,
    gchi0_inv_core: LocalFourPoint,
    g_loc: GreensFunction,
    u_loc: LocalInteraction,
) -> tuple[LocalFourPoint, LocalFourPoint, LocalFourPoint, LocalFourPoint, LocalFourPoint]:
    """
    Calculates the three-leg vertex, the auxiliary susceptibility and the irreducible vertex. Employs explicit
    asymptotics as proposed by Motoharu Kitatani et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d.
    Attention: This method will delete g2_r in the process of executing.
    """
    logger = config.logger

    gchi_r = create_generalized_chi(g2_r, g_loc)
    del g2_r
    logger.log_info(f"Local generalized susceptibility chi^wvv' ({gchi_r.channel.value}) done.")

    gamma_r = create_gamma_r_with_shell_correction(gchi_r, gchi0, u_loc)

    """
    for i, j, k, l in np.ndindex(gamma_r.mat.shape[:4]):
        if (i == 0 and j == 0 and k == 0 and l == 0) or (i == 1 and j == 1 and k == 1 and l == 1):
            continue
        gamma_r[i, j, k, l] = 0.0
    """

    gchi0 = gchi0.take_vn_diagonal()
    logger.log_info(f"Local irreducible vertex Gamma^wvv' ({gamma_r.channel.value}) with asymptotic correction done.")

    f_r = create_full_vertex_from_gamma(gamma_r, gchi0, u_loc)
    logger.log_info(f"Local full vertex F^wvv' ({f_r.channel.value}) done.")

    gchi_r_aux = create_auxiliary_chi(gamma_r, gchi0_inv_core, u_loc)
    logger.log_info(f"Local auxiliary susceptibility chi^*wvv' ({gchi_r_aux.channel.value}) done.")

    vrg_r = create_vrg(gchi_r_aux, gchi0_inv_core)
    logger.log_info(f"Local three-leg vertex gamma^wv ({vrg_r.channel.value}) done.")

    gchi_r_aux_sum = gchi_r_aux.sum_over_all_vn(config.sys.beta)
    del gchi_r_aux

    gchi_r_aux_sum = create_generalized_chi_with_shell_correction(gchi_r_aux_sum, gchi0, u_loc)
    logger.log_info(f"Updated local susceptibility chi^w ({gchi_r_aux_sum.channel.value}) with asymptotic correction.")

    return gamma_r, gchi_r_aux_sum, vrg_r, f_r, gchi_r


def get_loc_self_energy_vrg(
    vrg_dens: LocalFourPoint,
    vrg_magn: LocalFourPoint,
    gchi_dens_sum: LocalFourPoint,
    gchi_magn_sum: LocalFourPoint,
    g_loc: GreensFunction,
    u_loc: LocalInteraction,
) -> SelfEnergy:
    """
    Performs the local self-energy calculation using the Schwinger-Dyson equation,
    see Paul Worm's thesis, Eq. (3.70) and Anna Galler's Thesis, P. 76 ff.
    """
    # 1=i, 2=j, 3=k, 4=l, 7=o, 8=p
    g_wv = g_loc.get_g_wv(MFHelper.wn(config.box.niw_core), config.box.niv_core)
    inner = vrg_dens - vrg_dens @ u_loc.as_channel(SpinChannel.DENS) @ gchi_dens_sum
    inner -= vrg_magn - vrg_magn @ u_loc.as_channel(SpinChannel.MAGN) @ gchi_magn_sum
    inner = 0.5 * inner.to_full_niw_range()
    sigma_sum = -1.0 / config.sys.beta * u_loc.times("kjop,ilpowv,lkwv->ijv", inner, g_wv)
    hartree_fock = u_loc.as_channel(SpinChannel.DENS).times("abcd,dc->ab", config.sys.occ)[..., None]

    return SelfEnergy((hartree_fock + sigma_sum)[None, None, None, ...])


def perform_local_schwinger_dyson(
    g_loc: GreensFunction, g2_dens: LocalFourPoint, g2_magn: LocalFourPoint, u_loc: LocalInteraction
):
    """
    Performs the local Schwinger-Dyson equation calculation for the local (DMFT) self-energy for sanity checks.
    Includes the calculation of the three-leg and full vertices, (auxiliary/bare/physical) susceptibilities
    and the irreducible vertices. Employs explicit asymptotics as proposed by
    Motoharu Kitatani et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d.
    """
    gchi0 = BubbleGenerator.create_generalized_chi0(g_loc, config.box.niw_core, config.box.niv_full)

    if config.eliashberg.perform_eliashberg:
        gchi0.save(name="gchi0_loc", output_dir=config.output.output_path)

    gchi0_inv_core = gchi0.cut_niv(config.box.niv_core).invert().take_vn_diagonal()

    count_nonzero_orbital_entries(gchi0, "gchi0")
    count_nonzero_orbital_entries(gchi0_inv_core, "gchi0_inv")

    gamma_d, gchi_d_sum, vrg_d, f_d, gchi_d = create_vertex_functions(g2_dens, gchi0, gchi0_inv_core, g_loc, u_loc)
    gamma_m, gchi_m_sum, vrg_m, f_m, gchi_m = create_vertex_functions(g2_magn, gchi0, gchi0_inv_core, g_loc, u_loc)

    sigma_loc = get_loc_self_energy_vrg(vrg_d, vrg_m, gchi_d_sum, gchi_m_sum, g_loc, u_loc)
    return gamma_d, gamma_m, gchi_d_sum, gchi_m_sum, vrg_d, vrg_m, f_d, f_m, gchi_d, gchi_m, sigma_loc


# ----------------------------------------------- AbinitioDGA algorithms -----------------------------------------------


def get_loc_self_energy_gamma_abinitio_dga(
    gamma_dens: LocalFourPoint, u_loc: LocalInteraction, g_loc: GreensFunction
) -> SelfEnergy:
    r"""
    Returns the local self-energy with the three-leg gamma from AbinitioDGA
    .. math:: \Sigma_{ij}^{v} = -1/\beta \sum_w [ U_{iabc} * \gamma_{cbdj}^{wv} * G_{ad}^{w-v} ]
    """
    g_wv = g_loc.get_g_wv(MFHelper.wn(config.box.niw_core), config.box.niv_core)
    sigma = -1.0 / config.sys.beta * u_loc.times("iabc,cbdjwv,adwv->ijv", gamma_dens, g_wv)
    hartree = u_loc.as_channel(SpinChannel.DENS).times("abcd,dc->ab", config.sys.occ)[..., None]
    return SelfEnergy(sigma + hartree)


def perform_local_schwinger_dyson_abinitio_dga(
    g_loc: GreensFunction,
    g2_dens: LocalFourPoint,
    g2_magn: LocalFourPoint,
    u_loc: LocalInteraction,
):
    """
    ATTENTION: THIS IS THE ABINITODGA ROUTINE!
    Performs the local Schwinger-Dyson equation calculation for the local (DMFT) self-energy for sanity checks.
    """
    logger = config.logger

    gchi_dens_loc = create_generalized_chi(g2_dens, g_loc)
    logger.log_info("Generalized susceptibility chi^wvv' (dens) done.")
    del g2_dens
    gchi_magn_loc = create_generalized_chi(g2_magn, g_loc)
    logger.log_info("Generalized susceptibility chi^wvv' (magn) done.")
    del g2_magn

    gchi0_loc_full = BubbleGenerator.create_generalized_chi0(g_loc, config.box.niw_core, config.box.niv_full)
    logger.log_info("Local bare susceptibility chi_0^wv done.")
    gchi0_core = gchi0_loc_full.cut_niv(config.box.niv_core)

    # 1 + chi0 * F_r = gchi_r * (chi0)^(-1) = 1 + gamma_r or
    # F_r = -beta^2 * [chi0^(-1) - chi0^(-1) chi_r chi0^(-1)]
    # gamma_r is NOT the irreducible vertex in channel r but rather the three-point vertex from AbinitioDGA
    gchi0_inv_core = gchi0_core.invert()
    f_dens_loc = -config.sys.beta**2 * (gchi0_inv_core - gchi0_inv_core @ gchi_dens_loc @ gchi0_inv_core)
    logger.log_info("Local full vertex F^wvv' (dens) done.")
    f_magn_loc = -config.sys.beta**2 * (gchi0_inv_core - gchi0_inv_core @ gchi_magn_loc @ gchi0_inv_core)
    logger.log_info("Local full vertex F^wvv' (magn) done.")
    del gchi0_inv_core

    # f_dens_loc_with_asympt = create_asympt_f(gchi_dens_loc, gchi_magn_loc, gchi_ud_pp_loc_sum, u_loc)

    # in most equations we need 1 + gamma_r so we add it here
    one = LocalFourPoint.identity(config.sys.n_bands, config.box.niw_core, config.box.niv_full, 1)
    gamma_dens_loc = 1.0 / config.sys.beta * (gchi0_core @ f_dens_loc).sum_over_vn(config.sys.beta, axis=(-2,))
    one_plus_gamma_dens_loc = one + gamma_dens_loc
    logger.log_info("Local three-leg vertex gamma^wv (dens) done.")

    gamma_magn_loc = 1.0 / config.sys.beta * (gchi0_core @ f_magn_loc).sum_over_vn(config.sys.beta, axis=(-2,))
    one_plus_gamma_magn_loc = one + gamma_magn_loc
    logger.log_info("Local three-leg vertex gamma^wv (magn) done.")
    del gchi0_core, gamma_magn_loc

    sigma_loc = get_loc_self_energy_gamma_abinitio_dga(gamma_dens_loc, u_loc, g_loc)
    logger.log_info("Local self-energy done.")
    del gamma_dens_loc

    return (
        gchi_dens_loc,
        gchi_magn_loc,
        gchi0_loc_full,
        one_plus_gamma_dens_loc,
        one_plus_gamma_magn_loc,
        f_dens_loc,
        f_magn_loc,
        sigma_loc,
    )
