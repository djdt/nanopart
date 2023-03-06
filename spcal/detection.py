"""Functions for detecting and classifying particles."""
from typing import Dict, Tuple

import numpy as np

from spcal.lib.spcalext import maxima


def accumulate_detections(
    y: np.ndarray,
    limit_accumulation: float | np.ndarray,
    limit_detection: float | np.ndarray,
    integrate: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns an array of accumulated detections.

    Contiguous regions above `limit_accumulation` that contain at least one value above
    `limit_detection` are summed or integrated (sum - `limit_accumulation`).

    Args:
        y: array
        limit_accumulation: minimum accumulation value(s)
        limit_detection: minimum detection value(s)
        integrate: integrate, otherwise sum

    Returns:
        summed detection regions
        labels of regions
        regions [starts, ends]
    """
    if np.any(limit_accumulation > limit_detection):
        raise ValueError("accumulate_detections: limit_accumulation > limit_detection.")

    regions = get_contiguous_regions(y, limit_accumulation)
    indicies = regions.ravel()
    if indicies.size > 0 and indicies[-1] == y.size:
        indicies = indicies[:-1]

    # Get maximum in each region
    detections = np.logical_or.reduceat(y > limit_detection, indicies)[::2]
    # Remove regions without a max value above detection limit
    regions = regions[detections]
    indicies = regions.ravel()
    if indicies.size > 0 and indicies[-1] == y.size:
        indicies = indicies[:-1]

    # Sum regions
    if integrate:
        sums = np.add.reduceat(y - limit_accumulation, indicies)[::2]
    else:
        sums = np.add.reduceat(y, indicies)[::2]

    # Create a label array of detections
    labels = label_regions(regions, y.size)

    return sums, labels, regions


def get_contiguous_regions(x: np.ndarray, limit: float | np.ndarray) -> np.ndarray:
    """Returns start and end points of regions in x that are greater than limit.
    Indexs to the start point and point after region.

    Args:
        x: array
        limit: minium value in regions

    Returns:
        regions [start, end]
    """

    # Get start and end positions of regions above accumulation limit
    diff = np.diff((x > limit).astype(np.int8), prepend=0)
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1)
    # Stack into pairs of start, end. If no final end position set it as end of array.
    if starts.size != ends.size:
        # -1 for reduceat
        ends = np.concatenate((ends, [diff.size]))  # type: ignore
    return np.stack((starts, ends), axis=1)


def label_regions(regions: np.ndarray, size: int) -> np.ndarray:
    """Label regions 1 ... regions.size. Unlabled areas are 0.

    Args:
        regions: from `get_contiguous_regions`
        size: size of array
    Returns:
        labeled regions
    """
    labels = np.zeros(size, dtype=np.int16)
    if regions.size == 0:
        return labels

    ix = np.arange(1, regions.shape[0] + 1)

    starts, ends = regions[:, 0], regions[:, 1]
    ends = ends[ends < size]
    # Set start, end pairs to +i, -i.
    labels[starts] = ix
    labels[ends] = -ix[: ends.size]  # possible over end
    # Cumsum to label
    labels = np.cumsum(labels)
    return labels


def detection_maxima(y: np.ndarray, regions: np.ndarray) -> np.ndarray:
    """Calculates the maxima of each region.
    Does not work with overlapping regions.

    Args:
        y: array
        regions: regions from `accumulate_detections`

    Returns:
        idx of maxima
    """

    # def maxima(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    #     idx = np.zeros(a.size, dtype=int)
    #     idx[b[1:]] = 1
    #     shift = (a.max() + 1) * np.cumsum(idx)
    #     sortidx = np.argsort(a + shift)
    #     return sortidx[np.append(b[1:], a.size) - 1] - b
    idx = maxima(y, regions)
    return idx


def combine_detections(
    sums: Dict[str, np.ndarray],
    labels: Dict[str, np.ndarray],
    regions: Dict[str, np.ndarray],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Computes the relative fraction of each element in each detection.
    Recalculates the start and end point of each peak from *all* element data.
    Regions that overlap will be combined into a single region. Fractions are calculated
    as the sum of all regions contained within each of the reclaculated regions.
    Each argument must have the same dictionaty keys.

    Args:
        sums: dict of detection counts, sizes, mass, ...
        labels: dict of labels from `accumulate_detections`
        regions: dict of regions from `accumulate_detections`

    Returns:
        dict of total sum per peak

    """
    if not all(k in regions.keys() for k in sums.keys()):  # pragma: no cover
        raise ValueError(
            "detection_element_combined: labels and regions must have all of sums keys."
        )
    names = list(sums.keys())

    # Get regions from all elements
    # Some regions may overlap, these will be combined
    any_label = np.zeros(labels[names[0]].size, dtype=np.int8)
    for name in names:
        any_label[labels[name] > 0] = 1

    all_regions = get_contiguous_regions(any_label, 0)
    any_label = label_regions(all_regions, any_label.size)

    # Init empty
    combined = np.empty(
        all_regions.shape[0], dtype=[(name, np.float64) for name in sums]
    )
    for name in names:
        # Positions in name's region that corresponds to the combined regions
        idx = (regions[name][:, 0] >= all_regions[:, 0, None]) & (
            regions[name][:, 1] <= all_regions[:, 1, None]
        )
        combined[name] = np.sum(np.where(idx, sums[name], 0), axis=1)

    return combined, any_label, all_regions
