import numpy as np
import pytest
from unittest.mock import patch

from moldga.local_four_point import LocalFourPoint
from moldga.local_n_point import LocalNPoint
from moldga.n_point_base import SpinChannel


def test_initializes_with_valid_parameters():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 2, 1, 1)
    assert obj.num_orbital_dimensions == 2
    assert obj.num_wn_dimensions == 1
    assert obj.num_vn_dimensions == 1
    assert obj.full_niw_range is True
    assert obj.full_niv_range is True


def test_raises_error_for_invalid_orbital_dimensions():
    mat = np.zeros((4, 4))
    with pytest.raises(AssertionError):
        LocalNPoint(mat, 3, 1, 1)


def test_raises_error_for_invalid_fermionic_dimensions():
    mat = np.zeros((4, 4))
    with pytest.raises(AssertionError):
        LocalNPoint(mat, 2, 1, 3)


def test_raises_error_for_invalid_bosonic_dimensions():
    mat = np.zeros((4, 4))
    with pytest.raises(AssertionError):
        LocalNPoint(mat, 2, 2, 1)


def test_initializes_with_partial_frequency_ranges():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 4, 0, 2, full_niw_range=False, full_niv_range=False)
    assert obj.full_niw_range is False
    assert obj.full_niv_range is False


def test_returns_correct_number_of_bands_for_higher_dimensional_matrix():
    mat = np.zeros((4, 4, 9, 10, 10))
    obj = LocalNPoint(mat, 2, 1, 2)
    assert obj.n_bands == 4


def test_returns_zero_bosonic_frequencies_when_no_wn_dimensions():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 2, 0, 1)
    assert obj.niw == 0


def test_calculates_correct_bosonic_frequencies_with_full_range():
    mat = np.zeros((4, 5, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=True)
    assert obj.niw == 2


def test_calculates_correct_bosonic_frequencies_with_half_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=False)
    assert obj.niw == 2


def test_returns_zero_fermionic_frequencies_when_no_vn_dimensions():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 2, 1, 0)
    assert obj.niv == 0


def test_calculates_correct_fermionic_frequencies_with_full_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niv_range=True)
    assert obj.niv == 5


def test_calculates_correct_fermionic_frequencies_with_half_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niv_range=False)
    assert obj.niv == 5


def test_raises_error_when_cutting_bosonic_frequencies_with_no_wn_dimensions():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 2, 0, 1)
    with pytest.raises(ValueError):
        obj.cut_niw(1)


def test_raises_error_when_cutting_more_bosonic_frequencies_than_available():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1)
    with pytest.raises(ValueError):
        obj.cut_niw(6)


def test_cuts_bosonic_frequencies_correctly_with_full_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=True)
    result = obj.cut_niw(2)
    assert result.mat.shape[-3] == 4


def test_cuts_bosonic_frequencies_correctly_with_half_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=False)
    result = obj.cut_niw(2)
    assert result.mat.shape[-3] == 4


def test_preserves_matrix_shape_when_cutting_with_no_vn_dimensions():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 0)
    result = obj.cut_niw(2)
    assert result.mat.shape == (4, 4, 5)


def test_raises_error_when_cutting_fermionic_frequencies_with_no_vn_dimensions():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 2, 1, 0)
    with pytest.raises(ValueError):
        obj.cut_niv(1)


def test_raises_error_when_cutting_more_fermionic_frequencies_than_available():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1)
    with pytest.raises(ValueError):
        obj.cut_niv(6)


def test_cuts_fermionic_frequencies_correctly_with_full_range():
    mat = np.zeros((4, 4, 10, 10))
    obj = LocalNPoint(mat, 2, 1, 2, full_niv_range=True)
    result = obj.cut_niv(3)
    assert result.mat.shape[-1] == 6
    assert result.mat.shape[-2] == 6


def test_cuts_fermionic_frequencies_correctly_with_half_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niv_range=False)
    result = obj.cut_niv(3)
    assert result.mat.shape[-1] == 3


def test_preserves_matrix_shape_when_cutting_with_no_wn_dimensions():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 0, 1)
    result = obj.cut_niv(2)
    assert result.mat.shape == (4, 4, 4)


def test_raises_error_when_cutting_both_frequencies_with_invalid_bosonic_cut():
    mat = np.zeros((4, 4, 10, 10))
    obj = LocalNPoint(mat, 2, 1, 2)
    with pytest.raises(ValueError):
        obj.cut_niw_and_niv(6, 3)


def test_raises_error_when_cutting_both_frequencies_with_invalid_fermionic_cut():
    mat = np.zeros((4, 4, 10, 10))
    obj = LocalNPoint(mat, 2, 1, 2)
    with pytest.raises(ValueError):
        obj.cut_niw_and_niv(3, 6)


