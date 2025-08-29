import os

import numpy as np
import pytest

from scdga import brillouin_zone
from scdga.brillouin_zone import KGrid
from scdga.hamiltonian import Hamiltonian, HoppingElement, InteractionElement


def test_hoppingelement_valid():
    he = HoppingElement([1, 0, 0], [1, 2], 3.5)
    assert he.r_lat == (1, 0, 0)
    assert np.all(he.orbs == np.array([1, 2]))
    assert he.value == 3.5


def test_hoppingelement_invalid_inputs():
    with pytest.raises(ValueError):
        HoppingElement([1, 0], [1, 2], 1.0)
    with pytest.raises(ValueError):
        HoppingElement([1, 0, 0], [0, 2], 1.0)
    with pytest.raises(ValueError):
        HoppingElement([0, 1, 0], [1, 2], "abc")


def test_interactionelement_valid():
    ie = InteractionElement([0, 0, 0], [1, 1, 1, 1], 10)
    assert np.all(ie.orbs == np.array([1, 1, 1, 1]))
    assert ie.value == 10


def test_interactionelement_invalid_inputs():
    with pytest.raises(ValueError):
        InteractionElement([0, 0], [1, 1, 1, 1], 10)
    with pytest.raises(ValueError):
        InteractionElement([0, 0, 0], [1, 1, 1], 10)
    with pytest.raises(ValueError):
        InteractionElement([0, 0, 0], [1, 1, 1, 1], "bad")


def test_add_kinetic_term():
    h = Hamiltonian()
    hops = [HoppingElement([1, 0, 0], [1, 1], 1.0)]
    h._add_kinetic_term(hops)
    assert np.allclose(h._er, [[[1.0]]])


def test_add_kinetic_term_rejects_local():
    h = Hamiltonian()
    hops = [HoppingElement([0, 0, 0], [1, 1], 1.0)]
    with pytest.raises(ValueError):
        h._add_kinetic_term(hops)


def test_add_interaction_term_local_and_nonlocal():
    h = Hamiltonian()
    inter = [
        InteractionElement([0, 0, 0], [1, 1, 1, 1], 5.0),
        InteractionElement([1, 0, 0], [1, 1, 1, 1], 2.0),
    ]
    h._add_interaction_term(inter)
    assert h._ur_local[0, 0, 0, 0] == 5.0
    assert np.any(h._ur_nonlocal != 0)


def test_single_band_interaction_sets_correct_u():
    h = Hamiltonian().single_band_interaction(4.0)
    assert np.isclose(h._ur_local[0, 0, 0, 0], 4.0)


def test_kanamori_interaction_defaults_1_band():
    h = Hamiltonian().kanamori_interaction(n_bands=1, udd=5.0, jdd=1.0)
    assert np.isclose(h._ur_local[0, 0, 0, 0], 5.0)


def test_kanamori_interaction_with_vdd_1_band():
    h = Hamiltonian().kanamori_interaction(n_bands=1, udd=5.0, jdd=1.0, vdd=2.0)
    assert np.isclose(h._ur_local[0, 0, 0, 0], 5.0)


def test_kanamori_interaction_with_vdd_2_band():
    params = {
        "udd": np.random.rand(),
        "jdd": np.random.rand(),
        "vdd": np.random.rand(),
    }

    h = Hamiltonian().kanamori_interaction(n_bands=2, **params)

    assert np.isclose(h._ur_local[0, 0, 0, 0], params["udd"])
    assert np.isclose(h._ur_local[1, 1, 1, 1], params["udd"])

    for i, j in [(0, 1), (1, 0)]:
        assert np.isclose(h._ur_local[i, j, i, j], params["jdd"])
        assert np.isclose(h._ur_local[i, j, j, i], params["jdd"])

    assert np.isclose(h._ur_local[0, 0, 1, 1], params["vdd"])
    assert np.isclose(h._ur_local[1, 1, 0, 0], params["vdd"])


def test_convham_2_orbs():
    h = Hamiltonian()
    h._er_r_grid = np.zeros((1, 1, 1, 3))
    h._er_r_weights = np.ones((1, 1))
    h._er = np.ones((1, 1, 1))
    kmesh = np.zeros((3, 1))
    out = h._convham_2_orbs(kmesh)
    assert np.allclose(out, 1.0)


