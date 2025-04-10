import argparse
import os

from mpi4py import MPI
from ruamel.yaml import YAML

import config
from config import *
from dga_logger import DgaLogger


class ConfigParser:
    """
    Parses the config file and builds the DgaConfig. It is then broadcasted to all processes.
    """

    def __init__(self):
        self._config_file = None

    def parse_config(self, comm: MPI.Comm = None, path: str = "./", name: str = "dga_config.yaml"):
        """
        Parses the config file and builds the DgaConfig. It is then broadcasted to all processes.
        The config file location can be specified with the path and name arguments when executing the main python file.
        """
        parser = argparse.ArgumentParser(
            prog="DGApy", description="Multi-orbital dynamical vertex approximation solver."
        )
        parser.add_argument("-c", "--config", nargs="?", default=name, type=str, help=" Config file name. ")
        parser.add_argument("-p", "--path", nargs="?", default=path, type=str, help=" Path to the config file. ")

        if comm.rank == 0:
            args = parser.parse_args()
            self._config_file = YAML().load(open(os.path.join(args.path, args.config)))

        config.logger = DgaLogger(comm)

        self._config_file = comm.bcast(self._config_file, root=0)
        config.current_rank = comm.rank

        self._build_config_from_file(self._config_file)
        return self

    def save_config_file(self, path: str = "./", name: str = "dga_config.yaml") -> None:
        """
        Provides a way to dump the current config file to a separate location.
        """
        with open(os.path.join(path, name), "w+") as file:
            YAML().dump(self._config_file, file)

    def _build_config_from_file(self, conf_file):
        """
        Builds the full DgaConfig from the config file.
        """
        config.dmft = self._build_dmft_config(conf_file)
        config.output = self._build_output_config(conf_file)
        config.self_consistency = self._build_self_consistency_config(conf_file)
        config.eliashberg = self._build_eliashberg_config(conf_file)
        config.poly_fitting = self._build_poly_fitting_config(conf_file)
        config.box = self._build_box_config(conf_file)
        config.lattice = self._build_lattice_config(conf_file)
        config.sys = self._build_system_config(conf_file)

    def _build_box_config(self, config_file) -> BoxConfig:
        """
        Builds the box config from the config file. Mainly concerned with the frequency boxes.
        """
        conf = BoxConfig()
        box_section = config_file["box_sizes"]

        conf.niw_core = self._try_parse(box_section, "niw_core", -1)
        conf.niv_core = self._try_parse(box_section, "niv_core", -1)
        conf.niv_shell = self._try_parse(box_section, "niv_shell", 0)
        if conf.niv_shell <= 0:
            config.logger.log_info(f"'niv_shell' is set to {conf.niv_shell}. No asymptotics will be used.")
            conf.niv_shell = 0
        conf.niv_full = conf.niv_core + conf.niv_shell

        return conf

    def _build_lattice_config(self, config_file) -> LatticeConfig:
        """
        Builds the lattice config from the config file. Mainly concerned with the lattice and interaction input.
        """
        conf = LatticeConfig()
        lattice_section = config_file["lattice"]

        conf.nk = self._try_parse(lattice_section, "nk", (16, 16, 1))

        if "nq" not in lattice_section:
            config.logger.log_info("'nq' not set in config. Setting 'nq' = 'nk'.")
            conf.nq = conf.nk
        else:
            conf.nq = self._try_parse(lattice_section, "nq", (16, 16, 1))

        symmetries = self._try_parse(lattice_section, "symmetries", "two_dimensional_square")
        conf.symmetries = bz.get_lattice_symmetries_from_string(symmetries)

        conf.k_grid = bz.KGrid(conf.nk, conf.symmetries)
        conf.q_grid = bz.KGrid(conf.nq, conf.symmetries)

        conf.type = self._try_parse(lattice_section, "type", "from_wannier90")
        conf.er_input = lattice_section["hr_input"]  # can be multiple types

        conf.interaction_type = self._try_parse(lattice_section, "interaction_type", "local_from_dmft")
        conf.interaction_input = lattice_section["interaction_input"]  # can be multiple types
        return conf

    def _build_dmft_config(self, config_file) -> DmftConfig:
        """
        Builds the DMFT config from the config file. Mainly concerned with input data.
        """
        conf = DmftConfig()
        dmft_section = config_file["dmft_input"]

        conf.type = self._try_parse(dmft_section, "type", "w2dyn")
        conf.input_path = self._try_parse(dmft_section, "input_path", "./")
        conf.fname_1p = self._try_parse(dmft_section, "fname_1p", "1p-data.hdf5")
        conf.fname_2p = self._try_parse(dmft_section, "fname_2p", "g4iw_sym.hdf5")
        conf.do_sym_v_vp = self._try_parse(dmft_section, "do_sym_v_vp", True)

        return conf

    def _build_system_config(self, _) -> SystemConfig:
        """
        Builds the system config. This will be filled outside by the main routine.
        """
        return SystemConfig()

    def _build_output_config(self, config_file) -> OutputConfig:
        """
        Builds the output config from the config file. Mainly concerned with plotting and saving quantities.
        """
        conf = OutputConfig()
        output_section = config_file["output"]

        conf.do_plotting = self._try_parse(output_section, "do_plotting", True)
        conf.save_quantities = self._try_parse(output_section, "save_quantities", True)
        conf.output_path = self._try_parse(output_section, "output_path", "./")

        if not conf.output_path or conf.output_path == "":
            config.logger.log_info(
                f"'output_path' not set in config. Setting 'output_path' = '{config.dmft.input_path}'."
            )
            conf.output_path = config.dmft.input_path

        return conf

    def _build_self_consistency_config(self, conf_file) -> SelfConsistencyConfig:
        """
        Builds the self-consistency config from the config file. Mainly concerned with the self-consistency loop.
        """
        conf = SelfConsistencyConfig()
        sc_section = conf_file["self_consistency"]

        conf.max_iter = self._try_parse(sc_section, "max_iter", 20)
        conf.save_iter = self._try_parse(sc_section, "save_iter", True)
        conf.epsilon = self._try_parse(sc_section, "epsilon", 1e-4)
        conf.mixing = self._try_parse(sc_section, "mixing", 0.3)
        conf.use_poly_fit = self._try_parse(sc_section, "use_poly_fit", True)
        conf.previous_sc_path = self._try_parse(sc_section, "previous_sc_path", "./")

        return conf

    def _build_eliashberg_config(self, conf_file) -> EliashbergConfig:
        """
        Builds the Eliashberg config from the config file. Mainly concerned with the Eliashberg equation.
        """
        conf = EliashbergConfig()
        eliashberg_section = conf_file["eliashberg"]

        conf.perform_eliashberg = self._try_parse(eliashberg_section, "perform_eliashberg", False)
        conf.save_pairing_vertex = self._try_parse(eliashberg_section, "save_pairing_vertex", True)
        conf.epsilon = self._try_parse(eliashberg_section, "epsilon", 1e-4)
        conf.max_iter = self._try_parse(eliashberg_section, "max_iter", 3)
        conf.subfolder_name = self._try_parse(eliashberg_section, "subfolder_name", "Eliashberg")

        return conf

    def _build_poly_fitting_config(self, conf_file) -> PolyFittingConfig:
        """
        Builds the poly fitting config from the config file. Mainly concerned with the polynomial fitting of the self-energy.
        """
        conf = PolyFittingConfig()
        poly_fitting_section = conf_file["poly_fitting"]

        conf.do_poly_fitting = self._try_parse(poly_fitting_section, "do_poly_fitting", True)
        conf.n_fit = self._try_parse(poly_fitting_section, "n_fit", 4)
        conf.o_fit = self._try_parse(poly_fitting_section, "o_fit", 3)

        return conf

    def _try_parse(self, config_section, key: str, default_value):
        """
        Tries to parse the value for the key in the config_section. If it fails, the default_value is returned. Parses
        the value to the type of the param default_value.
        """
        if key not in config_section:
            return default_value

        value_type = type(default_value)
        try:
            return value_type(config_section[key])
        except ValueError:
            config.logger.log_info(f"Could not parse value for {key}. Using default value: {default_value}.")
            return default_value
