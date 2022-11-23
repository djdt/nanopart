import numpy as np
import pytest
from numpy.lib import stride_tricks

from spcal import calc, poisson

# Force using custom
calc.BOTTLENECK_FOUND = False


def test_moving_mean():
    x = np.random.random(1000)
    v = stride_tricks.sliding_window_view(x, 9)
    assert np.all(np.isclose(np.mean(v, axis=1), calc.moving_mean(x, 9)))
    v = stride_tricks.sliding_window_view(x, 10)
    assert np.all(np.isclose(np.mean(v, axis=1), calc.moving_mean(x, 10)))


def test_moving_median():
    x = np.random.random(1000)
    v = stride_tricks.sliding_window_view(x, 9)
    assert np.all(np.isclose(np.median(v, axis=1), calc.moving_median(x, 9)))
    v = stride_tricks.sliding_window_view(x, 10)
    assert np.all(np.isclose(np.median(v, axis=1), calc.moving_median(x, 10)))


def test_moving_std():
    x = np.random.random(1000)
    v = stride_tricks.sliding_window_view(x, 9)
    assert np.all(np.isclose(np.std(v, axis=1), calc.moving_std(x, 9)))
    v = stride_tricks.sliding_window_view(x, 10)
    assert np.all(np.isclose(np.std(v, axis=1), calc.moving_std(x, 10)))


def test_calculate_limits_automatic():
    for lam in np.linspace(1.0, 100.0, 25):
        x = np.random.poisson(size=1000, lam=lam)
        limits = calc.calculate_limits(
            x, method="Automatic", sigma=3.0, error_rates=(0.05, 0.05)
        )
        assert limits[0] == ("Poisson" if lam < 50.0 else "Gaussian")


def test_calculate_limits():
    with pytest.raises(ValueError):
        calc.calculate_limits(np.array([]), "Automatic")

    x = np.random.poisson(lam=50.0, size=1000)

    method, params, limits = calc.calculate_limits(x, "Poisson")  # ld ~= 87
    assert method == "Poisson"
    assert params == {"α": 0.05, "β": 0.05}
    assert limits["lc"], limits["ld"] == poisson.formula_c(np.mean(x)) + np.mean(x)

    method, params, limits = calc.calculate_limits(x, "Gaussian", sigma=5.0)  # ld ~= 86
    assert method == "Gaussian"
    assert params == {"σ": 5.00}
    assert limits["lc"] == limits["ld"] == np.mean(x) + 5.0 * np.std(x)

    method, params, limits = calc.calculate_limits(x, "Gaussian Median", sigma=5.0)
    assert limits["lc"] == limits["ld"] == np.median(x) + 5.0 * np.std(x)

    method, params, limits = calc.calculate_limits(x, "Highest", sigma=5.0)
    assert method == "Poisson"

    method, params, limits = calc.calculate_limits(x, "Poisson", window=3)
    assert limits.size == x.size


def test_results_from_mass_response():
    detections = np.array([10.0, 20.0, 30.0])
    results = calc.results_from_mass_response(
        detections,
        background=1.0,
        density=0.01,
        lod=5.0,
        mass_fraction=0.5,
        mass_response=1e-3,
    )
    assert all(
        x in results
        for x in ["masses", "sizes", "background_size", "lod", "lod_mass", "lod_size"]
    )
    assert np.all(results["masses"] == detections * 1e-3 / 0.5)
    assert results["lod_mass"] == 5.0 * 1e-3 / 0.5
    # Rest are calculated as per particle module


def test_results_from_nebulisation_efficieny():
    detections = np.array([10.0, 20.0, 30.0])
    results = calc.results_from_nebulisation_efficiency(
        detections,
        background=1.0,
        density=0.01,
        lod=5.0,
        dwelltime=1e-3,
        efficiency=0.05,
        uptake=0.2,
        time=60.0,
        response=100.0,
        mass_fraction=0.5,
    )
    assert all(
        x in results
        for x in ["masses", "sizes", "background_size", "lod", "lod_mass", "lod_size"]
    )
    assert all(
        x in results
        for x in ["concentration", "number_concentration", "background_concentration"]
    )
    assert results["background_concentration"] == 1.0 / 100.0
    # Rest are calculated as per particle module