def test_cuts_both_frequencies_correctly_with_full_ranges():
    mat = np.zeros((4, 4, 10, 10))
    obj = LocalNPoint(mat, 2, 1, 2, full_niw_range=True, full_niv_range=True)
    result = obj.cut_niw_and_niv(2, 3)
    assert result.mat.shape[-3] == 4
    assert result.mat.shape[-1] == 6
    assert result.mat.shape[-2] == 6


def test_cuts_both_frequencies_correctly_with_half_ranges():
    mat = np.zeros((1, 1, 1, 1, 5, 10, 10))
    obj = LocalNPoint(mat, 2, 1, 2, full_niw_range=False, full_niv_range=False)
    result = obj.cut_niw_and_niv(2, 3)
    assert result.mat.shape[-3] == 3
    assert result.mat.shape[-1] == 3
    assert result.mat.shape[-2] == 3


def test_raises_error_when_extending_with_no_fermionic_dimensions():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 2, 1, 0)
    with pytest.raises(ValueError):
        obj.extend_vn_to_diagonal()


def test_returns_self_when_extending_with_two_fermionic_dimensions():
    mat = np.zeros((4, 4, 4, 4, 4))
    obj = LocalNPoint(mat, 2, 1, 2)
    result = obj.extend_vn_to_diagonal()
    assert result is obj
    assert result.mat.shape == (4, 4, 4, 4, 4)


def test_extends_correctly_with_one_fermionic_dimension():
    mat = np.zeros((4, 4, 4, 4))
    obj = LocalNPoint(mat, 2, 1, 1)
    result = obj.extend_vn_to_diagonal()
    assert result is obj
    assert result.mat.shape == (4, 4, 4, 4, 4)
    assert np.allclose(result.mat[..., 0, 0], mat[..., 0], rtol=1e-2)
    assert np.allclose(result.mat[..., 0, 1], 0, rtol=1e-2)
    assert np.allclose(result.mat[..., 1, 0], 0, rtol=1e-2)
    assert np.allclose(result.mat[..., 1, 1], mat[..., 1], rtol=1e-2)
    assert np.allclose(result.mat[..., 2, 0], 0, rtol=1e-2)
    assert np.allclose(result.mat[..., 0, 2], 0, rtol=1e-2)
    assert np.allclose(result.mat[..., 2, 1], 0, rtol=1e-2)
    assert np.allclose(result.mat[..., 1, 2], 0, rtol=1e-2)
    assert np.allclose(result.mat[..., 2, 2], mat[..., 2], rtol=1e-2)


def test_raises_error_when_taking_diagonal_with_no_fermionic_dimensions():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 2, 1, 0)
    with pytest.raises(ValueError):
        obj.take_vn_diagonal()


def test_returns_self_when_taking_diagonal_with_one_fermionic_dimension():
    mat = np.zeros((4, 4, 4, 4))
    obj = LocalNPoint(mat, 2, 1, 1)
    result = obj.take_vn_diagonal()
    assert result is obj
    assert result.mat.shape == (4, 4, 4, 4)


def test_compresses_correctly_with_two_fermionic_dimensions():
    mat = np.zeros((4, 4, 4, 4, 4))
    for i in range(4):
        mat[..., i, i] = i + 1
    obj = LocalNPoint(mat, 2, 1, 2)
    result = obj.take_vn_diagonal()
    assert result is obj
    assert result.mat.shape == (4, 4, 4, 4)
    assert np.allclose(result.mat[..., 0], 1, rtol=1e-2)
    assert np.allclose(result.mat[..., 1], 2, rtol=1e-2)
    assert np.allclose(result.mat[..., 2], 3, rtol=1e-2)
    assert np.allclose(result.mat[..., 3], 4, rtol=1e-2)


def test_flips_matrix_along_valid_single_axis():
    mat = np.zeros((4, 4, 9, 10))
    obj = LocalNPoint(mat, 2, 1, 1)
    result = obj.flip_frequency_axis(axis=(-1,))
    assert np.allclose(result.mat, np.flip(mat, axis=-1), rtol=1e-2)


def test_flips_matrix_along_valid_multiple_axes():
    mat = np.zeros((4, 4, 9, 10))
    obj = LocalNPoint(mat, 2, 1, 1)
    result = obj.flip_frequency_axis(axis=(-2, -1))
    assert np.allclose(result.mat, np.flip(mat, axis=(-2, -1)), rtol=1e-2)


def test_raises_error_when_flipping_with_no_frequency_dimensions():
    mat = np.zeros((4, 4))
    obj = LocalNPoint(mat, 2, 0, 0)
    with pytest.raises(ValueError):
        obj.flip_frequency_axis(axis=(-1,))
        obj.flip_frequency_axis(axis=-1)


def test_raises_error_for_invalid_axis_outside_possible_range():
    mat = np.zeros((4, 4, 9, 10))
    obj = LocalNPoint(mat, 2, 1, 1)
    with pytest.raises(ValueError):
        obj.flip_frequency_axis(axis=(-3,))
        obj.flip_frequency_axis(axis=-3)
        obj.flip_frequency_axis(axis=(-3, -2))


