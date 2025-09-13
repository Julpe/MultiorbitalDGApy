import os

import mpi4py.MPI as MPI
import numpy as np
import scipy as sp

import scdga.config as config
from scdga import nonlocal_sde
from scdga.bubble_gen import BubbleGenerator
from scdga.four_point import FourPoint
from scdga.gap_function import GapFunction
from scdga.greens_function import GreensFunction
from scdga.interaction import LocalInteraction, Interaction
from scdga.local_four_point import LocalFourPoint
from scdga.matsubara_frequencies import MFHelper
from scdga.mpi_distributor import MpiDistributor
from scdga.n_point_base import SpinChannel, FrequencyNotation


def delete_files(filepath: str, *args) -> None:
    """
    Deletes files in the given directory. If the file is not found, it will be ignored. The files that are deleted
    are usually temporary files that are not needed anymore after the calculation is done.
    """
    for name in args:
        if not isinstance(name, str):
            raise TypeError(f"Expected string, got {type(name)}.")
        full_path = os.path.join(filepath, name)
        if os.path.isfile(full_path):
            try:
                os.remove(full_path)
            except OSError:
                config.logger.log_info(f"Error deleting file: {name}.")


def create_full_vertex_q_r(
    u_loc: LocalInteraction, v_nonloc: Interaction, gamma_r: LocalFourPoint, comm: MPI.Comm
) -> FourPoint:
    """
    Calculates the full vertex in the given channel (either density or magnetic). For details, see Eq. (3.139) in my thesis.
    """
    logger = config.logger
    logger.log_info(f"Starting to calculate the full {gamma_r.channel.value} vertex.")

    gchi0_q_inv = FourPoint.load(
        os.path.join(config.output.eliashberg_path, f"gchi0_q_inv_rank_{comm.rank}.npy"), num_vn_dimensions=1
    )
    logger.log_info(f"Loaded gchi0_q_inv and gamma_{gamma_r.channel.value}_loc from files.")
    f_q_r = nonlocal_sde.create_auxiliary_chi_r_q(gamma_r, gchi0_q_inv, u_loc, v_nonloc)
    logger.log_info(f"Non-Local auxiliary susceptibility ({gamma_r.channel.value}) calculated.")

    f_q_r = config.sys.beta**2 * (gchi0_q_inv - gchi0_q_inv @ f_q_r @ gchi0_q_inv)
    del gchi0_q_inv
    logger.log_info(f"Calculated first part of full {gamma_r.channel.value} vertex.")

    vrg_q_r = FourPoint.load(
        os.path.join(config.output.eliashberg_path, f"vrg_q_{gamma_r.channel.value}_rank_{comm.rank}.npy"),
        channel=gamma_r.channel,
        num_vn_dimensions=1,
    )
    gchi_aux_q_r_sum = FourPoint.load(
        os.path.join(config.output.eliashberg_path, f"gchi_aux_q_{gamma_r.channel.value}_sum_rank_{comm.rank}.npy"),
        channel=gamma_r.channel,
        num_vn_dimensions=0,
    )
    logger.log_info(f"Loaded vrg_q_{gamma_r.channel.value} and gchi_aux_q_{gamma_r.channel.value}_sum from files.")

    u = u_loc.as_channel(gamma_r.channel) + v_nonloc.as_channel(gamma_r.channel)
    f_q_r += (1 - u @ gchi_aux_q_r_sum) @ (u @ (vrg_q_r * vrg_q_r))
    del gchi_aux_q_r_sum, vrg_q_r
    logger.log_info(f"Calculated second part of full {f_q_r.channel.value} vertex.")

    delete_files(
        config.output.eliashberg_path,
        f"vrg_q_{gamma_r.channel.value}_rank_{comm.rank}.npy",
        f"gchi_aux_q_{gamma_r.channel.value}_sum_rank_{comm.rank}.npy",
    )

    return f_q_r


