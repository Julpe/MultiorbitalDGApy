import os

import numpy as np
from matplotlib import pyplot as plt

import scdga.config as config
from scdga.gap_function import GapFunction
from scdga.local_four_point import LocalFourPoint
from scdga.local_n_point import LocalNPoint
from scdga.matsubara_frequencies import MFHelper
from scdga.n_point_base import IAmNonLocal


def add_afzb(ax=None, kx=None, ky=None, lw=1.0, marker=""):
    """
    Add visual lines to mark the antiferromagnetic zone-boundary to existing axis.
    """
    if np.any(kx < 0):
        ax.plot(np.linspace(-np.pi, 0, 101), np.linspace(0, np.pi, 101), "--k", lw=lw, marker=marker)
        ax.plot(np.linspace(-np.pi, 0, 101), np.linspace(0, -np.pi, 101), "--k", lw=lw, marker=marker)
        ax.plot(np.linspace(0, np.pi, 101), np.linspace(-np.pi, 0, 101), "--k", lw=lw, marker=marker)
        ax.plot(np.linspace(0, np.pi, 101), np.linspace(np.pi, 0, 101), "--k", lw=lw, marker=marker)
        ax.plot(kx, 0 * kx, "-k", lw=lw, marker=marker)
        ax.plot(0 * ky, ky, "-k", lw=lw, marker=marker)
    else:
        ax.plot(np.linspace(0, np.pi, 101), np.linspace(np.pi, 2 * np.pi, 101), "--k", lw=lw, marker=marker)
        ax.plot(np.linspace(np.pi, 0, 101), np.linspace(0, np.pi, 101), "--k", lw=lw, marker=marker)
        ax.plot(np.linspace(np.pi, 2 * np.pi, 101), np.linspace(0, np.pi, 101), "--k", lw=lw, marker=marker)
        ax.plot(np.linspace(np.pi, 2 * np.pi, 101), np.linspace(np.pi * 2, np.pi, 101), "--k", lw=lw, marker=marker)
        ax.plot(kx, np.pi * np.ones_like(kx), "-k", lw=lw, marker=marker)
        ax.plot(np.pi * np.ones_like(ky), ky, "-k", lw=lw, marker=marker)

    ax.set_xlim(kx[0], kx[-1])
    ax.set_ylim(ky[0], ky[-1])
    ax.set_xlabel("$k_x$")
    ax.set_ylabel("$k_y$")


def find_zeros(mat: np.ndarray) -> np.ndarray:
    """Finds the zero crossings of a 2D matrix."""
    ind_x = np.arange(mat.shape[0])
    ind_y = np.arange(mat.shape[1])

    cs1 = plt.contour(ind_x, ind_y, mat.T.real, cmap="RdBu", levels=[0])
    paths = cs1.get_paths()
    plt.close()
    paths = np.atleast_1d(paths)
    vertices = []
    for path in paths:
        vertices.extend(path.vertices)
    return np.array(vertices, dtype=int)


