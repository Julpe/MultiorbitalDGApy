import numpy as np

import scdga.brillouin_zone as bz
from scdga.dga_logger import DgaLogger
from scdga.hamiltonian import Hamiltonian


class InteractionConfig:
    """
    Class to store the interaction parameters. Currently, we only require udd, vdd, jdd for local and Kanamori-type
    interactions. Other parameters are (currently) not used, however it is possible to extend the Hamiltonian class to
    use them when setting up the interaction matrix.
    """

    def __init__(self):
        self.udd: float = 0.0
        self.udp: float = 0.0
        self.upp: float = 0.0
        self.uppod: float = 0.0
        self.jdd: float = 0.0
        self.jdp: float = 0.0
        self.jpp: float = 0.0
        self.jppod: float = 0.0
        self.vdd: float = 0.0
        self.vpp: float = 0.0


class BoxConfig:
    """
    Class to store the box sizes. The main quantities are available in the core region. Due to explicit asymptotics,
    we can correct the core region by shell-region quantities. The full region is the sum of the core and shell regions
    and is there for convenience.
    """

    def __init__(self):
        self.niw_core: int = -1
        self.niv_core: int = -1
        self.niv_shell: int = 0
        self.niv_full: int = 0


class LatticeConfig:
    """
    Class to store the lattice parameters. The lattice is defined by the symmetries, the type of lattice, the input
    Hamiltonian and the input interaction. The k and q grids are defined by the number of k and q points and the
    symmetries of the lattice. For more information, have a look at the file dga_config.yaml.
    """

    def __init__(self):
        self.symmetries: list[bz.KnownSymmetries] = bz.two_dimensional_square_symmetries()
        self.type: str = "t_tp_tpp"
        self.er_input: str | list = ""
        self.interaction_type: str = ""
        self.interaction_input: str | list = ""
        self.nk: tuple[int, int, int] = (16, 16, 1)
        self.nq: tuple[int, int, int] = self.nk

        self.interaction: InteractionConfig = InteractionConfig()
        self.hamiltonian: Hamiltonian = Hamiltonian()
        self.k_grid: bz.KGrid = bz.KGrid(self.nk, self.symmetries)
        self.q_grid: bz.KGrid = bz.KGrid(self.nq, self.symmetries)


class SelfConsistencyConfig:
    """
    Class to store the self-consistency parameters. The self-consistency loop is controlled by the maximum number of
    iterations, the convergence criterion epsilon, the mixing parameter and the option to save the quantities throughout
    the self-consistency iteration. If previous_sc_path is set, the self-consistency will be started from the previous
    self-consistency iteration found in this path. We also added the possibility to change the mixing scheme from "linear" to
    (periodic) Pulay mixing, using a history of the last couple iterations if available.
    """

    def __init__(self):
        self.max_iter: int = 20
        self.save_iter: bool = True
        self.epsilon: float = 1e-4
        self.mixing: float = 0.2
        self.mixing_strategy: str = "linear"
        self.mixing_history_length: int = 3
        self.use_poly_fit = False
        self.previous_sc_path: str = "/."


class EliashbergConfig:
    """
    Class to store the configuration for the Eliashberg equation. It is defined by the option to perform the Eliashberg
    equation, the subfolder name and the option to save the pairing vertex.
    """

    def __init__(self):
        self.perform_eliashberg: bool = True
        self.save_pairing_vertex: bool = True
        self.n_eig: int = 2
        self.epsilon: float = 1e-4
        self.symmetry: str = "d-wave"
        self.subfolder_name: str = "Eliashberg"
        self.include_local_part: bool = True


class LambdaCorrectionConfig:
    """
    Class to store the configuration for the lambda correction. It is defined by the option to perform the lambda
    correction and the type of lambda correction.
    """

    def __init__(self):
        self.perform_lambda_correction: bool = True
        self.type: str = "spch"


class DmftConfig:
    """
    Class to store the DMFT parameters. The DMFT input is defined by the type of input, the input path, the filenames
    for the 1-particle and 2-particle data and the option to symmetrize the 2-particle data with respect to v and v'.
    """

    def __init__(self):
        self.type: str = "w2dyn"
        self.input_path: str = "/."
        self.fname_1p: str = "1p-data.hdf5"
        self.fname_2p: str = "g4iw_sym.hdf5"
        self.do_sym_v_vp: bool = True


class SystemConfig:
    """
    Class to store the system parameters. The system is defined by the number of bands, the inverse temperature beta, the
    chemical potential mu and the number of Matsubara frequencies n. The occupation numbers for the different bands are
    stored in the occ array.
    """

    def __init__(self):
        self.beta: float = 0.0
        self.mu: float = 0.0
        self.n: float = 0.0
        self.n_bands: int = 1
        self.occ: np.ndarray = np.ndarray(0)
        self.occ_k: np.ndarray = np.ndarray(0)
        self.occ_dmft: np.ndarray = np.ndarray(0)


class PolyFittingConfig:
    """
    Class to store the polynomial fitting parameters. The polynomial fitting is controlled by the order of the polynomial
    and the number of matsubara frequencies used for the polynomial fit.
    """

    def __init__(self):
        self.do_poly_fitting: bool = True
        self.n_fit: int = 4
        self.o_fit: int = 3


class OutputConfig:
    """
    Class to store the output parameters. What is output is specified by the properties.
    The output path is the path where some quantities are saved. If save_fq is set to True, the full ladder vertex
    will be saved.
    """

    def __init__(self):
        self.output_path: str = "./"
        self.save_quantities: bool = True
        self.do_plotting: bool = True
        self.plotting_path: str = "./Plots/"
        self.plotting_subfolder_name: str = "Plots"
        self.eliashberg_path: str = "./Eliashberg/"
        self.save_fq: bool = False


logger: DgaLogger
box: BoxConfig = BoxConfig()
lattice: LatticeConfig = LatticeConfig()
lambda_correction: LambdaCorrectionConfig = LambdaCorrectionConfig()
dmft: DmftConfig = DmftConfig()
sys: SystemConfig = SystemConfig()
output: OutputConfig = OutputConfig()
poly_fitting: PolyFittingConfig = PolyFittingConfig()
self_consistency: SelfConsistencyConfig = SelfConsistencyConfig()
eliashberg: EliashbergConfig = EliashbergConfig()
