import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Set, TextIO, Tuple

import numpy as np

from spcal import __version__
from spcal.result import SPCalResult

logger = logging.getLogger(__name__)


def import_single_particle_file(
    path: Path | str,
    delimiter: str = ",",
    columns: Tuple[int] | None = None,
    first_line: int = 1,
    new_names: Tuple[str] | None = None,
    convert_cps: float | None = None,
) -> Tuple[np.ndarray, List[str]]:
    """Imports data stored as text with elements in columns.

    Args:
        path: path to file
        delimiter: delimiting character between columns
        columns: which columns to import, deafults to all
        first_line: the first data (not header) line
        new_names: rename columns
        convert_cps: the dwelltime (in s) if data is stored as counts per second, else None

    Returns:
        data, structred array
        old_names, the original names used in text file
    """
    data = np.genfromtxt(
        path,
        delimiter=delimiter,
        usecols=columns,
        names=True,
        skip_header=first_line - 1,
        converters={0: lambda s: float(s.replace(",", "."))},
        invalid_raise=False,
    )
    assert data.dtype.names is not None

    names = list(data.dtype.names)
    if new_names is not None:
        data.dtype.names = new_names

    if convert_cps is not None:
        for name in data.dtype.names:
            data[name] = data[name] * convert_cps  # type: ignore

    return data, names


