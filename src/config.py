import numpy as np

import brillouin_zone as bz
from hamiltonian import Hamiltonian
from dga_logger import DgaLogger


class InteractionConfig:
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
    def __init__(self):
        self.niw_core: int = -1
        self.niv_core: int = -1
        self.niv_shell: int = 0
        self.niv_full: int = 0


class LatticeConfig:
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
    def __init__(self):
        self.max_iter: int = 20
        self.save_iter: bool = True
        self.epsilon: float = 1e-4
        self.mixing: float = 0.3


class DmftConfig:
    def __init__(self):
        self.type: str = "w2dyn"
        self.input_path: str = "/."
        self.fname_1p: str = "1p-data.hdf5"
        self.fname_2p: str = "g4iw_sym.hdf5"
        self.do_sym_v_vp: bool = True


class SystemConfig:
    def __init__(self):
        self.beta: float = 0.0
        self.mu: float = 0.0
        self.n: float = 0.0
        self.n_bands: int = 1
        self.occ: np.ndarray = np.ndarray(0)
        self.occ_dmft: int = 0


class OutputConfig:
    def __init__(self):
        self.do_plotting: bool = True
        self.save_quantities: bool = True
        self.output_path: str = "./"


current_rank: int = 0
logger: DgaLogger
box: BoxConfig = BoxConfig()
lattice: LatticeConfig = LatticeConfig()
dmft: DmftConfig = DmftConfig()
sys: SystemConfig = SystemConfig()
output: OutputConfig = OutputConfig()
self_consistency: SelfConsistencyConfig = SelfConsistencyConfig()
