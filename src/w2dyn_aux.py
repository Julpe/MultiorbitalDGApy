import h5py
import numpy as np


class W2dynFile:
    def __init__(self, fname=None):
        self._file = None
        self._fname = fname
        self.open()

    def __del__(self):
        self._file.close()

    def close(self):
        self._file.close()

    def open(self):
        self._file = h5py.File(self._fname, 'r')

    def atom_group(self, dmft_iter='dmft-last', atom=1):
        return dmft_iter + f'/ineq-{atom:03}'

    def get_niw(self):
        return self._file['.config'].attrs['qmc.niw']

    def get_nd(self, atom=1):
        return self._file['.config'].attrs[f'atoms.{atom:1}.nd']

    def get_natom(self):
        return self._file['.config'].attrs['general.nat']

    def get_nd_tot(self):
        natom = self.get_natom()
        nd_tot = 0
        for ia in range(natom):
            nd_tot += self.get_nd(atom=ia + 1)
        return nd_tot

    def get_beta(self):
        return self._file['.config'].attrs['general.beta']

    def get_mu(self, dmft_iter='dmft-last'):
        return self._file[dmft_iter + '/mu/value'][()]

    def get_totdens(self):
        return self._file['.config'].attrs['general.totdens']

    def get_udd(self, atom=1):
        return self._file['.config'].attrs[f'atoms.{atom:1}.udd']

    def get_siw_full(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/siw-full/value'][()]

    def get_giw_full(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/giw-full/value'][()]

    def get_g0iw_full(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/g0iw-full/value'][()]

    def get_siw(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/siw/value'][()]

    def get_giw(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/giw/value'][()]

    def get_g0iw(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/g0iw/value'][()]

    def get_smom_full(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/smom-full/value'][()]

    def get_dc_latt(self, dmft_iter='dmft-last'):
        return self._file[dmft_iter + '/dc-latt/value'][()]

    def get_dc(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/dc/value'][()]

    def get_occupation(self, dmft_iter='dmft-last', atom=1):
        return self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/occ/value'][()]

    def get_chi(self, dmft_iter='worm-last', atom=1, channel='dens'):
        chi_upup = self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/p2iw-worm/00001/value'][()]
        chi_updown = self._file[self.atom_group(dmft_iter=dmft_iter, atom=atom) + '/p2iw-worm/00002/value'][()]
        n = self.get_totdens()
        beta = self.get_beta()
        if channel == 'dens':
            niw = np.size(chi_upup) // 2
            wn = np.arange(-niw, niw + 1)
            chi_dens = chi_upup + chi_updown
            chi_dens[wn == 0] -= (n / 2 - 1) ** 2 * beta * 2
            return chi_dens
        elif channel == 'magn':
            return chi_upup - chi_updown
        else:
            raise ValueError(f'Provided channel ({channel}) is unknown. Channel must be dens/magn.')

    def load_dmft1p_w2dyn(self):

        beta = self.get_beta()
        u = self.get_udd()
        mu_dmft = self.get_mu()
        totdens = self.get_totdens()

        try:
            gloc = 0.5 * np.sum(self.get_giw_full(), axis=(0, 1, 2, 3))
        except:
            gloc = 0.5 * np.sum(self.get_giw(), axis=(0, 1))

        try:
            sloc = 0.5 * np.sum(self.get_siw_full(), axis=(0, 1, 2, 3))
        except:
            sloc = 0.5 * np.sum(self.get_siw(), axis=(0, 1))

        dmft1p = {
            'beta': beta,
            'u': u,
            'mu': mu_dmft,
            'n': totdens,
            'niv': sloc.shape[-1] // 2,
            'gloc': gloc,
            'sloc': sloc,
            'hartree': totdens * u / 2.0,
        }

        return dmft1p


class W2dynG4iwFile:
    def __init__(self, fname=None):
        self._fname = fname
        self._file = None
        self.open()

    def __del__(self):
        self._file.close()

    def close(self):
        self._file.close()

    def open(self):
        self._file = h5py.File(self._fname, 'r')

    def read_g2(self, ineq=1, channel=None, niw=0, niv=1, spinband=1):
        g2 = np.zeros((2 * niw + 1, 2 * niv, 2 * niv), dtype=complex)

        for wn in range(2 * niw + 1):
            g2[wn, :, :] = self._file[f'/ineq-{ineq:03}/' + channel + f'/{wn:05}/{spinband:05}/value'][()].T

        return g2

    def read_g2_full(self, ineq=1, channel=None, spinband=1):
        group_exists = True
        g2 = []
        wn = 0
        while group_exists:
            try:
                g2.append(self._file[f'/ineq-{ineq:03}/' + channel + f'/{wn:05}/{spinband:05}/value'][()].T)
                wn += 1
            except:
                group_exists = False
        g2 = np.array(g2)
        return g2