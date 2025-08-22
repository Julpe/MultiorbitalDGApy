import scdga.config as config
from scdga.bubble_gen import BubbleGenerator
from scdga.greens_function import GreensFunction
from scdga.interaction import LocalInteraction
from scdga.local_four_point import LocalFourPoint
from scdga.matsubara_frequencies import MFHelper
from scdga.n_point_base import *
from scdga.self_energy import SelfEnergy


def create_generalized_chi(g2: LocalFourPoint, g_loc: GreensFunction) -> LocalFourPoint:
    r"""
    Returns the generalized susceptibility, see also Eq. (3.31) in my master's thesis.
    :math:`\chi_{r;abcd}^{wvv'} = \beta G_{r;abcd}^{(2);wvv'} - 2 \delta_{rd} \delta_{w0} G_{ab}^{v} G_{cd}^{v'})`
    """
    chi = config.sys.beta * g2

    if g2.channel == SpinChannel.DENS and g2.frequency_notation == FrequencyNotation.PH:
        wn = MFHelper.wn(config.box.niw_core)
        ggv_mat = _get_ggv_mat(g_loc, niv_slice=config.box.niv_core)[:, :, :, :, None, ...]
        chi[:, :, :, :, wn == 0, ...] -= 2.0 * config.sys.beta * ggv_mat

    return chi


def _get_ggv_mat(g_loc: GreensFunction, niv_slice: int = -1) -> np.ndarray:
    r"""
    Returns the product of two Green's functions which is needed to retrieve the general susceptibility in the density
    channel: :math:`B_{0;abcd}^{vv'} = G_{ab}^{v} G_{cd}^{v'}`, see also Eq. (3.31) in my master's thesis.
    """
    if niv_slice == -1:
        niv_slice = g_loc.niv

    g_loc_slice_mat = g_loc.mat[..., g_loc.niv - niv_slice : g_loc.niv + niv_slice]

    g_left_mat = g_loc_slice_mat[:, :, None, None, :, None]
    g_right_mat = np.swapaxes(g_loc_slice_mat, 0, 1)[None, None, :, :, None, :]
    return g_left_mat * g_right_mat


def create_gamma_r(gchi_r: LocalFourPoint, gchi0_inv: LocalFourPoint) -> LocalFourPoint:
    r"""
    Returns the ph-irreducible vertex
    :math:`\Gamma_{r;abcd}^{wvv'} = \beta^2 * [(\chi_{r;abcd}^{wvv'})^{-1} - (\chi_{0;abcd}^{wv})^{-1}]`.
    """
    return config.sys.beta**2 * (gchi_r.invert() - gchi0_inv)


def create_gamma_r_with_shell_correction(
    gchi_r: LocalFourPoint, gchi0: LocalFourPoint, u_loc: LocalInteraction
) -> LocalFourPoint:
    r"""
    Calculates the irreducible vertex with the shell correction as described by Motoharu Kitatani
    et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d. More specifically equations A.4 to A.8.
    The irreducible vertex has an additional factor of :math:`1/\beta^2` compared to DGApy. This is also described in
    my master's thesis, Sec. 3.7.2.
    """
    chi_tilde_shell = (gchi0.invert() + 1.0 / config.sys.beta**2 * u_loc.as_channel(gchi_r.channel)).invert()
    chi_tilde_core_inv = chi_tilde_shell.cut_niv(config.box.niv_core).invert()

    gchi_r.invert().save(output_dir=config.output.output_path, name=f"gchi_{gchi_r.channel.value}_inverted")
    chi_tilde_core_inv.extend_vn_to_diagonal().save(output_dir=config.output.output_path, name=f"chi_tilde_core_inv")

    return config.sys.beta**2 * (gchi_r.invert() - chi_tilde_core_inv) + u_loc.as_channel(gchi_r.channel)


def create_auxiliary_chi(gamma_r: LocalFourPoint, gchi0_inv: LocalFourPoint, u_loc: LocalInteraction) -> LocalFourPoint:
    r"""
    Returns the auxiliary susceptibility, see Eq. (3.60) in my master's thesis.
    :math:`\chi^{*;wvv'}_{r;abcd} = ((\chi_{0;abcd}^{wv})^{-1} + (\Gamma_{r;abcd}^{wvv'}-U_{r;abcd})/\beta^2)^{-1}`.
    """
    return (gchi0_inv + (gamma_r - u_loc.as_channel(gamma_r.channel)) / config.sys.beta**2).invert()