def test_convham_4_orbs():
    h = Hamiltonian()
    h._ur_r_grid = np.zeros((1, 1, 1, 1, 1, 3))
    h._ur_r_weights = np.ones((1, 1))
    h._ur_nonlocal = np.ones((1, 1, 1, 1, 1))
    kmesh = np.zeros((3, 1))
    out = h._convham_4_orbs(kmesh)
    assert np.allclose(out, 1.0)


def test_set_and_get_ek():
    h = Hamiltonian()
    test_ek = np.array([[[[1.0]]]])
    h.set_ek(test_ek)
    assert np.allclose(h.get_ek(), test_ek)


def test_parse_elements_with_dicts():
    h = Hamiltonian()
    dicts = [{"r_lat": [1, 0, 0], "orbs": [1, 1], "value": 1.0}]
    parsed = h._parse_elements(dicts, HoppingElement)
    assert isinstance(parsed[0], HoppingElement)


def test_prepare_lattice_indices_and_orbs():
    h = Hamiltonian()
    elems = [HoppingElement([1, 0, 0], [1, 2], 1.0), HoppingElement([2, 0, 0], [2, 1], 1.5)]
    mapping, n_rp, n_orbs = h._prepare_lattice_indices_and_orbs(elems)
    assert isinstance(mapping, dict)
    assert n_rp == 2
    assert n_orbs == 2


def test_kinetic_one_band_2d_t_tp_tpp():
    h = Hamiltonian()
    h.kinetic_one_band_2d_t_tp_tpp(t=1.0, tp=0.5, tpp=0.25)
    # Check that nearest, next-nearest, and next-next-nearest hoppings are set
    values = h._er.flatten()
    assert np.isclose(values[0], -0.5)
    assert np.isclose(values[1], -1)
    assert np.isclose(values[2], -0.25)


def test_get_local_u_returns_localinteraction():
    h = Hamiltonian()
    h._ur_local = np.ones((1, 1, 1, 1))
    local_u = h.get_local_u()
    assert hasattr(local_u, "mat")
    assert local_u.mat.shape == (1, 1, 1, 1)


def test_get_vq_returns_interaction():
    h = Hamiltonian()
    h._ur_r_grid = np.zeros((1, 1, 1, 1, 1, 3))
    h._ur_r_weights = np.ones((1, 1))
    h._ur_nonlocal = np.ones((1, 1, 1, 1, 1))

    nk = (1, 1, 1)
    kg = brillouin_zone.KGrid(nk=nk, symmetries=[])
    vq = h.get_vq(kg)
    assert hasattr(vq, "mat")
    assert vq.mat.shape[-4:] == (1, 1, 1, 1)


def test_read_write_hr_hk_files():
    folder = f"{os.path.dirname(os.path.abspath(__file__))}/test_data/hamiltonian"
    k_grid = KGrid(nk=(24, 24, 1), symmetries=brillouin_zone.two_dimensional_square_symmetries())

    wannier_hr_oneband = Hamiltonian().read_hr_w2k(f"{folder}/wannier_hr_oneband.dat")
    ek = wannier_hr_oneband.get_ek(k_grid)

    assert wannier_hr_oneband._er.shape[-1] == 1
    assert wannier_hr_oneband._er.shape[-2] == 1

    assert ek.shape == (24, 24, 1, 1, 1)

    wannier_hk_oneband, _ = Hamiltonian().read_hk_w2k(f"{folder}/wannier_oneband_24x24.hk")
    ek_ref = wannier_hk_oneband.get_ek(k_grid).reshape(ek.shape)
    assert np.allclose(ek, ek_ref)

    wannier_hr_twoband = Hamiltonian().read_hr_w2k(f"{folder}/wannier_hr_twoband.dat")
    ek = wannier_hr_twoband.get_ek(k_grid)

    assert wannier_hr_twoband._er.shape[-1] == 2
    assert wannier_hr_twoband._er.shape[-2] == 2

    assert ek.shape == (24, 24, 1, 2, 2)

    wannier_hk_twoband, _ = Hamiltonian().read_hk_w2k(f"{folder}/wannier_twoband_24x24.hk")
    ek_ref = wannier_hk_twoband.get_ek(k_grid).reshape(ek.shape)
    assert np.allclose(ek, ek_ref)
