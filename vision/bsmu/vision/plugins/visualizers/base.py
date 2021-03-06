from __future__ import annotations

import abc
from typing import List

from PySide2.QtCore import QObject, Signal

from bsmu.vision.app.plugin import Plugin
from bsmu.vision.widgets.mdi.windows.base import DataViewerSubWindow


class DataVisualizerPlugin(Plugin):
    def __init__(self, app: App, data_visualizer_cls):
        super().__init__(app)

        self.data_visualizer_cls = data_visualizer_cls


class DataVisualizerMeta(abc.ABCMeta, type(QObject)):
    _DATA_TYPES = ()

    @property
    def data_types(cls) -> tuple:
        return cls._DATA_TYPES


class DataVisualizer(QObject, metaclass=DataVisualizerMeta):
    data_visualized = Signal(list)  # List[DataViewerSubWindow]

    def __init__(self, mdi):
        super().__init__()

        self.mdi = mdi

    @property
    def data_types(self):
        return type(self).data_types

    def visualize_data(self, data: Data) -> List[DataViewerSubWindow]:
        data_viewer_sub_windows = self._visualize_data(data)
        self.data_visualized.emit(data_viewer_sub_windows)
        return data_viewer_sub_windows

    @abc.abstractmethod
    def _visualize_data(self, data: Data) -> List[DataViewerSubWindow]:
        pass
