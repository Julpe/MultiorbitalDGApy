import gc
import itertools
import itertools as it
import logging

import h5py
import numpy as np


def index2component_general(num_bands: int, n: int, ind: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns the band and spin components corresponding to a compound index.
    """
    bandspin = np.zeros(n, dtype=np.int_)
    spin = np.zeros(n, dtype=np.int_)
    band = np.zeros(n, dtype=np.int_)
    ind_tmp = ind - 1
    tmp = (2 * num_bands) ** np.arange(n, -1, -1)

    for i in range(n):
        bandspin[i] = ind_tmp // tmp[i + 1]
        spin[i] = bandspin[i] % 2
        band[i] = bandspin[i] // 2
        ind_tmp -= tmp[i + 1] * bandspin[i]

    return bandspin, band, spin


def component2index_general(num_bands: int, bands: list, spins: list) -> int:
    """
    Computes a compound index from band and spin indices.
    """
    assert num_bands > 0, "Number of bands has to be set to non-zero positive integers."

    n_spins = 2
    dims_bs = 4 * (num_bands * n_spins,)
    dims_1 = (num_bands, n_spins)

    bandspin = np.ravel_multi_index((bands, spins), dims_1)
    return np.ravel_multi_index(bandspin, dims_bs) + 1


def index2component_band(num_bands: int, n: int, ind: int) -> list:
    """
    Computes only orbital indices from a compound index.
    """
    b = []
    ind_tmp = ind - 1
    for i in range(n):
        b.append(ind_tmp // (num_bands ** (n - i - 1)))
        ind_tmp = ind_tmp - b[i] * (num_bands ** (n - i - 1))
    return b


def component2index_band(num_bands: int, n: int, b: list) -> int:
    """
    Computes a compound index from orbital indices only.
    """
    ind = 1
    for i in range(n):
        ind = ind + num_bands ** (n - i - 1) * b[i]
    return ind


def get_worm_components(num_bands: int) -> list[int]:
    """
    Returns the list of worm components for a given number of bands, where only relevant spin combinations for the
    density and magnetic channels in the case of SU(2) symmetry are picked. If one wants to speed up the w2dynamics
    simulation, one can furthermore restrict the worm components to only allow spins = [0, 0, 0, 0], [0, 0, 1, 1] at
    the cost of more stochastic noise.
    """
    orbs = [list(orb) for orb in itertools.product(range(num_bands), repeat=4)]
    spins = [0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 1, 1], [1, 1, 0, 0], [1, 0, 0, 1], [0, 1, 1, 0]
    component_indices = []
    for o in orbs:
        for s in spins:
            component_indices.append(int(component2index_general(num_bands, o, s)))
    return sorted(component_indices)


def extract_g2_general(group_string: str, indices: list, file: h5py.File) -> tuple:
    """
    Extracts the g2 from the vertex file for given indices and group string.
    """
    print(f"Nonzero number of elements of g2 in dataset: {len(indices)} / {n_bands ** 4 * 2**4}")

    elements = np.array([file[f"{group_string}/{idx}/value"] for idx in indices])
    elements = elements.transpose(0, -1, 1, 2)

    # for some reason, the elements are stored transposed in vv' in symmetrize_old.py
    # therefore, every time we have to read or write, we have to transpose in vv' (this is a different transpose than above)
    elements = elements.transpose(0, 1, 3, 2)

    # construct G2dens and G2magn the output file
    bands, spins = zip(*(index2component_general(n_bands, 4, int(i))[1:3] for i in indices))

    # since we are SU(2) symmetric, we only have to pick out the elements where the spin is either
    # [0,0,0,0] or [1,1,1,1] for uu component, [0,0,1,1] or [1,1,0,0] for ud component and [0,1,1,0] or [1,0,0,1] for ud_bar component
    g2_uuuu, g2_dddd, g2_dduu, g2_uudd, g2_uddu, g2_duud = (
        np.zeros((n_bands, n_bands, n_bands, n_bands, 2 * niw + 1, 2 * niv, 2 * niv), dtype=np.complex64)
        for _ in range(6)
    )

    spin_dddd, spin_uuuu = [0, 0, 0, 0], [1, 1, 1, 1]
    spin_dduu, spin_uudd = [0, 0, 1, 1], [1, 1, 0, 0]
    spin_uddu, spin_duud = [1, 0, 0, 1], [0, 1, 1, 0]

    for a, b, c, d in it.product(range(n_bands), repeat=4):
        target_orbital = [a, b, c, d]
        print(f"Collecting G2 for orbitals {target_orbital} ...")

        idx_dddd, idx_dduu, idx_uudd, idx_uuuu, idx_uddu, idx_duud = (
            next(
                (
                    idx
                    for idx, band in enumerate(bands)
                    if np.array_equal(band, target_orbital) and np.array_equal(spins[idx], spin)
                ),
                None,
            )
            for spin in (spin_dddd, spin_dduu, spin_uudd, spin_uuuu, spin_uddu, spin_duud)
        )

        if None in (idx_dddd, idx_dduu, idx_uudd, idx_uuuu, idx_uddu, idx_duud):
            continue

        for g2, idx in zip(
            (g2_uuuu, g2_dddd, g2_dduu, g2_uudd, g2_uddu, g2_duud),
            (idx_uuuu, idx_dddd, idx_dduu, idx_uudd, idx_uddu, idx_duud),
        ):
            g2[a, b, c, d] = elements[idx]

    return g2_uuuu, g2_dddd, g2_dduu, g2_uudd, g2_uddu, g2_duud


def save_to_file(g2_list: list[np.ndarray], names: list[str], niw: int, n_bands: int):
    """
    Saves the given g2 to the output file.
    """
    assert len(g2_list) == len(names)
    for wn in range(2 * niw + 1):
        for i, j, k, l in it.product(range(n_bands), repeat=4):
            idx = component2index_band(n_bands, 4, [i, j, k, l])
            for g2, name in zip(g2_list, names):
                output_file[f"ineq-001/{name}/{wn:05}/{idx:05}/value"] = g2[i, j, k, l, wn].transpose()


def get_niw_niv(vertex_file, g4iw_groupstring, indices):
    """
    Determines niw and niv from the shape of the first element in the vertex file.
    """
    first_element_shape = vertex_file[f"{g4iw_groupstring}/{indices[0]}/value"].shape
    assert first_element_shape[0] % 2 == 0
    assert first_element_shape[-1] % 2 != 0
    return first_element_shape[-1] // 2, first_element_shape[0] // 2


if __name__ == "__main__":
    default_ph_filename = "Vertex.hdf5"
    default_output_filename = "g4iw_sym.hdf5"

    input_ph_filename = input(f"Enter the DMFT vertex file name (default = {default_ph_filename}): ")
    output_filename = input(f"Enter the output filename (default = {default_output_filename}): ")

    input_ph_filename = input_ph_filename if input_ph_filename else default_ph_filename
    output_filename = output_filename if output_filename else default_output_filename

    vertex_file_ph = h5py.File(input_ph_filename, "r")
    output_file = h5py.File(output_filename, "w")

    n_bands = int(vertex_file_ph[".config"].attrs[f"atoms.1.nd"]) + int(vertex_file_ph[".config"].attrs[f"atoms.1.np"])

    g4iw_ph_groupstring = "worm-last/ineq-001/g4iw-worm"

    try:
        indices_ph = list(vertex_file_ph[g4iw_ph_groupstring].keys())
    except KeyError:
        logging.getLogger().warning("No g4iw-worm group found in the PH input file. Aborting.")
        exit()

    # determination of niw and niv for ph channel
    niw, niv = get_niw_niv(vertex_file_ph, g4iw_ph_groupstring, indices_ph)

    print("Number of bands:", n_bands)
    print("Number of fermionic Matsubara frequencies:", niv)
    print("Number of bosonic Matsubara frequencies:", niw)

    print("Extracting G2ph ...")
    g2_uuuu_ph, g2_dddd_ph, g2_dduu_ph, g2_uudd_ph, g2_uddu_ph, g2_duud_ph = extract_g2_general(
        g4iw_ph_groupstring, indices_ph, vertex_file_ph
    )
    print("G2ph extracted. Calculating G2_dens and G2_magn for ph ...")
    g2_dens_ph = 0.5 * (g2_uuuu_ph + g2_dddd_ph + g2_uudd_ph + g2_dduu_ph)
    g2_magn_ph = 0.5 * (g2_uddu_ph + g2_duud_ph)

    del g2_uuuu_ph, g2_dddd_ph, g2_dduu_ph, g2_uudd_ph, g2_uddu_ph, g2_duud_ph
    gc.collect()
    print("G2_dens and G2_magn calculated. Writing to file ...")

    save_to_file([g2_dens_ph, g2_magn_ph], ["dens", "magn"], niw, n_bands)
    del g2_dens_ph, g2_magn_ph
    gc.collect()
    print("G2_dens and G2_magn successfully written to file.")

    output_file.close()
    vertex_file_ph.close()
    print("Done!")