def create_full_vertex_q_r2(channel: SpinChannel, niv_pp: int, mpi_distributor: MpiDistributor) -> FourPoint:
    r"""
    Alternative way that calculates the full vertex function in either the density or magnetic channel using
    :math:`F^q_r = F^\omega_r [ 1- \chi_0^{nl,q} F^\omega_r]^{-1}`, see Eq. (3.106a) and Eq. (3.106b) in my thesis for
    the case of :math:`V^q=0`.
    """
    f_r_loc = LocalFourPoint.load(
        os.path.join(config.output.output_path, f"f_{channel.value}_loc.npy"), channel=channel
    )  # .cut_niv(config.box.niv_core)
    gchi0_loc = LocalFourPoint.load(
        os.path.join(config.output.output_path, "gchi0_loc.npy"), num_vn_dimensions=1
    )  # .cut_niv(config.box.niv_core)
    gchi0_q = FourPoint.load(
        os.path.join(config.output.output_path, f"gchi0_q_rank_{mpi_distributor.comm.rank}.npy"),
        num_vn_dimensions=1,
    )  # .cut_niv(config.box.niv_core)

    f_q_r = (
        f_r_loc
        @ (
            FourPoint.identity(
                gchi0_q.n_bands, config.box.niw_core, config.box.niv_full, gchi0_q.nq_tot, config.lattice.nq
            )
            - (gchi0_q - gchi0_loc) @ f_r_loc
        ).invert()
    ).cut_niv(config.box.niv_core)
    del f_r_loc, gchi0_q, gchi0_loc
    return transform_vertex_ph_to_pp_w0(f_q_r, niv_pp)


def transform_vertex_ph_to_pp_w0(f_q_r: LocalFourPoint | FourPoint, niv_pp: int) -> LocalFourPoint | FourPoint:
    """
    Transforms the vertex function from particle-hole notation to particle-particle notation based on Motoharu Kitatani's
    frequency convention (which is the same as Georg Rohringer's). This is done by flipping the last Matsubara
    frequency to get v, -v' and then applying the necessary condition of w = v-v'. The full vertex is needed with these
    frequency shifts for the construction of the pairing vertex.
    """
    is_local = not isinstance(f_q_r, FourPoint)

    vn = MFHelper.vn(niv_pp)
    omega = vn[:, None] - vn[None, :]
    f_q_r = f_q_r.cut_niv(niv_pp).to_full_niw_range().flip_frequency_axis(-1)
    f_q_r_pp_mat = np.zeros((*f_q_r.current_shape[:-3], 2 * niv_pp, 2 * niv_pp), dtype=f_q_r.mat.dtype)
    for idx, w in enumerate(MFHelper.wn(config.box.niw_core)):
        f_q_r_pp_mat[..., omega == w] = -f_q_r[..., idx, omega == w]

    if is_local:
        return LocalFourPoint(f_q_r_pp_mat, f_q_r.channel, 0, frequency_notation=FrequencyNotation.PP)
    return FourPoint(
        f_q_r_pp_mat, f_q_r.channel, config.lattice.q_grid.nk, 0, 2, True, True, True, FrequencyNotation.PP
    )


def create_full_vertex_q_r_pp_w0(
    u_loc: LocalInteraction, v_nonloc: Interaction, gamma_r: LocalFourPoint, niv_pp: int, mpi_dist_irrk: MpiDistributor
):
    """
    Calculates the full vertex in PH notation and transforms it to PP notation for the both density or magnetic channel.
    """
    logger = config.logger

    f_q_r = create_full_vertex_q_r(u_loc, v_nonloc, gamma_r, mpi_dist_irrk.comm)
    f_q_r = transform_vertex_ph_to_pp_w0(f_q_r, niv_pp)

    logger.log_info(f"Full ladder-vertex ({gamma_r.channel.value}) calculated.")
    logger.log_memory_usage(f"Full ladder-vertex ({gamma_r.channel.value})", f_q_r, mpi_dist_irrk.comm.size)

    return f_q_r


