from __future__ import annotations

from typing import Union

from PySide2.QtCore import Signal
from PySide2.QtGui import QResizeEvent
from PySide2.QtWidgets import QMdiArea

from bsmu.vision.app.plugin import Plugin
from bsmu.vision.plugins.windows.main import MainWindowPlugin


class MdiPlugin(Plugin):
    def __init__(self, app: App,
                 main_window_plugin: Union[str, MainWindowPlugin] = MainWindowPlugin.full_name(),
                 ):
        super().__init__(app)

        self.main_window = app.enable_plugin(main_window_plugin).main_window

        self.mdi = Mdi()

    def _enable(self):
        self.main_window.setCentralWidget(self.mdi)

    def _disable(self):
        self.main_window.takeCentralWidget()


class Mdi(QMdiArea):
    resized = Signal(QResizeEvent)

    def __init__(self):
        super().__init__()

    def resizeEvent(self, resize_event: QResizeEvent):
        super().resizeEvent(resize_event)

        for sub_window in self.subWindowList():
            sub_window.lay_out_to_anchors()

        self.resized.emit(resize_event)
