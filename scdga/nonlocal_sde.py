import glob
import os
import re

import mpi4py.MPI as MPI
import numpy as np

import scdga.config as config
import scdga.lambda_correction as lc
from scdga.bubble_gen import BubbleGenerator
from scdga.debug_util import count_nonzero_orbital_entries
from scdga.four_point import FourPoint
from scdga.greens_function import GreensFunction, update_mu
from scdga.interaction import LocalInteraction, Interaction
from scdga.local_four_point import LocalFourPoint
from scdga.matsubara_frequencies import MFHelper
from scdga.mpi_distributor import MpiDistributor
from scdga.n_point_base import SpinChannel
from scdga.self_energy import SelfEnergy


def get_hartree_fock(
    u_loc: LocalInteraction, v_nonloc: Interaction, q_list: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    r"""
    Returns the Hartree-Fock term separately for the local and non-local interaction. Since we are always SU(2)-symmetric,
    the sum over the spins of the first term in Eq. (4.55) in Anna Galler's thesis results in a simple factor of 2.
    .. math:: \Sigma_{HF}^k = 2(U_{abcd} + V^{q=0}_{abcd}) n_{dc} - 1/N_q \sum_q (U_{adcb} + V^{q}_{adcb}) n^{k-q}_{dc}
    where the Hartree-term is given by

    .. math:: \Sigma_{H} = 2(U_{abcd} + V^{q=0}_{abcd}) n_{dc}
    and the Fock-term reads

    .. math:: \Sigma_{F}^k = - 1/N_q \sum_q (U_{adcb} + V^{q}_{adcb}) n^{k-q}_{dc}.
    """
    v_q0 = v_nonloc.find_q((0, 0, 0))
    occ_qk = np.array([np.roll(config.sys.occ_k, [-i for i in q], axis=(0, 1, 2)) for q in q_list])  # [q,k,o1,o2]
    nq_tot, nk_tot = np.prod(config.lattice.nq), np.prod(config.lattice.nk)
    occ_qk = occ_qk.reshape(nq_tot, nk_tot, config.sys.n_bands, config.sys.n_bands)

    hartree = 2 * (u_loc + v_q0).times("qabcd,dc->ab", config.sys.occ)
    fock = -1.0 / nq_tot * (u_loc + v_nonloc).compress_q_dimension().times("qadcb,qkdc->kab", occ_qk)
    return hartree[None, ..., None], fock[..., None]  # [k,o1,o2,v]


def create_auxiliary_chi_r_q(
    gamma_r: LocalFourPoint, gchi0_q_inv: FourPoint, u_loc: LocalInteraction, v_nonloc: Interaction
) -> FourPoint:
    r"""
    Returns the auxiliary susceptibility
    .. math:: \chi^{*;qvv'}_{r;lmm'l'} = ((\chi_{0;lmm'l'}^{qv})^{-1} + (\Gamma_{r;lmm'l'}^{wvv'}-U_{r;lmm'l'}-V_{r;lmm'l'}^q)/\beta^2)^{-1}

    See Eq. (3.68) in Paul Worm's thesis.
    """
    return (
        (gchi0_q_inv + 1.0 / config.sys.beta**2 * gamma_r)
        - 1.0 / config.sys.beta**2 * (v_nonloc.as_channel(gamma_r.channel) + u_loc.as_channel(gamma_r.channel))
    ).invert()


def create_auxiliary_chi_r_q_sum(
    gamma_r: LocalFourPoint,
    gchi0_q: FourPoint,
    gchi0_q_inv: FourPoint,
    u_loc: LocalInteraction,
    v_nonloc: Interaction,
    summands: int = -1,
) -> FourPoint:
    if summands <= 0:
        return create_auxiliary_chi_r_q(gamma_r, gchi0_q_inv, u_loc, v_nonloc)

    factor = gamma_r - v_nonloc.as_channel(gamma_r.channel) - u_loc.as_channel(gamma_r.channel)
    factor *= 1.0 / config.sys.beta**2
    factor = FourPoint(
        factor,
        gamma_r.channel,
        config.lattice.nq,
        1,
        2,
        gamma_r.full_niw_range,
        True,
        v_nonloc.has_compressed_q_dimension,
    )
    factor = factor @ gchi0_q
    bse_sum = gchi0_q
    next_value = gchi0_q
    for _ in range(summands - 1):
        next_value = -factor @ next_value
        bse_sum += next_value
    return bse_sum


def create_vrg_r_q(gchi_aux_q_r: FourPoint, gchi0_q_inv: FourPoint) -> FourPoint:
    r"""
    Returns the three-leg vertex
    .. math:: \gamma_{r;lmm'l'}^{qv} = \beta * (\chi^{qvv}_{0;lmab})^{-1} * (\sum_{v'} \chi^{*;qvv'}_{r;bam'l'}).
    See Eq. (3.71) in Paul Worm's thesis.
    """
    gchi_aux_q_r_sum = gchi_aux_q_r.sum_over_vn(config.sys.beta, axis=(-1,))
    return config.sys.beta * (gchi0_q_inv @ gchi_aux_q_r_sum)


def create_generalized_chi_q_with_shell_correction(
    gchi_aux_q_sum: FourPoint,
    gchi0_q_full_sum: FourPoint,
    gchi0_q_core_sum: FourPoint,
    u_loc: LocalInteraction,
    v_nonloc: Interaction,
) -> FourPoint:
    """
    Calculates the generalized susceptibility with the shell correction as described by
    Motoharu Kitatani et al. 2022 J. Phys. Mater. 5 034005; DOI 10.1088/2515-7639/ac7e6d. Eq. A.15
    """
    return (
        (gchi_aux_q_sum + gchi0_q_full_sum - gchi0_q_core_sum).invert()
        + (u_loc.as_channel(gchi_aux_q_sum.channel) + v_nonloc.as_channel(gchi_aux_q_sum.channel))
    ).invert()


def calculate_sigma_dc_kernel(f_1dens_3magn: LocalFourPoint, gchi0_q: FourPoint, u_loc: LocalInteraction) -> FourPoint:
    """
    Returns the double-counting kernel for the self-energy calculation.
    """
    kernel = 1.0 / config.sys.beta**2 * u_loc.permute_orbitals("abcd->adcb") @ gchi0_q
    kernel = kernel.times("qabcdwv,dcefwvp->qabefwp", f_1dens_3magn)
    return FourPoint(kernel, SpinChannel.NONE, config.lattice.nq, 1, 1, gchi0_q.full_niw_range, True, True).cut_niv(
        config.box.niv_core
    )


def calculate_kernel_r_q(
    vrg_q_r: FourPoint, gchi_aux_q_r_sum: FourPoint, v_nonloc: Interaction, u_loc: LocalInteraction
):
    r"""
    Returns the kernel for the self-energy calculation.
    .. math:: K = \gamma_{r;abcd}^{qv} - \gamma_{r;abef}^{qv} * U^{q}_{r;fehg} * \chi_{r;ghcd}^{q}

    minus 2/3 times the identity if the channel is the magnetic channel (due to the extra u in Eq. (1.125)).
    """
    u_r = v_nonloc.as_channel(vrg_q_r.channel) + u_loc.as_channel(vrg_q_r.channel)
    kernel = vrg_q_r - vrg_q_r @ u_r @ gchi_aux_q_r_sum

    if vrg_q_r.channel == SpinChannel.MAGN:
        kernel -= 2.0 / 3.0 * FourPoint.identity_like(kernel.to_full_niw_range())
        kernel = kernel.to_half_niw_range()

    return u_r @ kernel


def calculate_sigma_kernel_r_q(
    gamma_r: LocalFourPoint,
    gchi0_q_inv: FourPoint,
    gchi0_q_full_sum: FourPoint,
    gchi0_q_core_sum: FourPoint,
    u_loc: LocalInteraction,
    v_nonloc: Interaction,
    mpi_dist_irrq: MpiDistributor,
) -> FourPoint:
    """
    Returns the kernel in a specific channel for the self-energy calculation.
    """
    logger = config.logger

    gchi_aux_q_r = create_auxiliary_chi_r_q(gamma_r, gchi0_q_inv, u_loc, v_nonloc)
    logger.log_info(f"Non-Local auxiliary susceptibility ({gchi_aux_q_r.channel.value}) calculated.")
    logger.log_memory_usage(f"Gchi_aux ({gchi_aux_q_r.channel.value})", gchi_aux_q_r, mpi_dist_irrq.comm.size)

    if mpi_dist_irrq.comm.rank == 0:
        count_nonzero_orbital_entries(gchi_aux_q_r, f"gchi_aux_q_{gchi_aux_q_r.channel.value}")

    if config.eliashberg.perform_eliashberg:
        gchi_aux_q_r.save(
            name=f"gchi_aux_q_{gchi_aux_q_r.channel.value}_rank_{mpi_dist_irrq.comm.rank}",
            output_dir=config.output.eliashberg_path,
        )

    vrg_q_r = create_vrg_r_q(gchi_aux_q_r, gchi0_q_inv)
    logger.log_info(f"Non-local three-leg vertex gamma^wv ({vrg_q_r.channel.value}) done.")
    logger.log_memory_usage(f"Three-leg vertex ({vrg_q_r.channel.value})", vrg_q_r, mpi_dist_irrq.comm.size)

    if mpi_dist_irrq.comm.rank == 0:
        count_nonzero_orbital_entries(vrg_q_r, f"vrg_q_r_{vrg_q_r.channel.value}")

    if config.eliashberg.perform_eliashberg:
        vrg_q_r.save(
            name=f"vrg_q_{vrg_q_r.channel.value}_rank_{mpi_dist_irrq.comm.rank}",
            output_dir=config.output.eliashberg_path,
        )

    chi_phys_q_r = gchi_aux_q_r.sum_over_all_vn(config.sys.beta)
    del gchi_aux_q_r

    chi_phys_q_r = create_generalized_chi_q_with_shell_correction(
        chi_phys_q_r, gchi0_q_full_sum, gchi0_q_core_sum, u_loc, v_nonloc
    )
    logger.log_info(
        f"Updated non-local susceptibility chi^q ({chi_phys_q_r.channel.value}) with asymptotic correction."
    )
    logger.log_memory_usage(
        f"Summed auxiliary susceptibility ({chi_phys_q_r.channel.value})", chi_phys_q_r, mpi_dist_irrq.comm.size
    )

    if mpi_dist_irrq.comm.rank == 0:
        count_nonzero_orbital_entries(chi_phys_q_r, f"gchi_aux_q_{chi_phys_q_r.channel.value}_sum")

    if config.lambda_correction.perform_lambda_correction or config.output.save_quantities:
        chi_phys_q_r.mat = mpi_dist_irrq.gather(chi_phys_q_r.mat)
        if mpi_dist_irrq.comm.rank == 0:
            if config.lambda_correction.perform_lambda_correction:
                chi_phys_q_r = perform_lambda_correction(chi_phys_q_r)
            chi_phys_q_r.save(name=f"chi_phys_q_{chi_phys_q_r.channel.value}", output_dir=config.output.output_path)
        chi_phys_q_r.mat = mpi_dist_irrq.scatter(chi_phys_q_r.mat)
        logger.log_info(f"Saved physical susceptibility ({chi_phys_q_r.channel.value}) to file.")

    if config.eliashberg.perform_eliashberg:
        chi_phys_q_r.save(
            name=f"gchi_aux_q_{chi_phys_q_r.channel.value}_sum_rank_{mpi_dist_irrq.comm.rank}",
            output_dir=config.output.eliashberg_path,
        )

    return calculate_kernel_r_q(vrg_q_r, chi_phys_q_r, v_nonloc, u_loc)


def perform_lambda_correction(chi_phys_q_r: FourPoint) -> FourPoint:
    """
    Performs the lambda correction on the physical susceptibility. If 'spch' is specified, the lambda correction will
    be performed on both the density and magnetic channel whereas only the magnetic channel will be corrected if
    'sp' is specified.
    """
    logger = config.logger

    if config.lambda_correction.type not in ["spch", "sp"]:
        raise ValueError("Lambda correction type must be either 'spch' or 'sp'.")

    logger.log_info(f"Lambda correction type set to '{config.lambda_correction.type}'.")

    if config.lambda_correction.type == "spch":
        logger.log_info(f"Performing lambda correction for {chi_phys_q_r.channel.value} channel.")
        chi_r_loc = LocalFourPoint.load(
            os.path.join(config.output.output_path, f"chi_{chi_phys_q_r.channel.value}_loc.npy"),
            chi_phys_q_r.channel,
            num_vn_dimensions=0,
        ).to_full_niw_range()
        chi_phys_q_r, lambda_r = lc.perform_single_lambda_correction(
            chi_phys_q_r, chi_r_loc.mat.sum() / config.sys.beta
        )
        del chi_r_loc
        logger.log_info(
            f"Lambda correction for the {chi_phys_q_r.channel.value} channel applied with lambda = {lambda_r:.6f}."
        )
        return chi_phys_q_r

    # sp lambda correction only performed for magn channel
    if chi_phys_q_r.channel == SpinChannel.MAGN:
        logger.log_info(f"Performing lambda correction for magn channel.")
        chi_phys_q_dens = FourPoint.load(
            os.path.join(config.output.output_path, f"chi_phys_q_dens.npy"),
            SpinChannel.DENS,
            num_vn_dimensions=0,
        ).to_full_niw_range()

        chi_dens_loc, chi_magn_loc = [
            LocalFourPoint.load(
                os.path.join(config.output.output_path, f"chi_{channel.value}_loc.npy"),
                channel,
                num_vn_dimensions=0,
            ).to_full_niw_range()
            for channel in [SpinChannel.DENS, SpinChannel.MAGN]
        ]

        chi_magn_loc_sum = (chi_dens_loc.mat + chi_magn_loc.mat).sum() - 1 / config.lattice.q_grid.nk_tot * (
            config.lattice.q_grid.irrk_count[:, None, None, None, None, None] * chi_phys_q_dens.mat
        ).sum()
        chi_phys_q_r, lambda_r = lc.perform_single_lambda_correction(
            chi_phys_q_r, 1 / config.sys.beta * chi_magn_loc_sum
        )
        logger.log_info(f"Lambda correction 'sp' applied. Lambda for magn channel is: {lambda_r:.6f}.")
    return chi_phys_q_r


def calculate_sigma_from_kernel(kernel: FourPoint, giwk: GreensFunction, my_full_q_list: np.ndarray) -> SelfEnergy:
    r"""
    Returns
    .. math:: \Sigma_{ij}^{k} = -1/2 * 1/\beta * 1/N_q \sum_q [ U^q_{r;aibc} * K_{r;cbjd}^{qv} * G_{ad}^{w-v} ].
    """
    mat = np.zeros(
        (*config.lattice.k_grid.nk, config.sys.n_bands, config.sys.n_bands, 2 * config.box.niv_core),
        dtype=kernel.mat.dtype,
    )

    kernel = kernel.to_full_niw_range()
    wn = MFHelper.wn(config.box.niw_core)
    path = np.einsum_path("aijdv,xyzadv->xyzijv", kernel[0, ..., 0, :], mat, optimize=True)[1]

    for idx_q, q in enumerate(my_full_q_list):
        shifted_mat = np.roll(giwk.mat, [-i for i in q], axis=(0, 1, 2))
        for idx_w, wn_i in enumerate(wn):
            g_qk = shifted_mat[..., giwk.niv - config.box.niv_core - wn_i : giwk.niv + config.box.niv_core - wn_i]
            mat += np.einsum("aijdv,xyzadv->xyzijv", kernel[idx_q, ..., idx_w, :], g_qk, optimize=path)

    mat *= -0.5 / config.sys.beta / config.lattice.q_grid.nk_tot
    return SelfEnergy(mat, config.lattice.nk, True).compress_q_dimension()


def get_starting_sigma(output_path: str, default_sigma: SelfEnergy) -> tuple[SelfEnergy, int]:
    """
    If the output directory is specified to be the same directory as was used by a previous calculation, we try to
    retrieve the last calculated self-energy as a starting point for the next calculation. If no sigma_dga_N.npy file
    is found, we return the dmft self-energy as a starting point.
    """
    if output_path == "" or output_path is None or not os.path.exists(output_path):
        return default_sigma, 0

    files = glob.glob(os.path.join(output_path, "sigma_dga_iteration_*.npy"))
    if not files:
        return default_sigma, 0

    iterations = [int(match.group(1)) for f in files if (match := re.search(r"sigma_dga_iteration_(\d+)\.npy$", f))]
    if not iterations:
        return default_sigma, 0

    max_iter = max(iterations)
    mat = np.load(os.path.join(output_path, f"sigma_dga_iteration_{max_iter}.npy"))
    return SelfEnergy(mat, config.lattice.nk, True, True, False), max_iter


def read_last_n_sigmas_from_files(n: int, output_path: str = "./", previous_sc_path: str = "./") -> list[np.ndarray]:
    """
    Reads the last n total self-energies from the output directory and - if specified - the previous self-consistency path.
    """
    files_output_dir = glob.glob(os.path.join(output_path, "sigma_dga_iteration_*.npy"))
    if previous_sc_path != "" and previous_sc_path is not None and os.path.exists(previous_sc_path):
        files_prev_sc_dir = glob.glob(os.path.join(previous_sc_path, "sigma_dga_iteration_*.npy"))
    else:
        files_prev_sc_dir = []
    files = files_output_dir + files_prev_sc_dir

    last_iterations = sorted(
        [(int(match.group(1)), f) for f in files if (match := re.search(r"sigma_dga_iteration_(\d+)\.npy$", f))],
        key=lambda x: x[0],
        reverse=True,
    )
    last_iterations = last_iterations[:n] if len(last_iterations) >= n else last_iterations
    return [np.load(file) for _, file in last_iterations]


def calculate_self_energy_q(
    comm: MPI.Comm,
    giwk: GreensFunction,
    gamma_dens: LocalFourPoint,
    gamma_magn: LocalFourPoint,
    u_loc: LocalInteraction,
    v_nonloc: Interaction,
    sigma_dmft: SelfEnergy,
    sigma_local: SelfEnergy,
) -> SelfEnergy:
    logger = config.logger

    logger.log_info("Starting with non-local DGA routine.")
    logger.log_info("Initializing MPI distributor.")

    # MPI distributor for the irreducible BZ
    mpi_dist_irrk = MpiDistributor.create_distributor(ntasks=config.lattice.q_grid.nk_irr, comm=comm, name="Q")
    full_q_list = config.lattice.q_grid.get_q_list()
    irrk_q_list = config.lattice.q_grid.get_irrq_list()
    my_irr_q_list = irrk_q_list[mpi_dist_irrk.my_slice]

    mpi_dist_fullbz = MpiDistributor.create_distributor(ntasks=config.lattice.q_grid.nk_tot, comm=comm, name="FBZ")
    my_full_q_list = full_q_list[mpi_dist_fullbz.my_slice]

    # Hartree- and Fock-terms
    v_nonloc = v_nonloc.compress_q_dimension()
    if comm.rank == 0:
        hartree, fock = get_hartree_fock(u_loc, v_nonloc, full_q_list)
    else:
        hartree, fock = None, None
    hartree, fock = comm.bcast((hartree, fock), root=0)
    logger.log_info("Calculated Hartree and Fock terms.")
    v_nonloc = v_nonloc.reduce_q(my_irr_q_list)

    sigma_old, starting_iter = get_starting_sigma(config.self_consistency.previous_sc_path, sigma_dmft)
    if starting_iter > 0:
        logger.log_info(
            f"Using previous calculation and starting the self-consistency loop at iteration {starting_iter+1}."
        )

    delta_sigma = sigma_dmft.cut_niv(config.box.niv_core) - sigma_local.cut_niv(config.box.niv_core)
    mu_history = [config.sys.mu]

    for current_iter in range(starting_iter + 1, starting_iter + config.self_consistency.max_iter + 1):
        logger.log_info("----------------------------------------")
        logger.log_info(f"Starting iteration {current_iter}.")
        logger.log_info("----------------------------------------")

        giwk_full = GreensFunction.get_g_full(sigma_old, config.sys.mu, giwk.ek)
        # giwk_full.mat = giwk_full.mat[..., 0, 0, :][..., None, None, :]
        giwk_full.save(output_dir=config.output.output_path, name="g_dga")

        logger.log_memory_usage("giwk", giwk_full, comm.size)
        gchi0_q = BubbleGenerator.create_generalized_chi0_q(
            giwk_full, config.box.niw_core, config.box.niv_full, my_irr_q_list
        )

        if config.eliashberg.perform_eliashberg:
            gchi0_q.save(name=f"gchi0_q_rank_{comm.rank}", output_dir=config.output.output_path)

        logger.log_memory_usage("Gchi0_q_full", gchi0_q, comm.size)
        giwk_full = giwk_full.cut_niv(config.box.niw_core + config.box.niv_full)

        f_1dens_3magn = LocalFourPoint.load(os.path.join(config.output.output_path, "f_1dens_3magn_loc.npy"))
        kernel = -calculate_sigma_dc_kernel(f_1dens_3magn, gchi0_q, u_loc)

        if config.output.save_quantities:
            kernel.save(name=f"kernel_dc_rank_{comm.rank}", output_dir=config.output.output_path)

        del f_1dens_3magn
        logger.log_info("Calculated double-counting kernel.")

        gchi0_q_full_sum = 1.0 / config.sys.beta * gchi0_q.sum_over_all_vn(config.sys.beta)
        gchi0_q_core = gchi0_q.cut_niv(config.box.niv_core)
        del gchi0_q
        logger.log_memory_usage("Gchi0_q_core", gchi0_q_core, comm.size)

        gchi0_q_core_inv = gchi0_q_core.invert().take_vn_diagonal()
        logger.log_memory_usage("Gchi0_q_inv", gchi0_q_core_inv, comm.size)

        if config.eliashberg.perform_eliashberg:
            gchi0_q_core_inv.save(
                name=f"gchi0_q_inv_rank_{comm.rank}",
                output_dir=config.output.eliashberg_path,
            )

        gchi0_q_core_sum = 1.0 / config.sys.beta * gchi0_q_core.sum_over_all_vn(config.sys.beta)
        del gchi0_q_core

        kernel += calculate_sigma_kernel_r_q(
            gamma_dens, gchi0_q_core_inv, gchi0_q_full_sum, gchi0_q_core_sum, u_loc, v_nonloc, mpi_dist_irrk
        )
        logger.log_info("Calculated kernel for density channel.")

        kernel += 3 * calculate_sigma_kernel_r_q(
            gamma_magn, gchi0_q_core_inv, gchi0_q_full_sum, gchi0_q_core_sum, u_loc, v_nonloc, mpi_dist_irrk
        )
        del gchi0_q_core_inv, gchi0_q_full_sum, gchi0_q_core_sum
        logger.log_info("Calculated kernel for magnetic channel.")

        if comm.rank == 0:
            count_nonzero_orbital_entries(kernel, "kernel")

        giwk = giwk.cut_niv(config.box.niw_core + config.box.niv_core)

        kernel.mat = mpi_dist_irrk.gather(kernel.mat)
        if config.output.save_quantities:
            kernel.save(name="kernel", output_dir=config.output.output_path)

        if comm.rank == 0:
            kernel = kernel.map_to_full_bz(config.lattice.q_grid.irrk_inv)
        kernel.mat = mpi_dist_fullbz.scatter(kernel.mat)
        logger.log_info("Kernel mapped to full BZ and scattered across all MPI ranks.")

        sigma_new = calculate_sigma_from_kernel(kernel, giwk_full, my_full_q_list)

        del kernel
        logger.log_info("Self-energy calculated from kernel.")

        sigma_new.mat = mpi_dist_irrk.allreduce(sigma_new.mat)
        logger.log_memory_usage("Non-local sigma", sigma_new, comm.size)

        sigma_new = sigma_new + hartree + fock
        logger.log_info("Full non-local self-energy calculated.")

        # This is done to minimize noise. We remove some fluctuations from dmft that are included in the local self-energy
        # calculated in this code and add the smooth dmft self-energy
        sigma_new += delta_sigma
        sigma_new = sigma_new.concatenate_self_energies(sigma_dmft)

        if comm.rank == 0:
            count_nonzero_orbital_entries(sigma_new, "sigma_new")

        old_mu = config.sys.mu
        if comm.rank == 0:
            config.sys.mu = update_mu(
                config.sys.mu, config.sys.n, giwk_full.ek, sigma_new.mat, config.sys.beta, sigma_dmft.fit_smom()[0]
            )  # maybe sigma_new.fit_smom()[0]

        config.sys.mu = comm.bcast(config.sys.mu)
        mu_history.append(config.sys.mu)
        logger.log_info(f"Updated mu from {old_mu} to {config.sys.mu}.")

        if config.self_consistency.use_poly_fit and config.poly_fitting.do_poly_fitting:
            sigma_new = sigma_new.fit_polynomial(
                config.poly_fitting.n_fit, config.poly_fitting.o_fit, config.box.niv_core
            )
            logger.log_info(f"Fitted polynomial to sigma at iteration {current_iter}.")

        logger.log_info("Applying mixing strategy for the self-energy.")
        if comm.rank == 0:
            sigma_new = apply_mixing_strategy(sigma_new, sigma_old, sigma_dmft, current_iter)
        else:
            sigma_new = None
        sigma_new = comm.bcast(sigma_new)

        if config.self_consistency.save_iter and config.output.save_quantities and comm.rank == 0:
            sigma_new.save(name=f"sigma_dga_iteration_{current_iter}", output_dir=config.output.output_path)
            logger.log_info(f"Saved sigma for iteration {current_iter} as numpy array.")

        logger.log_info("Checking self-consistency convergence.")
        if comm.rank == 0 and current_iter > starting_iter + 1:
            converged = np.allclose(
                sigma_old.compress_q_dimension().mat,
                sigma_new.compress_q_dimension().mat,
                atol=config.self_consistency.epsilon,
            )
        else:
            converged = False
        converged = comm.bcast(converged)

        sigma_old = sigma_new
        if converged:
            logger.log_info(f"Self-consistency reached. Sigma converged at iteration {current_iter}.")
            break
        logger.log_info("Self-consistency not reached yet.")

    mpi_dist_irrk.delete_file()
    mpi_dist_fullbz.delete_file()

    if config.output.save_quantities:
        np.save(os.path.join(config.output.output_path, "mu_history.npy"), mu_history)
        logger.log_info("Saved mu history as numpy array.")

    return sigma_old


def apply_mixing_strategy(
    sigma_new: SelfEnergy, sigma_old: SelfEnergy, sigma_dmft: SelfEnergy, current_iter: int
) -> SelfEnergy:
    """
    Applies the mixing strategy for the self-consistency loop. The mixing strategy is defined in the config file and
    is either 'linear' or 'pulay'.
    """
    logger = config.logger
    strategy = config.self_consistency.mixing_strategy
    n_hist = config.self_consistency.mixing_history_length

    if (
        strategy == "pulay"
        and current_iter > n_hist
        and config.self_consistency.save_iter
        and config.output.save_quantities
    ):
        last_results = read_last_n_sigmas_from_files(
            n_hist, config.output.output_path, config.self_consistency.previous_sc_path
        )
        sigma_dmft_stacked = np.tile(sigma_dmft.mat, (config.lattice.k_grid.nk_tot, 1, 1, 1))
        last_proposals = [sigma_dmft_stacked] + last_results
        last_results = last_results + [sigma_new.mat]

        niv_dmft = sigma_new.current_shape[-1] // 2
        niv_core = config.box.niv_core
        last_proposals = [sigma[..., niv_dmft - niv_core : niv_dmft + niv_core] for sigma in last_proposals]
        last_results = [sigma[..., niv_dmft - niv_core : niv_dmft + niv_core] for sigma in last_results]
        logger.log_info(f"Loaded last {n_hist} self-energies from files.")

        shape = last_results[-1].shape
        n_total = int(np.prod(shape))
        r_matrix = np.zeros((2 * n_total, n_hist), dtype=np.float64)
        f_matrix = np.zeros_like(r_matrix)
        f_i = np.zeros((2 * n_total), dtype=np.float64)

        def get_proposal(idx: int):
            return last_proposals[idx].flatten()

        def get_result(idx: int):
            return last_results[idx].flatten()

        for i in range(n_hist):
            proposal_diff = get_proposal(-1 - i) - get_proposal(-2 - i)
            r_matrix[:n_total, i] = proposal_diff.real
            r_matrix[n_total:, i] = proposal_diff.imag

            result_diff = get_result(-1 - i) - get_result(-2 - i)
            f_matrix[:n_total, i] = result_diff.real
            f_matrix[n_total:, i] = result_diff.imag

            f_matrix[:, i] -= r_matrix[:, i]

        iter_diff = get_result(-1) - get_proposal(-1)
        f_i[:n_total] = iter_diff.real
        f_i[n_total:] = iter_diff.imag

        update = config.self_consistency.mixing * f_i
        fact1 = (r_matrix + config.self_consistency.mixing * f_matrix) @ np.linalg.inv(f_matrix.T @ f_matrix)
        update -= fact1 @ (f_matrix.T @ f_i)
        update = update[:n_total] + 1j * update[n_total:]
        sigma_new.mat[..., niv_dmft - niv_core : niv_dmft + niv_core] = sigma_old.compress_q_dimension().mat[
            ..., niv_dmft - niv_core : niv_dmft + niv_core
        ] + update.reshape(shape)

        logger.log_info(
            f"Pulay mixing applied with {n_hist} previous iterations and a mixing parameter of {config.self_consistency.mixing}."
        )

        return sigma_new

    sigma_new = config.self_consistency.mixing * sigma_new + (1 - config.self_consistency.mixing) * sigma_old
    logger.log_info(
        f"Sigma linearly mixed with previous iteration using a mixing parameter of {config.self_consistency.mixing}."
    )
    return sigma_new
