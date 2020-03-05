from __future__ import annotations

from PySide2.QtWidgets import QMdiSubWindow


class DataViewerSubWindow(QMdiSubWindow):
    def __init__(self, viewer: DataViewer):
        super().__init__()

        self.viewer = viewer

        self.setWindowTitle(self.viewer.data_path_name)

    @property
    def viewer(self):
        return self.widget()

    @viewer.setter
    def viewer(self, value):
        self.setWidget(value)
