from PySide6 import QtCore, QtGui, QtWidgets

import numpy as np
from pathlib import Path

from spcal.calc import (
    results_from_mass_response,
    results_from_nebulisation_efficiency,
)
from spcal.fit import fit_normal, fit_lognormal
from spcal.io import export_nanoparticle_results
from spcal.util import cell_concentration

from spcal.gui.graphs import ResultsView, graph_colors
from spcal.gui.iowidgets import ResultIOStack
from spcal.gui.inputs import SampleWidget, ReferenceWidget
from spcal.gui.options import OptionsWidget
from spcal.gui.units import UnitsWidget

from typing import Dict, Optional, List, Tuple


class ResultIOWidget(QtWidgets.QWidget):
    optionsChanged = QtCore.Signal(str)

    signal_units = {"counts": 1.0}
    size_units = {"nm": 1e-9, "μm": 1e-6, "m": 1.0}
    mass_units = {
        "ag": 1e-21,
        "fg": 1e-18,
        "pg": 1e-15,
        "ng": 1e-12,
        "μg": 1e-9,
        "g": 1e-3,
        "kg": 1.0,
    }
    molar_concentration_units = {
        "amol/L": 1e-18,
        "fmol/L": 1e-15,
        "pmol/L": 1e-12,
        "nmol/L": 1e-9,
        "μmol/L": 1e-6,
        "mmol/L": 1e-3,
        "mol/L": 1.0,
    }
    concentration_units = {
        "fg/L": 1e-18,
        "pg/L": 1e-15,
        "ng/L": 1e-12,
        "μg/L": 1e-9,
        "mg/L": 1e-6,
        "g/L": 1e-3,
        "kg/L": 1.0,
    }

    def __init__(self, name: str, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.name = name

        self.outputs = QtWidgets.QGroupBox("Outputs")
        self.outputs.setLayout(QtWidgets.QHBoxLayout())

        self.count = QtWidgets.QLineEdit()
        self.count.setReadOnly(True)
        self.number = UnitsWidget(
            {"#/L": 1.0, "#/ml": 1e3},
            default_unit="#/L",
            formatter=".0f",
        )
        self.number.setReadOnly(True)
        self.conc = UnitsWidget(
            self.concentration_units,
            default_unit="ng/L",
        )
        self.conc.setReadOnly(True)
        self.background = UnitsWidget(
            self.concentration_units,
            default_unit="ng/L",
        )
        self.background.setReadOnly(True)

        self.lod = UnitsWidget(
            self.size_units,
            default_unit="nm",
        )
        self.lod.setReadOnly(True)
        self.mean = UnitsWidget(
            self.size_units,
            default_unit="nm",
        )
        self.mean.setReadOnly(True)
        self.median = UnitsWidget(
            self.size_units,
            default_unit="nm",
        )
        self.median.setReadOnly(True)

        layout_outputs_left = QtWidgets.QFormLayout()
        layout_outputs_left.addRow("No. Detections:", self.count)
        layout_outputs_left.addRow("No. Concentration:", self.number)
        layout_outputs_left.addRow("Concentration:", self.conc)
        layout_outputs_left.addRow("Ionic Background:", self.background)

        layout_outputs_right = QtWidgets.QFormLayout()
        layout_outputs_right.addRow("Mean:", self.mean)
        layout_outputs_right.addRow("Median:", self.median)
        layout_outputs_right.addRow("LOD:", self.lod)

        self.outputs.layout().addLayout(layout_outputs_left)
        self.outputs.layout().addLayout(layout_outputs_right)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.outputs)

        self.setLayout(layout)

    def clearOutputs(self) -> None:
        self.mean.setBaseValue(None)
        self.mean.setBaseError(None)
        self.median.setBaseValue(None)
        self.lod.setBaseValue(None)

        self.count.setText("")
        self.number.setBaseValue(None)
        self.number.setBaseError(None)
        self.conc.setBaseValue(None)
        self.conc.setBaseError(None)
        self.background.setBaseValue(None)
        self.background.setBaseError(None)

    def updateOutputs(
        self,
        values: np.ndarray,
        units: Dict[str, float],
        lod: np.ndarray,
        count: float,
        count_error: float,
        conc: Optional[float] = None,
        number_conc: Optional[float] = None,
        background_conc: Optional[float] = None,
        background_error: Optional[float] = None,
    ) -> None:

        mean = np.mean(values)
        median = np.median(values)
        std = np.std(values)
        mean_lod = np.mean(lod)

        for te in [self.mean, self.median, self.lod]:
            te.setUnits(units)

        self.mean.setBaseValue(mean)
        self.mean.setBaseError(std)
        self.median.setBaseValue(median)
        self.lod.setBaseValue(mean_lod)

        unit = self.mean.setBestUnit()
        self.median.setUnit(unit)
        self.lod.setUnit(unit)

        relative_error = count / count_error
        self.count.setText(f"{count} ± {count_error:.1f}")
        self.number.setBaseValue(number_conc)
        if number_conc is not None:
            self.number.setBaseError(number_conc * relative_error)
        else:
            self.number.setBaseError(None)
        self.number.setBestUnit()

        self.conc.setBaseValue(conc)
        if conc is not None:
            self.conc.setBaseError(conc * relative_error)
        else:
            self.conc.setBaseError(None)
        unit = self.conc.setBestUnit()

        self.background.setBaseValue(background_conc)
        if background_conc is not None and background_error is not None:
            self.background.setBaseError(background_conc * background_error)
        else:
            self.background.setBaseError(None)
        self.background.setUnit(unit)