def sigma_loc_checks(
    siw_arr: list[np.ndarray],
    labels: list[str],
    beta: float,
    output_dir: str = "./",
    show: bool = False,
    save: bool = True,
    name: str = "",
    xmax: float = 0,
) -> None:
    """
    siw_arr: list of local self-energies for routine plots.
    """
    if xmax == 0:
        xmax = 5 + 2 * beta
    fig, axes = plt.subplots(ncols=2, nrows=2, figsize=(8, 5))
    axes = axes.flatten()

    for i, siw in enumerate(siw_arr):
        vn = MFHelper.vn(np.size(siw) // 2)
        axes[0].plot(vn, siw.real, label=labels[i])
        axes[1].plot(vn, siw.imag, label=labels[i])
        axes[2].loglog(vn, siw.real, label=labels[i])
        axes[3].loglog(vn, np.abs(siw.imag), label=labels[i])

    for i in range(4):
        axes[i].set_xlabel(r"$\nu_n$")

    axes[0].set_ylabel(r"$\Re \Sigma(i\nu_n)$")
    axes[1].set_ylabel(r"$\Im \Sigma(i\nu_n)$")
    axes[2].set_ylabel(r"$\Re \Sigma(i\nu_n)$")
    axes[3].set_ylabel(r"$|\Im \Sigma(i\nu_n)|$")

    axes[0].set_xlim(0, xmax)
    axes[1].set_xlim(0, xmax)
    axes[2].set_xlim(None, xmax)
    axes[3].set_xlim(None, xmax)
    plt.legend()
    axes[1].set_ylim(None, 0)
    plt.tight_layout()
    if save:
        plt.savefig(output_dir + f"/sde_" + name + "_check.png")
    if show:
        plt.show()
    else:
        plt.close()


def chi_checks(
    chi_dens_list: list[np.ndarray],
    chi_magn_list: list[np.ndarray],
    labels: list[str],
    e_kin: float,
    output_dir: str = "./",
    orbs=[0, 0, 0, 0],
    show: bool = False,
    save: bool = True,
    name: str = "",
):
    """
    Routine plots to inspect chi_dens and chi_magn
    """
    fig, axes = plt.subplots(ncols=2, nrows=2, figsize=(8, 5), dpi=500)
    axes = axes.flatten()
    niw_chi_input = np.size(chi_dens_list[0][*orbs, :])

    for i, cd in enumerate(chi_dens_list):
        axes[0].plot(MFHelper.wn(len(cd[*orbs, :]) // 2), cd[*orbs, :].real, label=labels[i])
    axes[0].set_ylabel(r"$\Re \chi(i\omega_n)_{dens}$")
    axes[0].legend()

    for i, cd in enumerate(chi_magn_list):
        axes[1].plot(MFHelper.wn(len(cd[*orbs, :]) // 2), cd[*orbs, :].real, label=labels[i])
    axes[1].set_ylabel(r"$\Re \chi(i\omega_n)_{magn}$")
    axes[1].legend()

    for i, cd in enumerate(chi_dens_list):
        axes[2].loglog(MFHelper.wn(len(cd[*orbs, :]) // 2), cd[*orbs, :].real, label=labels[i], ms=0)
    axes[2].loglog(
        MFHelper.wn(niw_chi_input),
        np.real(1 / (1j * MFHelper.wn(niw_chi_input, config.sys.beta) + 0.000001) ** 2 * e_kin) * 2,
        ls="--",
        label="Asympt",
        ms=0,
    )
    axes[2].set_ylabel(r"$\Re \chi(i\omega_n)_{dens}$")
    axes[2].legend()

    for i, cd in enumerate(chi_magn_list):
        axes[3].loglog(MFHelper.wn(len(cd[*orbs, :]) // 2), cd[*orbs, :].real, label=labels[i], ms=0)
    axes[3].loglog(
        MFHelper.wn(niw_chi_input),
        np.real(1 / (1j * MFHelper.wn(niw_chi_input, config.sys.beta) + 0.000001) ** 2 * e_kin) * 2,
        "--",
        label="Asympt",
        ms=0,
    )
    axes[3].set_ylabel(r"$\Re \chi(i\omega_n)_{magn}$")
    axes[3].legend()
    axes[0].set_xlim(-1, 10)
    axes[1].set_xlim(-1, 10)
    plt.tight_layout()
    if save:
        plt.savefig(output_dir + f"/chi_dens_magn_" + name + ".png")
    if show:
        plt.show()
    else:
        plt.close()


def plot_nu_nup(
    obj: LocalFourPoint,
    orbs: np.ndarray | list | tuple = (0, 0, 0, 0),
    omega: int = 0,
    do_save: bool = True,
    output_dir: str = "./",
    name: str = "Name",
    colormap: str = "RdBu",
    show: bool = False,
) -> None:
    """
    Plots the four-point object for a given set of orbitals and a given bosonic frequency.
    """
    if np.abs(omega) > obj.niw:
        raise ValueError(f"Omega {omega} out of range.")
    if len(orbs) != 4:
        raise ValueError("'orbs' needs to be of size 4.")

    fig, axes = plt.subplots(ncols=2, figsize=(7, 3), dpi=251)
    axes = axes.flatten()
    wn_list = MFHelper.wn(obj.niw)
    wn_index = np.argmax(wn_list == omega)
    mat = obj.mat[orbs[0], orbs[1], orbs[2], orbs[3], wn_index, ...]
    vn = MFHelper.vn(obj.niv)
    im1 = axes[0].pcolormesh(vn, vn, mat.real, cmap=colormap)
    im2 = axes[1].pcolormesh(vn, vn, mat.imag, cmap=colormap)
    axes[0].set_title(r"$\Re$")
    axes[1].set_title(r"$\Im$")
    for ax in axes:
        ax.set_xlabel(r"$\nu_p$")
        ax.set_ylabel(r"$\nu$")
        ax.set_aspect("equal")
    fig.suptitle(name)
    fig.colorbar(im1, ax=(axes[0]), aspect=15, fraction=0.08, location="right", pad=0.05)
    fig.colorbar(im2, ax=(axes[1]), aspect=15, fraction=0.08, location="right", pad=0.05)
    plt.tight_layout()
    if do_save:
        plt.savefig(os.path.join(output_dir, f"{name}_w{omega}.png"))
    if show:
        plt.show()
    else:
        plt.close()


def plot_two_point_kx_ky(
    obj: LocalNPoint | IAmNonLocal,
    kx: float,
    ky: float,
    pi_shift: bool = True,
    name: str = "",
    orbs: np.ndarray | list | tuple = (0, 0),
    output_dir="./",
    cmap="RdBu",
    scatter=None,
    do_save: bool = True,
    show: bool = False,
):
    if len(orbs) != 2:
        raise ValueError("'orbs' needs to be of size 2.")

    mat = obj.shift_k_by_pi().mat if pi_shift else obj.mat

    niv = mat.shape[-1] // 2
    mat = mat[:, :, 0, orbs[0], orbs[1], niv]
    fig, axes = plt.subplots(ncols=2, figsize=(7, 3), dpi=500)
    axes = axes.flatten()
    im1 = axes[0].pcolormesh(kx, ky, mat.T.real, cmap=cmap)
    im2 = axes[1].pcolormesh(kx, ky, mat.T.imag, cmap=cmap)
    axes[0].set_title(r"$\Re$")
    axes[1].set_title(r"$\Im$")
    for ax in axes:
        ax.set_xlabel(r"$k_x$")
        ax.set_ylabel(r"$k_y$")
        ax.set_aspect("equal")
        add_afzb(ax=ax, kx=kx, ky=ky, lw=1.0, marker="")
    fig.suptitle(name)
    fig.colorbar(im1, ax=(axes[0]), aspect=15, fraction=0.08, location="right", pad=0.05)
    fig.colorbar(im2, ax=(axes[1]), aspect=15, fraction=0.08, location="right", pad=0.05)
    if scatter is not None:
        for ax in axes:
            colours = plt.cm.get_cmap(cmap)(np.linspace(0, 1, np.shape(scatter)[0]))
            ax.scatter(scatter[:, 0], scatter[:, 1], marker="o", c=colours)
    if do_save:
        plt.savefig(os.path.join(output_dir, f"{name}.png"))
    if show:
        plt.show()
    else:
        plt.close()


def plot_two_point_kx_ky_with_fs_points(
    obj: LocalNPoint | IAmNonLocal,
    kx: float,
    ky: float,
    pi_shift: bool = True,
    name: str = "",
    orbs: np.ndarray | list | tuple = (0, 0),
    output_dir="./",
    cmap="RdBu",
    do_save: bool = True,
    show: bool = False,
):
    mat = obj.mat[..., 0, orbs[0], orbs[1], obj.niv][: obj.nq[0] // 2, : obj.nq[1] // 2]
    fs_ind = find_zeros(mat)
    n_fs = np.shape(fs_ind)[0]
    fs_ind = fs_ind[: n_fs // 2]
    fs_points = np.stack((config.lattice.k_grid.kx[fs_ind[:, 0]], config.lattice.k_grid.ky[fs_ind[:, 1]]), axis=1)
    plot_two_point_kx_ky(obj, kx, ky, pi_shift, name, orbs, output_dir, cmap, fs_points, do_save, show)


def plot_gap_function(
    obj: GapFunction,
    kx: np.ndarray,
    ky: np.ndarray,
    name: str = "",
    orbs: np.ndarray | list | tuple = (0, 0),
    output_dir="./",
    cmap="RdBu",
    scatter=None,
    do_save: bool = True,
    show: bool = False,
):
    if len(orbs) != 2:
        raise ValueError("'orbs' needs to be of size 2.")

    gap = obj.shift_k_by_pi().mat
    niv_pp = gap.shape[-1] // 2
    gap = gap[:, :, 0, orbs[0], orbs[1], niv_pp - 1 : niv_pp + 1]
    gap = np.concatenate([gap, gap[0:1, :, ...]], axis=0)
    gap = np.concatenate([gap, gap[:, 0:1, ...]], axis=1)

    fig, axes = plt.subplots(ncols=2, figsize=(7, 3), dpi=500)
    axes = axes.flatten()
    im1 = axes[0].pcolormesh(kx, ky, gap[..., 0].T.real, cmap=cmap)
    im2 = axes[1].pcolormesh(kx, ky, gap[..., 1].T.real, cmap=cmap)
    axes[0].set_title(r"$\nu_{n=0}=\frac{\pi}{\beta}$")
    axes[1].set_title(r"$\nu_{n=-1}=-\frac{\pi}{\beta}$")
    for ax in axes:
        ax.set_xlabel(r"$k_x$")
        ax.set_ylabel(r"$k_y$")
        ax.set_aspect("equal")
        add_afzb(ax=ax, kx=kx, ky=ky, lw=1.0, marker="")
    fig.suptitle(f"{obj.channel.value}let")
    fig.colorbar(im1, ax=(axes[0]), aspect=15, fraction=0.08, location="right", pad=0.05)
    fig.colorbar(im2, ax=(axes[1]), aspect=15, fraction=0.08, location="right", pad=0.05)
    if scatter is not None:
        for ax in axes:
            colours = plt.cm.get_cmap(cmap)(np.linspace(0, 1, np.shape(scatter)[0]))
            ax.scatter(scatter[:, 0], scatter[:, 1], marker="o", c=colours)
    plt.tight_layout()
    if do_save:
        plt.savefig(os.path.join(output_dir, f"{name}.png"))
    if show:
        plt.show()
    else:
        plt.close()
