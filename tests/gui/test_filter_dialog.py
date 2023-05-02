from typing import List

import numpy as np
from pytestqt.qtbot import QtBot

from spcal.gui.dialogs.filter import BooleanItemWidget, Filter, FilterDialog

names = ["a", "b", "c"]


def test_filter_dialog_empty(qtbot: QtBot):
    dlg = FilterDialog(names, [])
    qtbot.addWidget(dlg)
    with qtbot.wait_exposed(dlg):
        dlg.show()

    # Will all collapse
    dlg.action_add.trigger()
    dlg.action_add.trigger()
    dlg.action_or.trigger()
    dlg.action_add.trigger()
    dlg.action_add.trigger()
    dlg.list.itemWidget(dlg.list.item(0)).value.setBaseValue(1.0)

    def check_filters(filters: List[List[Filter]]) -> bool:
        if len(filters) != 1:
            return False
        if len(filters[0]) != 1:
            return False
        if filters[0][0].value != 1.0:
            return False
        return True

    with qtbot.wait_signal(dlg.filtersChanged, check_params_cb=check_filters):
        dlg.accept()


def test_filter_dialog_filters(qtbot: QtBot):
    filters = [
        [Filter("a", "mass", ">", 1.0), Filter("b", "mass", ">", 2.0)],
        [Filter("c", "mass", "<", 3.0)],
    ]
    dlg = FilterDialog(names, filters)
    qtbot.addWidget(dlg)
    with qtbot.wait_exposed(dlg):
        dlg.show()

    # Check loaded correctly
    assert dlg.list.itemWidget(dlg.list.item(0)).names.currentText() == "a"
    assert dlg.list.itemWidget(dlg.list.item(0)).unit.currentText() == "Mass"
    assert dlg.list.itemWidget(dlg.list.item(0)).value.baseValue() == 1.0
    assert dlg.list.itemWidget(dlg.list.item(1)).names.currentText() == "b"
    assert isinstance(dlg.list.itemWidget(dlg.list.item(2)), BooleanItemWidget)
    assert dlg.list.itemWidget(dlg.list.item(3)).names.currentText() == "c"
    assert dlg.list.itemWidget(dlg.list.item(3)).operation.currentText() == "<"

    # Remove the or
    dlg.list.itemWidget(dlg.list.item(2)).close()

    def check_filters(filters: List[List[Filter]]) -> bool:
        if len(filters) != 1:
            return False
        if len(filters[0]) != 3:
            return False
        for filter, val in zip(filters[0], [1.0, 2.0, 3.0]):
            if filter.value != val:
                return False
        return True

    with qtbot.wait_signal(dlg.filtersChanged, check_params_cb=check_filters):
        dlg.accept()

    # def filterResults(self) -> None:
    #     """Filters the current results.

    #     Filters are slected in the ``spcal.gui.dialogs.FilterDialog``. Filters are
    #     stored as a list of groups where each filters are combined by && (logical and).
    #     Each group is || (logical or'd) together.

    #     If no filters are selected then this does nothing.
    #     """
    #     if len(self.filters) == 0:
    #         return

    #     size = next(iter(self.results.values())).detections["signal"].size
    #     valid = np.zeros(size, dtype=bool)

    #     for filter_group in self.filters:
    #         group_valid = np.ones(size, dtype=bool)
    #         for filter in filter_group:
    #             if (
    #                 filter.name in self.results
    #                 and filter.unit in self.results[filter.name].detections
    #             ):
    #                 data = self.results[filter.name].detections[filter.unit]
    #                 group_valid = np.logical_and(
    #                     filter.ufunc(data, filter.value), group_valid
    #                 )
    #         valid = np.logical_or(group_valid, valid)

    #     valid_indicies = np.flatnonzero(valid)

    #     for name in self.results:
    #         indicies = self.results[name].indicies
    #         self.results[name].indicies = indicies[np.in1d(indicies, valid_indicies)]
