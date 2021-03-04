from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCharts import QtCharts

import numpy as np

import nanopart
from nanopart.fit import fit_normal, fit_lognormal

from nanopart.gui.charts import ParticleHistogram
from nanopart.gui.inputs import SampleWidget, ReferenceWidget
from nanopart.gui.options import OptionsWidget
from nanopart.gui.tables import ResultsTable
from nanopart.gui.units import UnitsWidget


# TODO instead of plotting atoms (same as mass) plot cell conc


class ResultsWidget(QtWidgets.QWidget):
    def __init__(
        self,
        options: OptionsWidget,
        sample: SampleWidget,
        reference: ReferenceWidget,
        parent: QtWidgets.QWidget = None,
    ):
        super().__init__(parent)

        self.options = options
        self.sample = sample
        self.reference = reference

        concentration_units = {
            "fg/L": 1e-18,
            "pg/L": 1e-15,
            "ng/L": 1e-12,
            "μg/L": 1e-9,
            "mg/L": 1e-6,
            "g/L": 1e-3,
            "kg/L": 1.0,
        }

        self.nbins = "auto"
        self.masses: np.ndarray = None
        self.sizes: np.ndarray = None
        self.number_concentration = 0.0
        self.concentration = 0.0
        self.ionic_background = 0.0
        self.background_lod_mass = 0.0
        self.background_lod_size = 0.0

        self.chart = ParticleHistogram()
        self.chart.drawVerticalLines(
            [0, 0, 0],
            names=["mean", "median", "lod"],
            pens=[
                QtGui.QPen(QtGui.QColor(255, 0, 0), 1.5, QtCore.Qt.DashLine),
                QtGui.QPen(QtGui.QColor(0, 0, 255), 1.5, QtCore.Qt.DashLine),
                QtGui.QPen(QtGui.QColor(0, 172, 0), 1.5, QtCore.Qt.DashLine),
            ],
        )
        self.chartview = QtCharts.QChartView(self.chart)
        self.chartview.setRenderHint(QtGui.QPainter.Antialiasing)

        self.table = ResultsTable()

        self.fitmethod = QtWidgets.QComboBox()
        self.fitmethod.addItems(["None", "Normal", "Lognormal"])
        self.fitmethod.setCurrentText("Lognormal")

        self.fitmethod.currentIndexChanged.connect(self.updateChartFit)

        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["Mass", "Size"])
        self.mode.setCurrentText("Size")
        self.mode.currentIndexChanged.connect(self.updateTable)
        self.mode.currentIndexChanged.connect(self.updateChart)

        self.outputs = QtWidgets.QGroupBox("Outputs")
        self.outputs.setLayout(QtWidgets.QHBoxLayout())

        self.count = QtWidgets.QLineEdit()
        self.count.setReadOnly(True)
        self.number = UnitsWidget(
            {"#/ml": 1e3, "#/L": 1.0}, default_unit="#/L", update_value_with_unit=True
        )
        self.number.setReadOnly(True)
        self.conc = UnitsWidget(
            concentration_units, default_unit="ng/L", update_value_with_unit=True
        )
        self.conc.setReadOnly(True)
        self.background = UnitsWidget(
            concentration_units, default_unit="ng/L", update_value_with_unit=True
        )
        self.background.setReadOnly(True)

        self.lod = UnitsWidget(
            {"nm": 1e-9, "μm": 1e-6, "m": 1.0},
            default_unit="nm",
            update_value_with_unit=True,
        )
        self.lod.setReadOnly(True)
        self.mean = UnitsWidget(
            {"nm": 1e-9, "μm": 1e-6, "m": 1.0},
            default_unit="nm",
            update_value_with_unit=True,
        )
        self.mean.setReadOnly(True)
        self.median = UnitsWidget(
            {"nm": 1e-9, "μm": 1e-6, "m": 1.0},
            default_unit="nm",
            update_value_with_unit=True,
        )
        self.median.setReadOnly(True)

        layout_outputs_left = QtWidgets.QFormLayout()
        layout_outputs_left.addRow("Detected particles:", self.count)
        layout_outputs_left.addRow("Number concentration:", self.number)
        layout_outputs_left.addRow("Concentration:", self.conc)
        layout_outputs_left.addRow("Ionic Background:", self.background)

        layout_outputs_right = QtWidgets.QFormLayout()
        layout_outputs_right.addRow("Mean size:", self.mean)
        layout_outputs_right.addRow("Median size:", self.median)
        layout_outputs_right.addRow("Size LOD:", self.lod)

        self.outputs.layout().addLayout(layout_outputs_left)
        self.outputs.layout().addLayout(layout_outputs_right)

        self.button_export = QtWidgets.QPushButton("Export")
        self.button_export.pressed.connect(self.dialogExportResults)

        layout_table_options = QtWidgets.QHBoxLayout()
        layout_table_options.addStretch(1)
        layout_table_options.addWidget(QtWidgets.QLabel("Mode:"), 0)
        layout_table_options.addWidget(self.mode)

        layout_table = QtWidgets.QVBoxLayout()
        layout_table.addLayout(layout_table_options)
        layout_table.addWidget(self.table, 1)
        layout_table.addWidget(self.button_export, 0, QtCore.Qt.AlignRight)

        layout_chart_options = QtWidgets.QHBoxLayout()
        layout_chart_options.addStretch(1)
        layout_chart_options.addWidget(QtWidgets.QLabel("Fit:"), 0)
        layout_chart_options.addWidget(self.fitmethod)

        layout_outputs = QtWidgets.QVBoxLayout()
        layout_outputs.addWidget(self.outputs)
        layout_outputs.addWidget(self.chartview)
        layout_outputs.addLayout(layout_chart_options)

        layout = QtWidgets.QHBoxLayout()
        layout.addLayout(layout_table, 0)
        layout.addLayout(layout_outputs, 1)
        self.setLayout(layout)

    def dialogExportResults(self) -> None:
        file, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export", "", "CSV Documents (.csv)"
        )
        if file != "":
            self.exportResults(file)

    def exportResults(self, path: str) -> None:
        text = (
            f"Detected particles,{self.sizes.size}\n"
            f"Number concentration,{self.number.value()},{self.number.unit()}\n"
            f"Concentration,{self.conc.value()},{self.conc.unit()}\n"
            f"Ionic background,{self.background.value()},{self.background.unit()}\n"
            f"Mean NP size,{np.mean(self.sizes) * 1e9},nm\n"
            f"Median NP size,{np.median(self.sizes) * 1e9},nm\n"
            f"LOD equivalent size,{self.background_lod_size * 1e9},nm\n"
        )

        # if False:
        #     text += (
        #         f"Median atoms per particle: {np.median(atoms)}\n"
        #         f"Background equivalent atoms: {beatoms}\n"
        #     )

        # # Output
        # if args.output:
        #     if args.molarmass:
        # if False:
        #     header = text + "Masses (kg),Sizes (m),Atoms"
        #     data = np.stack((self.masses, self.sizes, self.atoms), axis=1)
        # else:
        header = text + "Masses (kg),Sizes (m)"
        data = np.stack((self.masses, self.sizes), axis=1)

        np.savetxt(
            path,
            data,
            delimiter=",",
            header=header,
        )

    def updateChart(self) -> None:
        mode = self.mode.currentText()
        if mode == "Mass":
            data = self.masses * 1e21  # ag
            lod = self.background_lod_mass * 1e21  # ag
            self.chart.xaxis.setTitleText("Mass (ag)")
        elif mode == "Size":
            data = self.sizes * 1e9  # nm
            lod = self.background_lod_size * 1e9  # nm
            self.chart.xaxis.setTitleText("Size (nm)")

        hist, bins = np.histogram(
            data, bins=self.nbins, range=(data.min(), np.percentile(data, 99.9))
        )
        self.chart.setData(hist, bins, xmin=0.0)

        self.chart.setVerticalLines([np.mean(data), np.median(data), lod])

        self.updateChartFit()

    def updateChartFit(self) -> None:
        mode = self.mode.currentText()
        if mode == "Mass":
            data = self.masses * 1e21  # ag
        elif mode == "Size":
            data = self.sizes * 1e9  # nm

        method = self.fitmethod.currentText()
        if method == "None":
            self.chart.fit.clear()
            self.chart.label_fit.setVisible(False)
            return

        # vmin and vmax are for non-ednsity histogram
        vmin = data.min()
        vmax = np.percentile(data, 99.9)

        hist, bins = np.histogram(
            data, bins=self.nbins, range=(vmin, vmax), density=True
        )

        if method == "Normal":
            fit, err, opts = fit_normal(bins[1:], hist)
        elif method == "Lognormal":
            fit, err, opts = fit_lognormal(bins[1:], hist)

        # Fit to the non-density histogram
        binwidth = bins[1] - bins[0]
        fit = fit * binwidth * data.size
        self.chart.setFit(bins[1:], fit)
        self.chart.fit.setName(method)
        self.chart.label_fit.setVisible(True)

    def updateTable(self) -> None:
        mode = self.mode.currentText()
        if mode == "Mass":
            data = self.masses
        elif mode == "Size":
            data = self.sizes
        self.table.model().beginResetModel()
        self.table.model().array = data[:, None]
        self.table.model().endResetModel()

    def updateResults(self) -> None:
        method = self.options.efficiency_method.currentText()

        if method == "Manual":
            efficiency = float(self.options.efficiency.text())
            self.updateResultsNebEff(efficiency)
        elif method == "Reference":
            efficiency = float(self.reference.efficiency.text())
            self.updateResultsNebEff(efficiency)
        elif method == "Mass Response (None)":
            massresponse = self.reference.massresponse.baseValue()
            self.updateResultsMassResponse(massresponse)

        self.mean.setBaseValue(np.nanmean(self.sizes))
        self.median.setBaseValue(np.nanmedian(self.sizes))
        self.lod.setBaseValue(self.background_lod_size)

        self.count.setText(f"{self.sample.detections.size}")
        self.number.setBaseValue(self.number_concentration)
        self.conc.setBaseValue(self.concentration)
        self.background.setBaseValue(self.ionic_background)

        self.updateTable()
        self.updateChart()

    def updateResultsMassResponse(self, massresponse: float) -> None:
        density = self.sample.density.baseValue()
        molarratio = float(self.sample.molarratio.text())

        self.masses = self.sample.detections * (massresponse / molarratio)
        self.sizes = nanopart.particle_size(self.masses, density=density)

        self.number_concentration = None
        self.concentration = None
        self.ionic_background = None

        self.background_lod_mass = self.sample.limits[3] / (massresponse * molarratio)
        self.background_lod_size = nanopart.particle_size(
            self.background_lod_mass, density=density
        )

    def updateResultsNebEff(self, efficiency: float) -> None:
        dwelltime = self.options.dwelltime.baseValue()
        density = self.sample.density.baseValue()
        molarratio = float(self.sample.molarratio.text())
        time = self.sample.timeAsSeconds()
        uptake = self.options.uptake.baseValue()
        response = self.options.response.baseValue()

        self.masses = nanopart.particle_mass(
            self.sample.detections,
            dwell=dwelltime,
            efficiency=efficiency,
            flowrate=uptake,
            response_factor=response,
            molar_ratio=molarratio,
        )
        self.sizes = nanopart.particle_size(self.masses, density=density)

        self.number_concentration = nanopart.particle_number_concentration(
            self.sample.detections.size,
            efficiency=efficiency,
            flowrate=uptake,
            time=time,
        )
        self.concentration = nanopart.particle_total_concentration(
            self.masses,
            efficiency=efficiency,
            flowrate=uptake,
            time=time,
        )

        self.ionic_background = self.sample.background / response
        self.background_lod_mass = nanopart.particle_mass(
            self.sample.limits[3],
            dwell=dwelltime,
            efficiency=efficiency,
            flowrate=uptake,
            response_factor=response,
            molar_ratio=molarratio,
        )
        self.background_lod_size = nanopart.particle_size(
            self.background_lod_mass, density=density
        )

    def updateResultsSingleCell(self) -> None:
        size = self.options.diameter.baseValue()
        density = self.options.density.baseValue()

        # dwelltime = self.options.dwelltime.baseValue()
        # uptake = self.options.uptake.baseValue()
        # response = self.options.response.baseValue()
        # efficiency = float(self.options.efficiency.text())

        # time = self.sample.timeAsSeconds()
        # density = self.sample.density.baseValue()
        # molarratio = float(self.sample.molarratio.text())

        # self.masses = nanopart.particle_mass(
        #     self.sample.detections,
        #     dwell=dwelltime,
        #     efficiency=efficiency,
        #     flowrate=uptake,
        #     response_factor=response,
        #     # mass_fraction=molarratio,
        # )
        # self.sizes = nanopart.particle_size(self.masses, density=density)
        # self.number_concentration = nanopart.particle_number_concentration(
        #     self.sample.detections.size,
        #     efficiency=efficiency,
        #     flowrate=uptake,
        #     time=time,
        # )
        # self.concentration = nanopart.particle_total_concentration(
        #     self.masses,
        #     efficiency=efficiency,
        #     flowrate=uptake,
        #     time=time,
        # )

        # self.ionic_background = self.sample.background / response
        # self.background_lod_mass = nanopart.particle_mass(
        #     self.sample.limits[3],
        #     dwell=dwelltime,
        #     efficiency=efficiency,
        #     flowrate=uptake,
        #     response_factor=response,
        #     mass_fraction=molarratio,
        # )
        # self.background_lod_size = nanopart.particle_size(
        #     self.background_lod_mass, density=density
        # )

        # self.count.setText(f"{self.sample.detections.size}")
        # self.number.setBaseValue(self.number_concentration)
        # self.conc.setBaseValue(self.concentration)
        # self.background.setBaseValue(self.ionic_background)

        # self.updateChart()
