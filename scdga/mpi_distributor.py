import os

import h5py
import mpi4py.MPI as MPI
import numpy as np

import scdga.config as config


class MpiDistributor:
    """
    Distributes tasks among all available cores. Uses the first (q) dimension to slice the vertex data into chunks
    and sends it to all active MPI processes. Saves intermediate computational results in rank files. Each rank
    has their own instance of an MPI distributor and hdf5-file to avoid write conflicts.
    """

    def __init__(self, ntasks: int = 1, comm: MPI.Comm = None, name: str = ""):
        self._comm = comm
        self._ntasks = ntasks
        self._file = None
        self._my_slice = None
        self._sizes = None
        self._my_size = None
        self._slices = None

        self._distribute_tasks()

        if config.output.output_path is not None:
            # creates rank file if it does not exist
            self._fname = os.path.join(config.output.output_path, f"{name}_Rank{self.my_rank:05d}.hdf5")
            self._file = h5py.File(self._fname, "a")
            self._file.close()

    def __del__(self):
        """
        Destructor to close the hdf5 file if it is still open.
        """
        if self._file is not None:
            try:
                self.close_file()
            except:
                pass

    def __enter__(self):
        """
        Context manager to open the hdf5 file.
        """
        self.open_file()
        return self._file

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Context manager to close the hdf5 file.
        """
        if self._file:
            self.close_file()

    @property
    def comm(self) -> MPI.Comm:
        """
        Returns the MPI communicator.
        """
        return self._comm

    @property
    def is_root(self) -> bool:
        """
        Returns True if the current rank is the root rank (rank 0).
        """
        return self.my_rank == 0

    @property
    def ntasks(self) -> int:
        """
        Returns the total number of tasks to be distributed, i.e. in our case the total number of q-points in the
        irreducible Brillouin zone.
        """
        return self._ntasks

    @property
    def sizes(self) -> np.ndarray:
        """
        Returns the sizes of the chunks for each rank.
        """
        return self._sizes

    @property
    def my_rank(self) -> int:
        """
        Returns the rank of the current process.
        """
        return self._comm.Get_rank()

    @property
    def my_tasks(self) -> np.ndarray:
        """
        Returns the tasks assigned to the current rank, i.e. the q-points the current rank has to process.
        """
        return np.arange(0, self.ntasks)[self.my_slice]

    @property
    def mpi_size(self) -> int:
        """
        Returns the total number of MPI processes.
        """
        return self._comm.size

    @property
    def my_size(self) -> int:
        """
        Returns the number of tasks assigned to the current rank, i.e. the number of q-points the current rank has to
        process.
        """
        return self._my_size

    @property
    def my_slice(self) -> int:
        """
        Returns the slice object for the current rank to slice the full q-list to the q-list for that rank.
        """
        return self._my_slice

    def open_file(self):
        """
        Opens the hdf5 file for the current rank.
        """
        try:
            self._file = h5py.File(self._fname, "r+")
        except:
            pass

    def close_file(self):
        """
        Closes the hdf5 file for the current rank.
        """
        try:
            self._file.close()
        except:
            pass

    def delete_file(self):
        """
        Deletes the hdf5 file for the current rank.
        """
        try:
            os.remove(self._fname)
        except:
            pass

    def allgather(self, rank_result: np.ndarray = None) -> np.ndarray:
        """
        Gathers the numpy array from all ranks in the correct q-list order.
        """
        tot_shape = (self.ntasks,) + rank_result.shape[1:]
        tot_result = np.empty(tot_shape, rank_result.dtype)
        # tot_result[...] = np.nan
        other_dims = np.prod(rank_result.shape[1:])

        # The sizes argument needs the total number of elements rather than
        # just the first axis. The type argument is inferred.
        self.comm.Allgatherv(rank_result, [tot_result, self.sizes * other_dims])
        return tot_result

    def gather(self, rank_result: np.ndarray = None, root: int = 0) -> np.ndarray:
        """
        Gathers the numpy array from all ranks in the correct q-list order to the root rank.
        """
        tot_shape = (self.ntasks,) + rank_result.shape[1:]
        tot_result = np.empty(tot_shape, rank_result.dtype)
        other_dims = np.prod(rank_result.shape[1:])
        rank_result = np.ascontiguousarray(rank_result, dtype=rank_result.dtype)
        self.comm.Gatherv(rank_result, [tot_result, self.sizes * other_dims], root=root)
        return tot_result

    def scatter(self, full_data: np.ndarray = None, root: int = 0) -> np.ndarray:
        """
        Scatters the numpy array from the root rank to all ranks.
        """
        if full_data is not None:
            assert isinstance(full_data, np.ndarray), "full_data must be a numpy array"
            rest_shape = np.shape(full_data)[1:]
            data_type = full_data.dtype
        else:
            rest_shape = None
            data_type = None

        data_type = self.comm.bcast(data_type, root)
        rest_shape = self.comm.bcast(rest_shape, root)
        rank_shape = (self.my_size,) + rest_shape
        rank_data = np.empty(rank_shape, dtype=data_type)
        other_dims = np.prod(rank_data.shape[1:])
        # displacements = np.insert(np.cumsum(self.sizes[:-1]), 0, 0)
        self.comm.Scatterv([full_data, self.sizes * other_dims], rank_data, root=root)
        return rank_data

    def bcast(self, data, root=0):
        """
        Broadcasts data from the root rank to all other ranks.
        """
        return self.comm.bcast(data, root=root)

    def allreduce(self, rank_result=None) -> np.ndarray:
        """
        Reduces the numpy array from all ranks by summing it up on the first axis.
        """
        tot_result = np.zeros(np.shape(rank_result), dtype=rank_result.dtype)
        self.comm.Allreduce(rank_result, tot_result)
        return tot_result

    @staticmethod
    def create_distributor(ntasks: int, comm: MPI.Comm, name: str = "") -> "MpiDistributor":
        """
        Factory method to create an MpiDistributor instance.
        """
        if comm is None:
            comm = MPI.COMM_WORLD
        return MpiDistributor(ntasks=ntasks, comm=comm, name=name)

    def _distribute_tasks(self):
        """
        Distributes the tasks among all ranks. Calculates the sizes and slices for each rank.
        """
        n_per_rank = self.ntasks // self.mpi_size
        n_excess = self.ntasks - n_per_rank * self.mpi_size
        self._sizes = n_per_rank * np.ones(self.mpi_size, int)

        if n_excess:
            self._sizes[-n_excess:] += 1

        slice_ends = self._sizes.cumsum()
        self._slices = list(map(slice, slice_ends - self._sizes, slice_ends))
        self._my_size = self._sizes[self.my_rank]
        self._my_slice = self._slices[self.my_rank]