def create_generalized_chi_with_shell_correction(
    gchi_aux_sum: LocalFourPoint, gchi0: LocalFourPoint, u_loc: LocalInteraction
) -> LocalFourPoint:
    """
    Calculates the generalized susceptibility with the shell correction as described by
    Motoharu Kitatani et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d. Eq. A.15. This is also
    described in my master's thesis, Sec. 3.7.2.
    """
    gchi0_full_sum = 1.0 / config.sys.beta * gchi0.sum_over_all_vn(config.sys.beta)
    gchi0_core_sum = 1.0 / config.sys.beta * gchi0.cut_niv(config.box.niv_core).sum_over_all_vn(config.sys.beta)
    return ((gchi_aux_sum + gchi0_full_sum - gchi0_core_sum).invert() + u_loc.as_channel(gchi_aux_sum.channel)).invert()


def create_full_vertex_from_gamma(gamma_r, gchi0, u_loc):
    """
    Returns the local full vertex in the niv_full region. F = Gamma [1 + X_0 Gamma]^(-1)
    """
    gamma_urange = gamma_r.pad_with_u(u_loc.as_channel(gamma_r.channel), config.box.niv_full)
    return gamma_urange @ (
        LocalFourPoint.identity_like(gamma_urange) + 1.0 / config.sys.beta**2 * gchi0 @ gamma_urange
    ).invert(False)


def create_full_vertex(gchi_r: LocalFourPoint, gchi0_inv: LocalFourPoint) -> LocalFourPoint:
    r"""
    Returns the local full vertex in the niv_core region, see Eq. (3.58) in my master's thesis.
    :math:`F_{r;abcd}^{wvv'} = -\beta^2 * (\chi_{0;abcd}^{-1} - \chi_{0;abef}^{-1} \chi_{r;fehg} \chi_{0;ghcd}^{-1})`.
    """
    return config.sys.beta**2 * (gchi0_inv - gchi0_inv @ gchi_r @ gchi0_inv)


def create_vrg(gchi_aux: LocalFourPoint, gchi0_inv: LocalFourPoint) -> LocalFourPoint:
    r"""
    Returns the three-leg vertex, see Eq. (3.63) in my master's thesis.
    :math:`\gamma_{r;abcd}^{wv} = \beta * (\chi^{wvv}_{0;ablm})^{-1} * (\sum_{v'} \chi^{*;wvv'}_{r;mlcd})`.
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
    Calculates the local irreducible vertex, summed generalized susceptibility, three-leg vertex, full vertex and the
    generalized susceptibility for either density or magnetic channel. Employs explicit asymptotics as proposed by
    Motoharu Kitatani et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d for the local irreducible vertex.
    Attention: This method will delete g2_r in the process of executing.
    """
    logger = config.logger

    gchi_r = create_generalized_chi(g2_r, g_loc)
    del g2_r
    logger.log_info(f"Local generalized susceptibility chi^wvv' ({gchi_r.channel.value}) done.")

    gamma_r = create_gamma_r_with_shell_correction(gchi_r, gchi0, u_loc)

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
    Performs the local self-energy calculation using the Schwinger-Dyson equation, i.e. the local variant of Eq. (3.64)
    in my master's thesis. This is done to verify the implementation of the Schwinger-Dyson equation with the three-leg
    vertex and the local susceptibility against the DMFT self-energy. Note that there will never be a perfect match due
    to the sampling method of w2dynamics and the stochastic nature of the CTQMC solver. Nevertheless, the results should
    be very close. For more details, see also Paul Worm's PhD thesis, Eq. (3.70) and Anna Galler's PhD Thesis, P. 76 ff.
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
    Performs the local Schwinger-Dyson equation calculation for the local self-energy for sanity checks against the
    DMFT self-energy. Includes the calculation of the local three-leg and full vertices, (auxiliary/bare/physical)
    susceptibilities and the irreducible vertices for both the density and magnetic channel. Employs explicit
    asymptotics as proposed by Motoharu Kitatani et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d.
    """
    gchi0 = BubbleGenerator.create_generalized_chi0(g_loc, config.box.niw_core, config.box.niv_full)

    if config.eliashberg.perform_eliashberg:
        gchi0.save(name="gchi0_loc", output_dir=config.output.output_path)

    gchi0_inv_core = gchi0.cut_niv(config.box.niv_core).invert().take_vn_diagonal()

    gamma_d, gchi_d_sum, vrg_d, f_d, gchi_d = create_vertex_functions(g2_dens, gchi0, gchi0_inv_core, g_loc, u_loc)
    gamma_m, gchi_m_sum, vrg_m, f_m, gchi_m = create_vertex_functions(g2_magn, gchi0, gchi0_inv_core, g_loc, u_loc)

    sigma_loc = get_loc_self_energy_vrg(vrg_d, vrg_m, gchi_d_sum, gchi_m_sum, g_loc, u_loc)
    return gamma_d, gamma_m, gchi_d_sum, gchi_m_sum, vrg_d, vrg_m, f_d, f_m, gchi_d, gchi_m, sigma_loc