def export_single_particle_results(
    path: Path | str, results: Dict[str, SPCalResult]
) -> None:
    """Export results for elements to a file."""

    def write_if_exists(
        fp: TextIO,
        results: Dict[str, SPCalResult],
        fn: Callable[[SPCalResult], Any],
        prefix: str = "",
        postfix: str = "",
        delimiter: str = ",",
        format: str = "{:.8g}",
    ) -> None:
        values = [fn(result) for result in results.values()]
        if all(x is None for x in values):
            return
        text = delimiter.join(format.format(v) if v is not None else "" for v in values)
        fp.write(prefix + text + postfix + "\n")

    def write_header(fp: TextIO, first_result: SPCalResult) -> None:
        fp.write(f"# SPCal Export {__version__}\n")
        fp.write(f"# File,'{first_result.file}'\n")
        fp.write(f"# Acquisition events,{first_result.events}\n")
        fp.write("#\n")

    def write_inputs(fp: TextIO, results: Dict[str, SPCalResult]) -> None:
        input_units = {
            "cell_diameter": "m",
            "density": "kg/m3",
            "dwelltime": "s",
            "molar_mass": "kg/mol",
            "reponse": "counts/(kg/L)",
            "time": "s",
            "uptake": "L/s",
        }

        # first_result = next(iter(results.values()))

        # Todo: split into insutrment, sample, reference inputs?
        fp.write(f"# Options and inputs,{','.join(results.keys())}\n")
        # fp.write(f"# Dwelltime,{first_result.inputs['dwelltime']},s")
        # fp.write(f"# Uptake,{first_result.inputs['dwelltime']},s")

        input_set: Set[str] = set()  # All inputs across all elements
        for result in results.values():
            input_set.update(result.inputs.keys())

        for input in sorted(list(input_set)):
            values = [str(result.inputs.get(input, "")) for result in results.values()]
            fp.write(
                f"# {input.replace('_', ' ').capitalize()},"
                f"{','.join(values)},{input_units.get(input, '')}\n"
            )
        fp.write("#\n")

        def limit_name_and_params(r: SPCalResult):
            params = ";".join(f"{k}={v:.4g}" for k, v in r.limits.params.items())
            if r.limits.window_size != 0:
                if len(params) > 0:
                    params += ";"
                params += f"window={r.limits.window_size}"
            if len(params) == 0:
                return r.limits.name
            return r.limits.name + " (" + params + ")"

        write_if_exists(
            fp, results, limit_name_and_params, "# Limit method,", format="{}"
        )

        fp.write("#\n")

    def write_detection_results(fp: TextIO, results: Dict[str, SPCalResult]) -> None:
        fp.write(f"# Detection results,{','.join(results.keys())}\n")

        write_if_exists(fp, results, lambda r: r.number, "# Particle number,")
        write_if_exists(fp, results, lambda r: r.number_error, "# Number error,")
        write_if_exists(
            fp,
            results,
            lambda r: r.number_concentration,
            "# Number concentration,",
            postfix=",#/L",
        )
        write_if_exists(
            fp,
            results,
            lambda r: r.mass_concentration,
            "# Mass concentration,",
            postfix=",kg/L",
        )
        fp.write("#\n")

        # === Background ===
        write_if_exists(
            fp, results, lambda r: r.background, "# Background,", postfix=",counts"
        )
        # write_if_exists(
        #     fp, results, lambda r: r.asMass(r.background), "#,", postfix=",kg"
        # )
        write_if_exists(
            fp, results, lambda r: r.asSize(r.background), "#,", postfix=",m"
        )
        write_if_exists(
            fp,
            results,
            lambda r: r.background_error,
            "# Background error,",
            postfix=",counts",
        )
        write_if_exists(
            fp,
            results,
            lambda r: r.ionic_background,
            "# Ionic background,",
            postfix=",kg/L",
        )
        fp.write("#\n")

        fp.write(f"# Mean,{','.join(results.keys())}\n")

        def ufunc_or_none(r: SPCalResult, ufunc, key: str) -> float | None:
            if key not in r.detections:
                return None
            return ufunc(r.detections[key][r.indicies])

        for key, unit in zip(
            ["signal", "mass", "size", "cell_concentration"],
            ["counts", "kg", "m", "mol/L"],
        ):
            write_if_exists(
                fp,
                results,
                lambda r: (ufunc_or_none(r, np.mean, key)),
                "#,",
                postfix="," + unit,
            )
        fp.write(f"# Median,{','.join(results.keys())}\n")
        for key, unit in zip(
            ["signal", "mass", "size", "cell_concentration"],
            ["counts", "kg", "m", "mol/L"],
        ):
            write_if_exists(
                fp,
                results,
                lambda r: (ufunc_or_none(r, np.median, key)),
                "#,",
                postfix="," + unit,
            )

    def write_limits(fp: TextIO, results: Dict[str, SPCalResult]) -> None:
        fp.write(f"# Limits of detection,{','.join(results.keys())}\n")

        def limit_or_range(
            x: np.ndarray | float | None, format: str = "{:.8g}"
        ) -> str | None:
            if x is None:
                return None
            elif isinstance(x, float):
                return format.format(x)
            return format.format(x.min()) + " - " + format.format(x.max())

        write_if_exists(
            fp,
            results,
            lambda r: limit_or_range(r.limits.limit_of_detection),
            "#,",
            postfix=",counts",
            format="{}",
        )
        write_if_exists(
            fp,
            results,
            lambda r: limit_or_range(r.asMass(r.limits.limit_of_detection)),
            "#,",
            postfix=",kg",
            format="{}",
        )
        write_if_exists(
            fp,
            results,
            lambda r: limit_or_range(r.asSize(r.limits.limit_of_detection)),
            "#,",
            postfix=",m",
            format="{}",
        )
        write_if_exists(
            fp,
            results,
            lambda r: limit_or_range(
                r.asCellConcentration(r.limits.limit_of_detection)
            ),
            "#,",
            postfix=",mol/L",
            format="{}",
        )
        fp.write("#\n")

    def write_arrays(fp: TextIO, results: Dict[str, SPCalResult]) -> None:
        fp.write("# Raw detection data\n")
        # Output data
        data = []
        header_name = ""
        header_unit = ""

        for name, result in results.items():
            header_name += f",{name}"
            header_unit += ",counts"
            data.append(result.detections["signal"])
            for key, unit in [
                ("mass", "kg"),
                ("size", "m"),
                ("cell_concentration", "mol/L"),
            ]:
                if key in result.detections:
                    header_name += f",{name}"
                    header_unit += f",{unit}"
                    data.append(result.detections[key])

        data = np.stack(data, axis=1)

        fp.write(header_name[1:] + "\n")
        fp.write(header_unit[1:] + "\n")
        for line in data:
            fp.write(
                ",".join("" if x == 0.0 else "{:.8g}".format(x) for x in line) + "\n"
            )
        fp.write("#\n")

    path = Path(path)

    with path.open("w", encoding="utf-8") as fp:
        write_header(fp, next(iter(results.values())))
        write_inputs(fp, results)
        write_detection_results(fp, results)
        write_limits(fp, results)
        write_arrays(fp, results)
        fp.write("# End of export")