def test_handles_single_axis_as_integer():
    mat = np.zeros((4, 4, 9, 10))
    obj = LocalNPoint(mat, 2, 1, 1)
    result = obj.flip_frequency_axis(axis=-1)
    assert np.allclose(result.mat, np.flip(mat, axis=-1), rtol=1e-2)


def test_aligns_frequency_dimensions_correctly_when_self_has_one_and_other_has_two_fermionic_dimensions():
    mat_self = np.zeros((4, 4, 4, 4))
    mat_other = np.zeros((4, 4, 4, 4, 4))
    obj_self = LocalNPoint(mat_self, 2, 1, 1)
    obj_other = LocalNPoint(mat_other, 2, 1, 2)
    result_other, self_extended, other_extended = obj_self._align_frequency_dimensions_for_operation(obj_other)
    assert self_extended is True
    assert other_extended is False
    assert obj_self.mat.shape == (4, 4, 4, 4, 4)
    assert obj_other.mat.shape == (4, 4, 4, 4, 4)
    assert result_other is obj_other


def test_aligns_frequency_dimensions_correctly_when_self_has_two_and_other_has_one_fermionic_dimensions():
    mat_self = np.zeros((4, 4, 4, 4, 4))
    mat_other = np.zeros((4, 4, 4, 4))
    obj_self = LocalNPoint(mat_self, 2, 1, 2)
    obj_other = LocalNPoint(mat_other, 2, 1, 1)
    result_other, self_extended, other_extended = obj_self._align_frequency_dimensions_for_operation(obj_other)
    assert self_extended is False
    assert other_extended is True
    assert obj_self.mat.shape == (4, 4, 4, 4, 4)
    assert obj_other.mat.shape == (4, 4, 4, 4, 4)
    assert result_other.mat.shape == (4, 4, 4, 4, 4)


def test_does_not_extend_frequency_dimensions_when_both_have_two_fermionic_dimensions():
    mat_self = np.zeros((4, 4, 4, 4, 4))
    mat_other = np.zeros((4, 4, 4, 4, 4))
    obj_self = LocalNPoint(mat_self, 2, 1, 2)
    obj_other = LocalNPoint(mat_other, 2, 1, 2)
    result_other, self_extended, other_extended = obj_self._align_frequency_dimensions_for_operation(obj_other)
    assert self_extended is False
    assert other_extended is False
    assert obj_self.mat.shape == (4, 4, 4, 4, 4)
    assert result_other.mat.shape == (4, 4, 4, 4, 4)


def test_does_not_extend_frequency_dimensions_when_both_have_one_fermionic_dimension():
    mat_self = np.zeros((4, 4, 4, 4))
    mat_other = np.zeros((4, 4, 4, 4))
    obj_self = LocalNPoint(mat_self, 2, 1, 1)
    obj_other = LocalNPoint(mat_other, 2, 1, 1)
    result_other, self_extended, other_extended = obj_self._align_frequency_dimensions_for_operation(obj_other)
    assert self_extended is False
    assert other_extended is False
    assert obj_self.mat.shape == (4, 4, 4, 4)
    assert result_other.mat.shape == (4, 4, 4, 4)


def test_returns_self_when_already_in_full_bosonic_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=True)
    result = obj.to_full_niw_range()
    assert result is obj
    assert result.mat.shape == mat.shape


def test_converts_to_half_bosonic_range_correctly():
    mat = np.random.rand(4, 4, 21, 20) + 1j * np.random.rand(4, 4, 21, 20)
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=True)
    result = obj.to_half_niw_range()
    assert result is obj
    assert result.mat.shape == (4, 4, 11, 20)
    assert np.allclose(result.mat, np.take(mat, np.arange(10, 21), axis=-2), rtol=1e-2)


def test_returns_self_when_already_in_half_bosonic_range():
    mat = np.random.rand(4, 4, 11, 10)
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=False)
    result = obj.to_half_niw_range()
    assert result is obj
    assert result.mat.shape == mat.shape


def test_saves_matrix_calls_to_full_niw_range_when_full_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=True)
    with patch.object(obj, "to_full_niw_range") as mock_full, patch.object(
        obj, "to_half_niw_range"
    ) as mock_half, patch("numpy.save") as mock_save:
        obj.save(output_dir="dir", name="full_range")
        mock_full.assert_called_once()
        mock_half.assert_called_once()
        mock_save.assert_called_once()


def test_saves_matrix_calls_to_half_niw_range_when_half_range():
    mat = np.zeros((4, 4, 10))
    obj = LocalNPoint(mat, 2, 1, 1, full_niw_range=False)
    with patch.object(obj, "to_full_niw_range") as mock_full, patch.object(
        obj, "to_half_niw_range"
    ) as mock_half, patch("numpy.save") as mock_save:
        obj.save(output_dir="dir", name="half_range")
        mock_full.assert_not_called()
        mock_half.assert_called_once()
        mock_save.assert_called_once()