class ResultsWidget(QtWidgets.QWidget):
    signal_units = {"counts": 1.0}
    size_units = {"nm": 1e-9, "μm": 1e-6, "m": 1.0}
    mass_units = {
        "ag": 1e-21,
        "fg": 1e-18,
        "pg": 1e-15,
        "ng": 1e-12,
        "μg": 1e-9,
        "g": 1e-3,
        "kg": 1.0,
    }
    molar_concentration_units = {
        "amol/L": 1e-18,
        "fmol/L": 1e-15,
        "pmol/L": 1e-12,
        "nmol/L": 1e-9,
        "μmol/L": 1e-6,
        "mmol/L": 1e-3,
        "mol/L": 1.0,
    }
    concentration_units = {
        "fg/L": 1e-18,
        "pg/L": 1e-15,
        "ng/L": 1e-12,
        "μg/L": 1e-9,
        "mg/L": 1e-6,
        "g/L": 1e-3,
        "kg/L": 1.0,
    }

    def __init__(
        self,
        options: OptionsWidget,
        sample: SampleWidget,
        reference: ReferenceWidget,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)

        self.options = options
        self.sample = sample
        self.reference = reference

        self.nbins = "auto"
        self.result: Dict[str, dict] = {}

        self.graph = ResultsView()

        self.io = ResultIOStack()

        self.fitmethod = QtWidgets.QComboBox()
        self.fitmethod.addItems(["None", "Normal", "Lognormal"])
        self.fitmethod.setCurrentText("Lognormal")

        self.fitmethod.currentIndexChanged.connect(self.drawGraph)

        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["Signal", "Mass (kg)", "Size (m)", "Conc. (mol/L)"])
        self.mode.setItemData(0, "Accumulated detection signal.", QtCore.Qt.ToolTipRole)
        self.mode.setItemData(
            1, "Particle mass, requires calibration.", QtCore.Qt.ToolTipRole
        )
        self.mode.setItemData(
            2, "Particle size, requires calibration.", QtCore.Qt.ToolTipRole
        )
        self.mode.setItemData(
            3,
            "Intracellular concentration, requires cell diameter and analyte molarmass.",
            QtCore.Qt.ToolTipRole,
        )
        self.mode.setCurrentText("Signal")
        self.mode.currentIndexChanged.connect(lambda: self.updateOutputs(None))
        self.mode.currentIndexChanged.connect(self.drawGraph)

        self.label_file = QtWidgets.QLabel()

        self.button_export = QtWidgets.QPushButton("Export Results")
        self.button_export.pressed.connect(self.dialogExportResults)

        self.button_export_image = QtWidgets.QPushButton("Save Image")
        self.button_export_image.pressed.connect(self.dialogExportImage)

        self.io.layout_top.insertWidget(
            0, QtWidgets.QLabel("Mode:"), 0, QtCore.Qt.AlignLeft
        )
        self.io.layout_top.insertWidget(1, self.mode, 0, QtCore.Qt.AlignLeft)
        self.io.layout_top.insertStretch(2, 1)

        layout_filename = QtWidgets.QHBoxLayout()
        layout_filename.addWidget(self.button_export, 0, QtCore.Qt.AlignLeft)
        layout_filename.addWidget(self.label_file, 1)

        layout_chart_options = QtWidgets.QHBoxLayout()
        layout_chart_options.addWidget(self.button_export_image)
        layout_chart_options.addStretch(1)
        layout_chart_options.addWidget(QtWidgets.QLabel("Fit:"), 0)
        layout_chart_options.addWidget(self.fitmethod)

        layout_main = QtWidgets.QVBoxLayout()
        # layout_outputs.addLayout(layout_filename)
        layout_main.addWidget(self.io)
        layout_main.addWidget(self.graph)

        layout = QtWidgets.QHBoxLayout()
        layout.addLayout(layout_main, 1)
        self.setLayout(layout)

    def dialogExportResults(self) -> None:
        file, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export", "", "CSV Documents (*.csv)"
        )
        if file != "":
            export_nanoparticle_results(Path(file), self.result)

    def dialogExportImage(self) -> None:
        file, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Image", "", "PNG Images (*.png)"
        )
        # if file != "":
        #     self.chartview.saveToFile(file)

    def asBestUnit(
        self, data: np.ndarray, current_unit: str = ""
    ) -> Tuple[np.ndarray, float, str]:
        units = {
            "z": 1e-21,
            "a": 1e-18,
            "f": 1e-15,
            "p": 1e-12,
            "n": 1e-9,
            "μ": 1e-6,
            "m": 1e-3,
            "": 1.0,
            "k": 1e3,
            "M": 1e6,
        }

        data = data * units[current_unit]

        mean = np.mean(data)
        pwr = 10 ** int(np.log10(mean) - (1 if mean < 1.0 else 0))

        vals = list(units.values())
        names = list(units.keys())
        idx = np.searchsorted(list(units.values()), pwr) - 1

        return data / vals[idx], vals[idx] / units[current_unit], names[idx]

    def readyForResults(self) -> bool:
        if not self.options.isComplete():
            return False
        if not self.sample.isComplete():
            return False

        method = self.options.efficiency_method.currentText()
        if method != "Manual Input" and not self.reference.isComplete():
            return False
        return True

    def drawGraph(self) -> None:
        self.graph.clear()
        mode = self.mode.currentText()

        if mode == "Signal":
            label, unit = "Intensity", None
        elif mode == "Mass (kg)":
            label, unit = "Mass", "g"
        elif mode == "Size (m)":
            label, unit = "Size", "m"
        elif mode == "Conc. (mol/L)":
            label, unit = "Concentration", "mol/L"
        else:
            raise ValueError("drawGraph: unknown mode.")

        self.graph.xaxis.setLabel(label, unit)

        graph_data = {}
        for name in self.result:
            if mode == "Signal":
                graph_data[name] = self.result[name]["detections"]
            elif mode == "Mass (kg)" and "masses" in self.result[name]:
                graph_data[name] = self.result[name]["masses"] * 1000  # convert to gram
            elif mode == "Size (m)" and "sizes" in self.result[name]:
                graph_data[name] = self.result[name]["sizes"]
            elif mode == "Conc. (mol/L)" and "cell_concentrations" in self.result[name]:
                graph_data[name] = self.result[name]["cell_concentrations"]
            else:
                continue

        # median 'sturges' bin width
        bin_width = np.median(
            [
                np.ptp(graph_data[name]) / (np.log2(graph_data[name].size) + 1)
                for name in graph_data
            ]
        )

        for name, color in zip(graph_data, graph_colors):
            bins = np.arange(
                graph_data[name].min(), graph_data[name].max() + bin_width, bin_width
            )
            bins -= bins[0] % bin_width  # align bins
            color = QtGui.QColor(color)
            color.setAlpha(128)
            self.graph.drawData(
                name, graph_data[name], bins=bins, brush=QtGui.QBrush(color)
            )

    # def updateChartFit(self, hist: np.ndarray, bins: np.ndarray, size: int) -> None:
    #     method = self.fitmethod.currentText()
    #     if method == "None":
    #         self.chart.fit.clear()
    #         self.chart.label_fit.setVisible(False)
    #         return

    #     # Convert to density
    #     binwidth = bins[1] - bins[0]
    #     hist = hist / binwidth / size

    #     if method == "Normal":
    #         fit = fit_normal(bins[1:], hist)[0]
    #     elif method == "Lognormal":
    #         fit = fit_lognormal(bins[1:], hist)[0]
    #     else:
    #         raise ValueError(f"Unknown fit type '{method}'.")

    #     # Convert from density
    #     fit = fit * binwidth * size

    #     self.chart.setFit(bins[1:], fit)
    #     self.chart.fit.setName(method)
    #     self.chart.label_fit.setVisible(True)

    def updateOutputs(self, _name: Optional[str] = None) -> None:
        mode = self.mode.currentText()
        if _name is None or _name == "Overlay":
            names = list(self.sample.detections.keys())
        else:
            names = [_name]

        for name in names:
            if mode == "Signal":
                units = self.signal_units
                values = self.result[name]["detections"]
                lod = self.result[name]["lod"]
            elif mode == "Mass (kg)" and "masses" in self.result[name]:
                units = self.mass_units
                values = self.result[name]["masses"]
                lod = self.result[name]["lod_mass"]
            elif mode == "Size (m)" and "sizes" in self.result[name]:
                units = self.size_units
                values = self.result[name]["sizes"]
                lod = self.result[name]["lod_size"]
            elif mode == "Conc. (mol/L)" and "cell_concentrations" in self.result[name]:
                units = self.molar_concentration_units
                values = self.result[name]["cell_concentrations"]
                lod = self.result[name]["lod_cell_concentration"]
            else:
                self.io[name].clearOutputs()
                continue

            self.io[name].updateOutputs(
                values,
                units,
                lod,
                count=self.result[name]["detections"].size,
                count_error=self.result[name]["detections_std"],
                conc=self.result[name].get("concentration", None),
                number_conc=self.result[name].get("number_concentration", None),
                background_conc=self.result[name].get("background_concentration", None),
                background_error=self.result[name]["background_std"]
                / self.result[name]["background"],
            )

    def updateResults(self, _name: Optional[str] = None) -> None:
        method = self.options.efficiency_method.currentText()

        if _name is None or _name == "Overlay":
            names = list(self.sample.detections.keys())
        else:
            names = [_name]

        for name in names:
            trim = self.sample.trimRegion(name)
            responses = self.sample.responses[name][trim[0] : trim[1]]

            result = {
                "background": np.mean(responses[self.sample.labels[name] == 0]),
                "background_std": np.std(responses[self.sample.labels[name] == 0]),
                "detections": self.sample.detections[name],
                "detections_std": np.sqrt(self.sample.detections[name].size),
                "events": responses.size,
                "file": self.sample.label_file.text(),
                "limit_method": f"{self.sample.limits[name][0]},{','.join(f'{k}={v}' for k,v in self.sample.limits[name][1].items())}",
                "limit_window": int(self.options.window_size.text()),
                "lod": self.sample.limits[name][2]["ld"],
            }

            if method in ["Manual Input", "Reference Particle"]:
                try:
                    if method == "Manual Input":
                        efficiency = float(self.options.efficiency.text())
                    elif method == "Reference Particle":
                        efficiency = float(self.reference.io[name].efficiency.text())
                    else:
                        raise KeyError(f"Unknown method {method}.")
                except ValueError:
                    efficiency = None

                dwelltime = self.options.dwelltime.baseValue()
                density = self.sample.io[name].density.baseValue()
                massfraction = float(self.sample.io[name].massfraction.text())
                time = result["events"] * dwelltime
                uptake = self.options.uptake.baseValue()
                response = self.options.response.baseValue()

                if all(
                    x is not None
                    for x in [efficiency, density, dwelltime, uptake, response]
                ):
                    result.update(
                        results_from_nebulisation_efficiency(
                            result["detections"],
                            result["background"],
                            result["lod"],
                            density=density,
                            dwelltime=dwelltime,  # type: ignore
                            efficiency=efficiency,  # type: ignore
                            massfraction=massfraction,
                            uptake=uptake,  # type: ignore
                            response=response,  # type: ignore
                            time=time,
                        )
                    )
                    result["inputs"] = {
                        "density": density,
                        "dwelltime": dwelltime,
                        "transport_efficiency": efficiency,
                        "mass_fraction": massfraction,
                        "uptake": uptake,
                        "response": response,
                        "time": time,
                    }
            elif method == "Mass Response":
                density = self.sample.io[name].density.baseValue()
                massfraction = float(self.sample.io[name].massfraction.text())
                massresponse = self.reference.io[name].massresponse.baseValue()

                if density is not None:
                    self.result.update(
                        results_from_mass_response(
                            result["detections"],
                            result["background"],
                            result["lod"],
                            density=density,
                            massfraction=massfraction,
                            massresponse=massresponse,
                        )
                    )
                    result["inputs"] = {
                        "density": density,
                        "mass_fraction": massfraction,
                        "mass_response": massresponse,
                    }

            # Cell inputs
            celldiameter = self.options.celldiameter.baseValue()
            molarmass = self.sample.io[name].molarmass.baseValue()
            if celldiameter is not None:  # Scale sizes to hypothesised
                scale = celldiameter / np.mean(result["sizes"])
                result["sizes"] *= scale
                result["lod_size"] *= scale
                result["inputs"].update({"cell_diameter": celldiameter})

            if (
                celldiameter is not None and molarmass is not None
            ):  # Calculate the intracellular concetrations
                result["cell_concentrations"] = cell_concentration(
                    result["masses"],
                    diameter=celldiameter,
                    molarmass=molarmass,
                )
                result["lod_cell_concentration"] = cell_concentration(
                    result["lod_mass"],
                    diameter=celldiameter,
                    molarmass=molarmass,
                )
                result["inputs"].update({"molarmass": molarmass})

            self.result[name] = result
            self.updateOutputs(name)
        # end for name in names
        self.drawGraph()