def get_initial_gap_function(shape: tuple, channel: SpinChannel) -> np.ndarray:
    """
    Generates the initial gap function based on the specified shape, spin channel and symmetry settings from the
    configuration. Depending on the symmetry and spin channel, it initializes the gap function with appropriate
    properties. Most often it should suffice to use a random initialization.
    """
    if channel not in {SpinChannel.SING, SpinChannel.TRIP}:
        raise ValueError("Channel must be either SING or TRIP.")

    gap0 = np.zeros(shape, dtype=np.complex64)
    niv = shape[-1] // 2
    k_grid = config.lattice.k_grid.grid

    symm = {
        "d-wave": lambda k: -np.cos(k[0])[:, None, None] + np.cos(k[1])[None, :, None],
        "p-wave-x": lambda k: np.sin(k[0])[:, None, None],
        "p-wave-y": lambda k: np.sin(k[1])[None, :, None],
    }

    if config.eliashberg.symmetry in symm:
        gap0[..., niv:] = np.repeat(symm[config.eliashberg.symmetry](k_grid)[:, :, :, None, None, None], niv, axis=-1)
    else:
        gap0 = np.random.random_sample(shape)

    v_sym = {
        "d-wave": "even" if channel == SpinChannel.SING else "odd",
        "p-wave-x": "odd" if channel == SpinChannel.SING else "even",
        "p-wave-y": "odd" if channel == SpinChannel.SING else "even",
    }.get(config.eliashberg.symmetry, "")

    if v_sym in {"even", "odd"}:
        gap0[..., :niv] = gap0[..., niv:] if v_sym == "even" else -gap0[..., niv:]
    else:
        gap0 = np.random.random_sample(shape)

    return gap0


def solve_eliashberg_lanczos(gamma_q_r_pp: FourPoint, gchi0_q0_pp: FourPoint):
    """
    Solves the Eliashberg equation for the superconducting eigenvalue and gap function using an Implicitly Restarted
    Lanczos Method with ARPACK. Returns the largest n_eig eigenvalues and corresponding eigenvectors as two separate
    lists.
    """
    logger = config.logger

    logger.log_info(
        f"Starting to solve the Eliashberg equation for the {gamma_q_r_pp.channel.value}let channel.",
        allowed_ranks=(0, 1),
    )

    gamma_q_r_pp = gamma_q_r_pp.map_to_full_bz(
        config.lattice.q_grid.irrk_inv, config.lattice.q_grid.nk
    ).decompress_q_dimension()
    logger.log_memory_usage(f"Gamma_pp_{gamma_q_r_pp.channel.value}", gamma_q_r_pp, 1, allowed_ranks=(0, 1))

    sign = 1 if gamma_q_r_pp.channel == SpinChannel.SING else -1

    gamma_x = sign * gamma_q_r_pp.fft()
    gamma_x_flipped = gamma_x.flip_momentum_axis().flip_frequency_axis(-1).permute_orbitals("abcd->adcb")

    gap_shape = gamma_q_r_pp.nq + 2 * (gamma_q_r_pp.n_bands,) + (2 * gamma_q_r_pp.niv,)
    gchi0_q0_pp = gchi0_q0_pp.decompress_q_dimension()

    gap0 = get_initial_gap_function(gap_shape, gamma_q_r_pp.channel)
    logger.log_info(
        f"Initialized the gap function as {config.eliashberg.symmetry if config.eliashberg.symmetry else "random"} "
        f"for the {gamma_q_r_pp.channel.value}let channel.",
        allowed_ranks=(0, 1),
    )

    einsum_str1 = "xyzacbdv,xyzdcv->xyzabv"
    path1 = np.einsum_path(einsum_str1, gchi0_q0_pp.mat, gap0, optimize=True)[1]
    einsum_str2 = "xyzadbcvp,xyzcdp->xyzabv"
    path2 = np.einsum_path(einsum_str2, gamma_x.mat, gap0, optimize=True)[1]

    norm = 0.5 / config.lattice.q_grid.nk_tot / config.sys.beta

    def mv(gap: np.ndarray):
        gap_gg = np.fft.fftn(
            np.einsum(einsum_str1, gchi0_q0_pp.mat, gap.reshape(gap_shape), optimize=path1), axes=(0, 1, 2)
        )
        gap_gg_flipped = np.roll(np.flip(gap_gg, axis=(0, 1, 2)), shift=1, axis=(0, 1, 2))
        gap_new = np.einsum(einsum_str2, gamma_x.mat, gap_gg, optimize=path2) + sign * np.einsum(
            einsum_str2, gamma_x_flipped.mat, gap_gg_flipped, optimize=path2
        )
        return np.fft.ifftn(norm * gap_new, axes=(0, 1, 2)).flatten()

    mat = sp.sparse.linalg.LinearOperator(shape=(np.prod(gap_shape), np.prod(gap_shape)), matvec=mv)
    logger.log_info(
        f"Starting Lanczos method to retrieve largest {"" if config.eliashberg.n_eig > 1 else f" {config.eliashberg.n_eig}"}"
        f"eigenvalue{"" if config.eliashberg.n_eig == 1 else "s"} and eigenvector{"" if config.eliashberg.n_eig == 1 else "s"} "
        f"for the {gamma_q_r_pp.channel.value}let channel.",
        allowed_ranks=(0, 1),
    )

    lambdas, gaps = sp.sparse.linalg.eigsh(
        mat, k=config.eliashberg.n_eig, tol=config.eliashberg.epsilon, v0=gap0, which="LA", maxiter=10000
    )
    logger.log_info(
        f"Finished Lanczos method for the largest {"" if config.eliashberg.n_eig > 1 else f" {config.eliashberg.n_eig}"} "
        f"eigenvalue{"" if config.eliashberg.n_eig == 1 else "s"} and eigenvector{"" if config.eliashberg.n_eig == 1 else "s"} "
        f"for the {gamma_q_r_pp.channel.value}let channel.",
        allowed_ranks=(0, 1),
    )

    order = lambdas.argsort()[::-1]  # sort eigenvalues in descending order
    lambdas = lambdas[order]
    gaps = gaps[:, order]

    logger.log_info(
        f"Largest {config.eliashberg.n_eig} eigenvalue{"" if config.eliashberg.n_eig == 1 else "s"} for the "
        f"{gamma_q_r_pp.channel.value}let channel are: {', '.join(f'{lam:.6f}' for lam in lambdas)}.",
        allowed_ranks=(0, 1),
    )

    gaps = [
        GapFunction(gaps[..., i].reshape(gap_shape), gamma_q_r_pp.channel, gamma_q_r_pp.nq)
        for i in range(config.eliashberg.n_eig)
    ]

    logger.log_info(
        f"Finished solving the Eliashberg equation for the {gamma_q_r_pp.channel.value}let channel.",
        allowed_ranks=(0, 1),
    )

    return lambdas, gaps


