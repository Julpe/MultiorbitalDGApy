import numpy as np
import matplotlib.pyplot as plt


if __name__ == "__main__":
    folder = "/home/julpe/Documents/DATA/Singleorb-DATA/N085/LDGA_Nk256_Nq256_wc100_vc60_vs0_4"

    siw_dmft = np.load(f"{folder}/sigma_dmft.npy")[0, 0, 0, 0, 0]
    # siw_dga_local = np.load(f"{folder}/siw_sde_full.npy")
    siw_dga_nonlocal = np.load(f"{folder}/sigma_dga_iteration_1.npy")
    # siw_dga_nonlocal_fit = np.load(f"{folder}/sigma_dga_fitted.npy")

    niv = siw_dga_nonlocal.shape[-1] // 2

    siw_dmft = siw_dmft[..., niv : niv + 80]
    # siw_dga_local = siw_dga_local[..., niv:]
    siw_dga_nonlocal = np.mean(siw_dga_nonlocal[..., niv : niv + 80], axis=0)[0, 0]
    # siw_dga_nonlocal_fit = np.mean(siw_dga_nonlocal_fit[..., niv : niv + 50], axis=0)[0, 0]

    plt.figure()
    plt.plot(siw_dga_nonlocal.real, label="real, dga")
    plt.plot(siw_dga_nonlocal.imag, label="imag, dga")
    # plt.plot(siw_dga_nonlocal_fit.real, label="real, dga_fit")
    # plt.plot(siw_dga_nonlocal_fit.imag, label="imag, dga_fit")
    plt.plot(siw_dmft.real, label="real, dmft")
    plt.plot(siw_dmft.imag, label="imag, dmft")
    plt.tight_layout()
    plt.legend()
    plt.grid()
    plt.show()
