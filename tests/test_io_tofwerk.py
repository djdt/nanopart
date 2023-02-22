from pathlib import Path

import h5py
import numpy as np

from spcal.io.tofwerk import (
    calibrate_index_to_mass,
    calibrate_mass_to_index,
    integrate_tof_data,
    is_tofwerk_file,
)

path = Path(__file__).parent.joinpath("data/tofwerk_au_50nm.h5")


def test_is_tofwerk_file():
    assert is_tofwerk_file(path)
    assert not is_tofwerk_file(path.parent.joinpath("text_normal.csv"))
    assert not is_tofwerk_file(path.parent.joinpath("non_existant.h5"))


def test_calibration():
    with h5py.File(path, "r") as h5:
        mass = h5["FullSpectra"]["MassAxis"][:]
        idx = np.arange(mass.size)

        mode = 2
        ps = [2827.69757786, -5221.04079879, 0.49997113]

        mass_to_idx = np.around(calibrate_mass_to_index(mass, mode, ps), 0).astype(int)
        assert np.all(mass_to_idx == idx)

        idx_to_mass = calibrate_index_to_mass(idx, mode, ps)
        assert np.allclose(idx_to_mass, mass)


def test_integrate():
    with h5py.File(path, "r") as h5:
        data = integrate_tof_data(h5)
        peak_data = h5["PeakData"]["PeakData"][:]
        assert np.allclose(data, peak_data)
