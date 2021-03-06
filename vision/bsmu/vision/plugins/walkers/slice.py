from __future__ import annotations

from PySide2.QtCore import QObject, Qt

from bsmu.vision.app.plugin import Plugin
from bsmu.vision.plugins.windows.main import ViewMenu
from bsmu.vision.widgets.mdi.windows.image.layered import VolumeSliceImageViewerSubWindow


class MdiVolumeSliceWalkerPlugin(Plugin):
    def __init__(self, app: App):
        super().__init__(app)

        self.main_window = app.enable_plugin('bsmu.vision.plugins.windows.main.MainWindowPlugin').main_window
        mdi = app.enable_plugin('bsmu.vision.plugins.doc_interfaces.mdi.MdiPlugin').mdi

        self.mdi_volume_slice_walker = MdiVolumeSliceWalker(mdi)

    def _enable(self):
        self.main_window.add_menu_action(ViewMenu, 'Next Slice',
                                         self.mdi_volume_slice_walker.show_next_slice,
                                         Qt.CTRL + Qt.Key_Up)
        self.main_window.add_menu_action(ViewMenu, 'Previous Slice',
                                         self.mdi_volume_slice_walker.show_prev_slice,
                                         Qt.CTRL + Qt.Key_Down)

    def _disable(self):
        raise NotImplementedError


class MdiVolumeSliceWalker(QObject):
    def __init__(self, mdi: Mdi):
        super().__init__()

        self.mdi = mdi

    def show_next_slice(self):
        for volume_slice_image_viewer in self._volume_slice_image_viewers():
            volume_slice_image_viewer.show_next_slice()

    def show_prev_slice(self):
        for volume_slice_image_viewer in self._volume_slice_image_viewers():
            volume_slice_image_viewer.show_prev_slice()

    def _volume_slice_image_viewers(self):
        active_sub_window = self.mdi.activeSubWindow()
        if isinstance(active_sub_window, VolumeSliceImageViewerSubWindow):
            return [active_sub_window.viewer]
        else:
            return []