def create_local_reducible_pp_diagrams(
    giwk_dmft: GreensFunction,
    f_dens_loc: LocalFourPoint,
    f_magn_loc: LocalFourPoint,
    gchi_dens_loc: LocalFourPoint,
    gchi_magn_loc: LocalFourPoint,
    channel: SpinChannel,
) -> LocalFourPoint:
    """
    Creates the reducible particle-particle diagrams for either singlet or triplet channel in PP notation. NOTE:
    This is not finished yet and still in development. Please consider setting "include_local_part" in the Eliashberg
    configuration to False.
    """
    logger = config.logger

    if channel not in (SpinChannel.SING, SpinChannel.TRIP):
        raise ValueError("Channel must be either singlet or triplet.")

    gchi0 = BubbleGenerator.create_generalized_chi0(
        giwk_dmft, config.box.niw_core, config.box.niv_core
    )  # .change_frequency_notation_ph_to_pp()

    f_dens_loc = f_dens_loc.cut_niv(config.box.niv_core)  # .change_frequency_notation_ph_to_pp()
    f_magn_loc = f_magn_loc.cut_niv(config.box.niv_core)  # .change_frequency_notation_ph_to_pp()
    logger.log_info("Loaded full local density and magnetic vertices and transformed them to pp notation.")

    f_r_loc = 0.5 * f_dens_loc + (-1.5 if channel == SpinChannel.SING else 0.5) * f_magn_loc
    f_r_loc.channel = channel
    logger.log_info(f"Constructed local {channel.value}let vertex.")

    logger.log_info("Loaded local density and magnetic susceptibilities and transformed them to pp notation.")

    gchi_r_loc = 0.5 * gchi_dens_loc + (-1.5 if channel == SpinChannel.SING else 0.5) * gchi_magn_loc
    gchi_r_loc.channel = channel
    logger.log_info(f"Constructed local {channel.value}let susceptibility.")

    sign = 1 if channel == SpinChannel.SING else -1
    gamma_r_loc = config.sys.beta**2 * (4 * (gchi_r_loc - sign * gchi0).invert() + 2 * sign * gchi0.invert())
    logger.log_info(f"Constructed local {channel.value}let irreducible diagrams.")

    phi_r_loc = 1.0 / config.sys.beta**2 * (f_r_loc - gamma_r_loc).change_frequency_notation_ph_to_pp()
    phi_r_loc.mat = phi_r_loc.mat[..., phi_r_loc.current_shape[-3] // 2, :, :]  # we need w=0,v,v'
    phi_r_loc.update_original_shape()
    return phi_r_loc.to_half_niw_range()


def solve(
    giwk_dga: GreensFunction,
    giwk_dmft: GreensFunction,
    u_loc: LocalInteraction,
    v_nonloc: Interaction,
    gamma_dens: LocalFourPoint,
    gamma_magn: LocalFourPoint,
    comm: MPI.Comm,
):
    """
    Solves the Eliashberg equation for largest the superconducting eigenvalues and corresponding gap functions.
    """
    logger = config.logger

    mpi_dist_irrk = MpiDistributor.create_distributor(ntasks=config.lattice.q_grid.nk_irr, comm=comm, name="Q")
    irrk_q_list = config.lattice.q_grid.get_irrq_list()
    my_irr_q_list = irrk_q_list[mpi_dist_irrk.my_slice]

    v_nonloc = v_nonloc.reduce_q(my_irr_q_list)

    niv_pp = min(config.box.niw_core // 2, config.box.niv_core // 2)
    if config.eliashberg.include_local_part:
        niv_pp = min(config.box.niw_core // 3, config.box.niv_core // 3)

    # f_dens_pp = create_full_vertex_q_r2(SpinChannel.DENS, niv_pp, mpi_dist_irrk)
    f_dens_pp = create_full_vertex_q_r_pp_w0(u_loc, v_nonloc, gamma_dens, niv_pp, mpi_dist_irrk)

    # f_magn_pp = create_full_vertex_q_r2(SpinChannel.MAGN, niv_pp, mpi_dist_irrk)
    f_magn_pp = create_full_vertex_q_r_pp_w0(u_loc, v_nonloc, gamma_magn, niv_pp, mpi_dist_irrk)

    delete_files(config.output.eliashberg_path, f"gchi0_q_inv_rank_{comm.rank}.npy")
    delete_files(config.output.output_path, f"gchi0_q_rank_{comm.rank}.npy")

    if config.eliashberg.save_fq:
        for f_pp, name in [(f_dens_pp, "f_irrq_dens_pp"), (f_magn_pp, "f_irrq_magn_pp")]:
            f_pp.mat = mpi_dist_irrk.gather(f_pp.mat)
            if comm.rank == 0:
                f_pp.save(output_dir=config.output.output_path, name=name)
            f_pp.mat = mpi_dist_irrk.scatter(f_pp.mat)
        config.logger.log_info("Saved full ladder-vertices (dens & magn) in the irreducible BZ to file.")

    mpi_dist_irrk.delete_file()

    gamma_sing_pp = 0.5 * f_dens_pp - 1.5 * f_magn_pp
    gamma_sing_pp.channel = SpinChannel.SING
    logger.log_info("Calculated full ladder-vertex (singlet) in pp notation.")

    gamma_trip_pp = 0.5 * f_dens_pp + 0.5 * f_magn_pp
    gamma_trip_pp.channel = SpinChannel.TRIP
    del f_dens_pp, f_magn_pp
    logger.log_info("Calculated full ladder-vertex (triplet) in pp notation.")

    gamma_sing_pp.mat = mpi_dist_irrk.gather(gamma_sing_pp.mat)
    gamma_trip_pp.mat = mpi_dist_irrk.gather(gamma_trip_pp.mat)

    gchi0_q0_pp = None
    if mpi_dist_irrk.my_rank == 0:
        gchi0_q0_pp = BubbleGenerator.create_generalized_chi0_pp_w0(giwk_dga, niv_pp)
        logger.log_info("Created the bare bubble susceptibility in pp notation.")

        if config.eliashberg.include_local_part:
            f_dens_loc = LocalFourPoint.load(
                os.path.join(config.output.output_path, f"f_dens_loc.npy"), SpinChannel.DENS
            )
            f_magn_loc = LocalFourPoint.load(
                os.path.join(config.output.output_path, f"f_magn_loc.npy"), SpinChannel.MAGN
            )
            f_ud_loc_fs_pp = transform_vertex_ph_to_pp_w0(0.5 * f_dens_loc - 0.5 * f_magn_loc, niv_pp)
            f_ud_loc_fs_pp.channel = SpinChannel.UD
            logger.log_info(f"Calculated full local UD vertex in pp notation.")

            if config.output.save_quantities:
                f_ud_loc_fs_pp.save(output_dir=config.output.eliashberg_path, name="f_ud_loc_fs_pp")

                f_ud_loc_pp = (
                    (0.5 * f_dens_loc - 0.5 * f_magn_loc)
                    .cut_niv(config.box.niv_core)
                    .change_frequency_notation_ph_to_pp()
                )
                f_ud_loc_pp.save(output_dir=config.output.eliashberg_path, name="f_ud_loc_pp")
                del f_ud_loc_pp

            gamma_sing_pp -= f_ud_loc_fs_pp
            gamma_trip_pp -= f_ud_loc_fs_pp

            gchi_dens_loc = LocalFourPoint.load(
                os.path.join(config.output.output_path, f"gchi_dens_loc.npy"), SpinChannel.DENS
            )  # .change_frequency_notation_ph_to_pp()
            gchi_magn_loc = LocalFourPoint.load(
                os.path.join(config.output.output_path, f"gchi_magn_loc.npy"), SpinChannel.MAGN
            )  # .change_frequency_notation_ph_to_pp()

            phi_sing_loc_pp = create_local_reducible_pp_diagrams(
                giwk_dmft, f_dens_loc, f_magn_loc, gchi_dens_loc, gchi_magn_loc, SpinChannel.SING
            )
            phi_trip_loc_pp = create_local_reducible_pp_diagrams(
                giwk_dmft, f_dens_loc, f_magn_loc, gchi_dens_loc, gchi_magn_loc, SpinChannel.TRIP
            )
            phi_ud_loc_pp = 0.5 * (phi_sing_loc_pp + phi_trip_loc_pp)
            logger.log_info("Created the local reducible singlet and triplet pairing diagrams.")

            if config.output.save_quantities:
                phi_sing_loc_pp.save(output_dir=config.output.eliashberg_path, name="phi_sing_loc_pp")
                phi_trip_loc_pp.save(output_dir=config.output.eliashberg_path, name="phi_trip_loc_pp")
                phi_ud_loc_pp.save(output_dir=config.output.eliashberg_path, name="phi_ud_loc_pp")

            gamma_sing_pp -= phi_ud_loc_pp
            gamma_trip_pp -= phi_ud_loc_pp
            del (
                f_dens_loc,
                f_magn_loc,
                f_ud_loc_fs_pp,
                gchi_dens_loc,
                gchi_magn_loc,
                phi_sing_loc_pp,
                phi_trip_loc_pp,
                phi_ud_loc_pp,
            )

        if config.eliashberg.save_pairing_vertex:
            gamma_sing_pp.save(
                output_dir=config.output.eliashberg_path, name=f"gamma_irrq_{gamma_sing_pp.channel.value}_pp"
            )
            gamma_trip_pp.save(
                output_dir=config.output.eliashberg_path, name=f"gamma_irrq_{gamma_trip_pp.channel.value}_pp"
            )
            config.logger.log_info(
                f"Saved singlet and triplet pairing vertices in pp notation in the irreducible BZ to file."
            )

    gchi0_q0_pp = mpi_dist_irrk.bcast(gchi0_q0_pp, root=0)
    gamma_trip_pp = mpi_dist_irrk.bcast(gamma_trip_pp, root=0)

    lambdas_sing, lambdas_trip, gaps_sing, gaps_trip = (None,) * 4
    if mpi_dist_irrk.my_rank == 0:
        lambdas_sing, gaps_sing = solve_eliashberg_lanczos(gamma_sing_pp, gchi0_q0_pp)
    if mpi_dist_irrk.mpi_size == 1 or mpi_dist_irrk.my_rank == 1:
        lambdas_trip, gaps_trip = solve_eliashberg_lanczos(gamma_trip_pp, gchi0_q0_pp)

    mpi_dist_irrk.delete_file()

    lambdas_sing = mpi_dist_irrk.bcast(lambdas_sing, root=0)
    lambdas_trip = mpi_dist_irrk.bcast(lambdas_trip, root=1 if mpi_dist_irrk.mpi_size > 1 else 0)

    gaps_sing = mpi_dist_irrk.bcast(gaps_sing, root=0)
    gaps_trip = mpi_dist_irrk.bcast(gaps_trip, root=1 if mpi_dist_irrk.mpi_size > 1 else 0)

    return lambdas_sing, lambdas_trip, gaps_sing, gaps_trip
