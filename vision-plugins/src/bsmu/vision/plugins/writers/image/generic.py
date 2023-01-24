from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import skimage.io
from PySide6.QtWidgets import QFileDialog, QMessageBox

from bsmu.vision.plugins.windows.main import FileMenu
from bsmu.vision.plugins.writers.base import FileWriterPlugin, FileWriter
from bsmu.vision.widgets.viewers.image.layered.base import LayeredImageViewerHolder

if TYPE_CHECKING:
    from bsmu.vision.core.image.base import Image
    from bsmu.vision.plugins.windows.main import MainWindowPlugin, MainWindow
    from bsmu.vision.plugins.doc_interfaces.mdi import MdiPlugin, Mdi


class GenericImageFileWriterPlugin(FileWriterPlugin):
    _DEFAULT_DEPENDENCY_PLUGIN_FULL_NAME_BY_KEY = {
        'main_window_plugin': 'bsmu.vision.plugins.windows.main.MainWindowPlugin',
        'mdi_plugin': 'bsmu.vision.plugins.doc_interfaces.mdi.MdiPlugin',
    }

    def __init__(
            self,
            main_window_plugin: MainWindowPlugin,
            mdi_plugin: MdiPlugin,
    ):
        super().__init__(GenericImageFileWriter)

        self._main_window_plugin = main_window_plugin
        self._main_window: MainWindow | None = None

        self._mdi_plugin = mdi_plugin
        self._mdi: Mdi | None = None

    def _enable_gui(self):
        self._main_window = self._main_window_plugin.main_window
        self._main_window.add_menu_action(FileMenu, 'Save Mask...', self._select_path_and_save_active_window_image)

        self._mdi = self._mdi_plugin.mdi

    def _select_path_and_save_active_window_image(self):
        active_sub_window = self._mdi.activeSubWindow()
        if not isinstance(active_sub_window, LayeredImageViewerHolder):
            QMessageBox.warning(
                self._main_window,
                'No Layered Image',
                'The active window does not contain a layered image.')
            return

        layer_name = 'masks'
        image_layer = active_sub_window.layered_image_viewer.layer_by_name(layer_name)
        if not image_layer or not image_layer.image:
            QMessageBox.warning(
                self._main_window,
                'No Image',
                f'The layered image does not contain an image in the "{layer_name}" layer.')
            return

        file_name, selected_filter = QFileDialog.getSaveFileName(
            parent=self._main_window, caption='Save Mask', filter='PNG (*.png)')
        if not file_name:
            return

        self._file_writer_cls().write_to_file(image_layer.image, Path(file_name))


class GenericImageFileWriter(FileWriter):
    _FORMATS = ('png', 'jpg', 'jpeg', 'bmp', 'tiff')

    def _write_to_file(self, data: Image, path: Path, **kwargs):
        print('Write Generic Image')

        skimage.io.imsave(str(path), data.pixels, check_contrast=False)
