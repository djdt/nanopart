"""Helper class for SPCal limits and thresholding."""
import logging
from statistics import NormalDist
from typing import Callable

import bottleneck as bn
import numpy as np

from spcal.calc import is_integer_or_near
from spcal.dists.util import (
    compound_poisson_lognormal_quantile,
    simulate_zt_compound_poisson,
)
from spcal.poisson import currie, formula_a, formula_c, stapleton_approximation

logger = logging.getLogger(__name__)


class SPCalLimit(object):
    """Limit and threshold class.

    Limits should be created through the class methods ``fromMethodString``,
    ``fromBest``, ``fromHighest``, ``fromGaussian`` and ``fromPoisson``.

    These functions will iteratively threshold for ``max_iters`` until a stable
    threshold is reached. Iteration can help threshold in samples with a very large
    number of particles to background. For no iteration, pass 0 to ``max_iters``.

    Windowed thresholding can be performed by passing a number greater than 0 to
    ``window_size``. This will calculate the signal mean and threshold for every
    point using data from only the surrounding window.

    Attributes:
        mean_signal: average signal
        detection_threshold: threshold for particle detection
        name: name of the filter / method
        params: filter / method parameters
    """

    def __init__(
        self,
        mean_background: float | np.ndarray,
        detection_threshold: float | np.ndarray,
        name: str,
        params: dict[str, float],
    ):
        self.mean_signal = mean_background
        self.detection_threshold = detection_threshold

        self.name = name
        self.params = params

    def __str__(self) -> str:
        pstring = ";".join(f"{k}={v}" for k, v in self.params.items() if v != 0)
        return f"{self.name} ({pstring})" if len(pstring) > 0 else self.name

    @property
    def detection_limit(self) -> float | np.ndarray:
        """The 'true' detection limit in counts.

        There may be values less than the ``detection_threshold`` due to
        subtraction of the ``signal_mean`` during calculations.
        """
        return self.detection_threshold - self.mean_signal

    def accumulationLimit(self, method: str) -> float | np.ndarray:
        method = method.lower()
        if method not in [
            "detection threshold",
            "half detection threshold",
            "signal mean",
        ]:  # pragma: no cover
            raise ValueError(f"invalid accumulation method '{method}'.")
        if method == "detection threshold":
            return self.detection_threshold
        elif method == "half detection threshold":
            return (self.mean_signal + self.detection_threshold) / 2.0
        else:
            return self.mean_signal

    @classmethod
    def fromMethodString(
        cls,
        method: str,
        responses: np.ndarray,
        poisson_kws: dict | None = None,
        gaussian_kws: dict | None = None,
        compound_kws: dict | None = None,
        window_size: int = 0,
        max_iters: int = 1,
    ) -> "SPCalLimit":
        """Takes a string and returns limit class.

        Valid stings are 'automatic', 'best', 'highest', 'compound', gaussian' and
        'poisson'.

        The CompoundPoisson method is seeded with a set number so will always give
        the same results.

        Args:
            method: method to use
            responses: single particle data
            compound_kws: key words for Compound Poisson thresholding
            poisson_kws: key words for Poisson thresholding
            gaussian_kws: key words for Gaussian thresholding
            window_size: size of window to use, 0 for no window
            max_iters: maximum iterations to try
        """
        if compound_kws is None:
            compound_kws = {}
        if gaussian_kws is None:
            gaussian_kws = {}
        if poisson_kws is None:
            poisson_kws = {}

        method = method.lower()
        if method in ["automatic", "best"]:
            return SPCalLimit.fromBest(
                responses,
                compound_kws=compound_kws,
                poisson_kws=poisson_kws,
                gaussian_kws=gaussian_kws,
                window_size=window_size,
                max_iters=max_iters,
            )
        elif method == "highest":
            return SPCalLimit.fromHighest(
                responses,
                poisson_kws=poisson_kws,
                gaussian_kws=gaussian_kws,
                window_size=window_size,
                max_iters=max_iters,
            )
        elif method.startswith("compound"):
            return SPCalLimit.fromCompoundPoisson(
                responses,
                alpha=compound_kws.get("alpha", 1e-6),
                single_ion_dist=compound_kws.get("single ion", None),
                sigma=compound_kws.get("sigma", 0.45),
                max_iters=max_iters,
            )
        elif method.startswith("gaussian"):
            return SPCalLimit.fromGaussian(
                responses,
                alpha=gaussian_kws.get("alpha", 1e-6),
                window_size=window_size,
                max_iters=max_iters,
            )
        elif method.startswith("poisson"):
            return SPCalLimit.fromPoisson(
                responses,
                alpha=poisson_kws.get("alpha", 0.001),
                formula=poisson_kws.get("formula", "formula c"),
                formula_kws=poisson_kws.get("params", None),
                window_size=window_size,
                max_iters=max_iters,
            )
        else:
            raise ValueError("fromMethodString: unknown method")

    @classmethod
    def fromCompoundPoisson(
        cls,
        responses: np.ndarray,
        alpha: float = 1e-6,
        single_ion_dist: np.ndarray | None = None,
        sigma: float = 0.45,
        size: int | None = None,
        max_iters: int = 1,
    ) -> "SPCalLimit":
        """Calculate threshold from simulated compound distribution.

        ToF data is a the sum of multiple Poisson accumulation events, each of which are
        an independant sample of lognormal like SIS distribution. This function will
        simulate the expected background and calculate the appropriate quantile for a
        given alpha value.

        Two methods are available, depending on the presence of ``single_ion_dist``. If
        passed, the background is simulated as a compound poisson using the SIS
        distribution. Otherwise an approximation is made that assumes the underlying SIS
        distribution is log-normal with a log stdev of ``sigma``. The approximation is
        much faster, but may be less accurate.

        A good value for ``sigma`` is 0.45, for both Nu Instruments and TOFWERK ToFs.

        Args:
            responses: single-particle data
            alpha: type I error rate
            single_ion: single ion distribution
            sigma: sigma of SIS, used for compound log-normal approx
            size: size of simulation, larger values will give more consistent quantiles
            max_iters: number of iterations, set to 1 for no iters

        References:
            Gundlach-Graham, A.; Lancaster, R. Mass-Dependent Critical Value Expressions
                for Particle Finding in Single-Particle ICP-TOFMS, Anal. Chem 2023
                https://doi.org/10.1021/acs.analchem.2c05243
            Gershman, D.; Gliese, U.; Dorelli, J.; Avanov, L.; Barrie, A.; Chornay, D.;
                MacDonald, E.; Hooland, M.l Giles, B.; Pollock, C. The parameterization
                of microchannel-plate-based detection systems, J. Geo. R. 2018
                https://doi.org/10.1002/2016JA022563
        """
        # sigma = 0.45  # Matches both Nu Instruments and TOFWERK SIAs
        if size is None:
            size = responses.size

        # Make sure weights are set correctly
        weights = None
        if single_ion_dist is not None:
            if single_ion_dist.ndim == 2:  # histogram of (bins, counts)
                weights = single_ion_dist[:, 1] / single_ion_dist[:, 1].sum()
                single_ion_dist = single_ion_dist[:, 0]
            average_single_ion = np.average(single_ion_dist, weights=weights)

        threshold, prev_threshold = np.inf, np.inf
        iters = 0
        while (np.all(prev_threshold > threshold) and iters < max_iters) or iters == 0:
            prev_threshold = threshold

            lam = bn.nanmean(responses[responses < threshold])
            if single_ion_dist is not None and single_ion_dist.size > 0:  # Simulate
                sim = simulate_zt_compound_poisson(
                    lam, single_ion_dist, weights=weights, size=size
                )
                sim /= average_single_ion

                p0 = np.exp(-lam)
                q0 = ((1.0 - alpha) - p0) / (1.0 - p0)
                if q0 < 0.0:  # pragma: no cover
                    threshold = 0.0
                else:
                    threshold = float(np.quantile(sim, q0))
            else:
                threshold = compound_poisson_lognormal_quantile(
                    (1.0 - alpha), lam, np.log(1.0) - 0.5 * sigma**2, sigma
                )
            iters += 1

        if iters == max_iters and max_iters != 1:  # pragma: no cover
            logger.warning("fromCompoundPoisson: reached max_iters")

        return cls(
            lam,
            threshold,
            name="CompoundPoisson",
            params={"alpha": alpha, "iters": iters - 1},
        )

    @classmethod
    def fromGaussian(
        cls,
        responses: np.ndarray,
        alpha: float = 1e-6,
        window_size: int = 0,
        max_iters: int = 1,
    ) -> "SPCalLimit":
        """Gaussian thresholding.

        Threshold is calculated as the mean + z * std deviation of the sample.

        Args:
            responses: single-particle data
            alpha: type I error rate
            window_size: size of window, 0 for no window
            max_iters: max iterations, 1 for no iteration
        """
        if responses.size == 0:  # pragma: no cover
            raise ValueError("fromGaussian: responses is size 0")

        z = NormalDist().inv_cdf(1.0 - alpha)

        threshold, prev_threshold = np.inf, np.inf
        iters = 0
        while (np.all(prev_threshold > threshold) and iters < max_iters) or iters == 0:
            prev_threshold = threshold

            if window_size == 0:  # No window
                mu = bn.nanmean(responses[responses < threshold])
                std = bn.nanstd(responses[responses < threshold])
            else:
                halfwin = window_size // 2
                pad = np.pad(
                    np.where(responses < threshold, responses, np.nan),
                    [halfwin, halfwin],
                    mode="reflect",
                )
                mu = bn.move_mean(pad, window_size, min_count=1)[2 * halfwin :]
                std = bn.move_std(pad, window_size, min_count=1)[2 * halfwin :]

            threshold = mu + std * z
            iters += 1

        if iters == max_iters and max_iters != 1:  # pragma: no cover
            logger.warning("fromPoisson: reached max_iters")

        return cls(
            mu,
            threshold,
            name="Gaussian",
            params={"alpha": alpha, "window": window_size, "iters": iters - 1},
        )

    @classmethod
    def fromPoisson(
        cls,
        responses: np.ndarray,
        alpha: float = 0.001,
        formula: str = "formula c",
        formula_kws: dict[str, float] | None = None,
        window_size: int = 0,
        max_iters: int = 1,
    ) -> "SPCalLimit":
        """Poisson thresholding.

        Calculate the limit of criticality using the supplied formula and params.

        Args:
            responses: single-particle data
            alpha: type I error rate
            formula: formula to use, {currie, formula a, formula c, stapleton}
            formula_kws: kws for formula
            window_size: size of window, 0 for no window
            max_iters: max iterations, 1 for no iteration
        """
        if responses.size == 0:  # pragma: no cover
            raise ValueError("fromPoisson: responses is size 0")

        formula = formula.lower()
        if formula == "currie":
            poisson_fn: Callable[
                [...], tuple[float | np.ndarray, float | np.ndarray]
            ] = currie
        elif formula == "formula a":
            poisson_fn = formula_a
        elif formula == "formula c":
            poisson_fn = formula_c
        elif formula.startswith("stapleton"):
            poisson_fn = stapleton_approximation
        else:  # pragma: no cover
            raise ValueError(f"unknown poisson limit formula: {formula}")

        if formula_kws is None:
            formula_kws = {}
        formula_kws["alpha"] = alpha

        threshold, prev_threshold = np.inf, np.inf
        iters = 0
        while (np.all(prev_threshold > threshold) and iters < max_iters) or iters == 0:
            prev_threshold = threshold
            if window_size == 0:  # No window
                mu = bn.nanmean(responses[responses < threshold])
            else:
                halfwin = window_size // 2
                pad = np.pad(
                    np.where(responses < threshold, responses, np.nan),
                    [halfwin, halfwin],
                    mode="reflect",
                )
                mu = bn.move_mean(pad, window_size, min_count=1)[2 * halfwin :]

            sc, _ = poisson_fn(mu, **formula_kws)
            threshold = np.ceil(mu + sc)
            iters += 1

        if iters == max_iters and max_iters != 1:  # pragma: no cover
            logger.warning("fromPoisson: reached max_iters")

        return cls(
            mu,
            threshold,
            name="Poisson",
            params={"alpha": alpha, "window": window_size, "iters": iters - 1},
        )

    @classmethod
    def fromBest(
        cls,
        responses: np.ndarray,
        compound_kws: dict | None = None,
        poisson_kws: dict | None = None,
        gaussian_kws: dict | None = None,
        window_size: int = 0,
        max_iters: int = 1,
    ) -> "SPCalLimit":
        """Returns 'best' threshold.

        Uses a Poisson threshold to calculate the mean of the background (signal below
        the limit of criticality). If this is above 10.0 then Gaussian thresholding is
        used instead.
        If data contains a significant fraction of non-integer values, it is treated as
        ToF data and a Compound Poisson limit is used instead of Poisson.

        Args:
            responses: single-particle data
            compound_kws: keywords for CompoundPoisson
            poisson_kws: keywords for Poisson
            gaussian_kws: keywords for Gaussian
            window_size: size of window, 0 for no window
            max_iters: max iterations, 0 for no iteration
        """
        if compound_kws is None:
            compound_kws = {}
        if poisson_kws is None:
            poisson_kws = {}
        if gaussian_kws is None:
            gaussian_kws = {}

        # Find if data is Poisson distributed
        nonzero_response = responses > 0.0
        low_responses = responses[nonzero_response & (responses <= 5.0)]
        # Less than 5% of nonzero values are below 5, equivilent to background of ~ 10
        if low_responses.size / np.count_nonzero(nonzero_response) < 0.05:
            return SPCalLimit.fromGaussian(
                responses,
                alpha=gaussian_kws.get("alpha", 1e-6),
                window_size=window_size,
                max_iters=max_iters,
            )
        # Quad data sometimes has a small offset from integer, almost always less than
        # 0.05 counts. If 75% of data is near integer we consider it Poisson, for ToF
        # data only ~ 10% will be.
        elif (
            np.count_nonzero(is_integer_or_near(low_responses, 0.05))
            / low_responses.size
            > 0.75
        ):
            return SPCalLimit.fromPoisson(
                responses,
                alpha=poisson_kws.get("alpha", 0.001),
                formula=poisson_kws.get("formula", "formula c"),
                formula_kws=poisson_kws.get("params", None),
                window_size=window_size,
                max_iters=max_iters,
            )
        else:
            return SPCalLimit.fromCompoundPoisson(
                responses,
                alpha=compound_kws.get("alpha", 1e-6),
                single_ion_dist=compound_kws.get("single ion", None),
                sigma=compound_kws.get("sigma", 0.45),
                max_iters=max_iters,
            )

    @classmethod
    def fromHighest(
        cls,
        responses: np.ndarray,
        poisson_kws: dict | None = None,
        gaussian_kws: dict | None = None,
        window_size: int = 0,
        max_iters: int = 1,
    ) -> "SPCalLimit":
        """Returns highest threshold.

        Calculates the Poisson and Gaussian thresholds and returns on with the highest
        detection threshold.

        Args:
            responses: single-particle data
            poisson_kws: keywords for Poisson
            gaussian_kws: keywords for Gaussian
            window_size: size of window, 0 for no window
            max_iters: max iterations, 0 for no iteration
        """
        if poisson_kws is None:
            poisson_kws = {}
        if gaussian_kws is None:
            gaussian_kws = {}
        poisson = SPCalLimit.fromPoisson(
            responses,
            alpha=poisson_kws.get("alpha", 0.001),
            formula=poisson_kws.get("formula", "formula c"),
            formula_kws=poisson_kws.get("params", None),
            window_size=window_size,
            max_iters=max_iters,
        )
        gaussian = SPCalLimit.fromGaussian(
            responses,
            alpha=gaussian_kws.get("alpha", 1e-6),
            window_size=window_size,
            max_iters=max_iters,
        )
        if np.mean(gaussian.detection_threshold) > np.mean(poisson.detection_threshold):
            return gaussian
        else:
            return poisson
