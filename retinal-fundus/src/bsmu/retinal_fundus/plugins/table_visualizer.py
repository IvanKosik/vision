from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PySide2.QtCore import QObject, Qt, Signal, QModelIndex, QSize
from PySide2.QtGui import QImage
from PySide2.QtWidgets import QGridLayout, QTableView, QHeaderView, QStyledItemDelegate, QSplitter, QAbstractItemView

import bsmu.vision.core.converters.image as image_converter
import bsmu.vision.dnn.segmenter as segmenter
from bsmu.vision.core.data import Data
from bsmu.vision.core.image.base import FlatImage
from bsmu.vision.core.image.layered import LayeredImage
from bsmu.vision.core.models.table import RecordTableModel, TableColumn
from bsmu.vision.core.palette import Palette
from bsmu.vision.core.plugins.base import Plugin
from bsmu.vision.dnn.segmenter import Segmenter as DnnSegmenter, ModelParams as DnnModelParams
from bsmu.vision.plugins.windows.main import WindowsMenu
from bsmu.vision.widgets.mdi.windows.base import DataViewerSubWindow
from bsmu.vision.widgets.viewers.base import DataViewer
from bsmu.vision.widgets.viewers.image.layered.flat import LayeredFlatImageViewer
from bsmu.vision.widgets.visibility_v2 import Visibility

if TYPE_CHECKING:
    from typing import List, Any

    from PySide2.QtCore import QAbstractItemModel
    from PySide2.QtWidgets import QWidget, QStyleOptionViewItem

    from bsmu.vision.plugins.doc_interfaces.mdi import MdiPlugin, Mdi
    from bsmu.vision.plugins.windows.main import MainWindowPlugin, MainWindow
    from bsmu.vision.plugins.visualizers.manager import DataVisualizationManagerPlugin, DataVisualizationManager
    from bsmu.vision.plugins.post_load_converters.manager import PostLoadConversionManagerPlugin, \
        PostLoadConversionManager


class RetinalFundusTableVisualizerPlugin(Plugin):
    _DEFAULT_DEPENDENCY_PLUGIN_FULL_NAME_BY_KEY = {
        'main_window_plugin': 'bsmu.vision.plugins.windows.main.MainWindowPlugin',
        'data_visualization_manager_plugin': 'bsmu.vision.plugins.visualizers.manager.DataVisualizationManagerPlugin',
        'post_load_conversion_manager_plugin':
            'bsmu.vision.plugins.post_load_converters.manager.PostLoadConversionManagerPlugin',
        'mdi_plugin': 'bsmu.vision.plugins.doc_interfaces.mdi.MdiPlugin',
    }

    _DNN_MODELS_DIR_NAME = 'dnn-models'
    _DATA_DIRS = (_DNN_MODELS_DIR_NAME,)

    def __init__(
            self,
            main_window_plugin: MainWindowPlugin,
            data_visualization_manager_plugin: DataVisualizationManagerPlugin,
            post_load_conversion_manager_plugin: PostLoadConversionManagerPlugin,
            mdi_plugin: MdiPlugin,
    ):
        super().__init__()

        self._main_window_plugin = main_window_plugin
        self._main_window: MainWindow | None = None

        self._data_visualization_manager_plugin = data_visualization_manager_plugin
        self._data_visualization_manager: DataVisualizationManager | None = None

        self._post_load_conversion_manager_plugin = post_load_conversion_manager_plugin
        self._post_load_conversion_manager: PostLoadConversionManager | None = None

        self._mdi_plugin = mdi_plugin
        self._mdi: Mdi | None = None

    def _enable(self):
        self._main_window = self._main_window_plugin.main_window
        self._data_visualization_manager = self._data_visualization_manager_plugin.data_visualization_manager
        self._post_load_conversion_manager = self._post_load_conversion_manager_plugin.post_load_conversion_manager
        self._mdi = self._mdi_plugin.mdi

        disk_segmenter_model_props = self.config.value('disk-segmenter-model')
        disk_segmenter_model_params = DnnModelParams(
            self.data_path(self._DNN_MODELS_DIR_NAME, disk_segmenter_model_props['name']),
            disk_segmenter_model_props['input-size'],
            disk_segmenter_model_props['preprocessing-mode'],
        )
        self.table_visualizer = RetinalFundusTableVisualizer(
            self._data_visualization_manager, self._mdi, disk_segmenter_model_params)

        self._post_load_conversion_manager.data_converted.connect(self.table_visualizer.visualize_retinal_fundus_data)

        self._main_window.add_menu_action(WindowsMenu, 'Table', self._disable, #% self.table_visualizer.raise_journal_sub_window,
                                         Qt.CTRL + Qt.Key_1)

    def _disable(self):
        self._post_load_conversion_manager.data_converted.disconnect(self.table_visualizer.visualize_retinal_fundus_data)


class PatientRetinalFundusRecord(QObject):
    def __init__(self, layered_image: LayeredImage):
        super().__init__()

        self._layered_image = layered_image

    @classmethod
    def from_flat_image(cls, image: FlatImage) -> PatientRetinalFundusRecord:
        layered_image = LayeredImage()
        layered_image.add_layer_from_image(image, 'image')
        return cls(layered_image)

    @property
    def layered_image(self) -> LayeredImage:
        return self._layered_image

    @property
    def image(self) -> FlatImage:
        return self._layered_image.layers[0].image


class PatientRetinalFundusJournal(Data):
    record_adding = Signal(PatientRetinalFundusRecord)
    record_added = Signal(PatientRetinalFundusRecord)
    record_removing = Signal(PatientRetinalFundusRecord)
    record_removed = Signal(PatientRetinalFundusRecord)

    def __init__(self):
        super().__init__()

        self._records = []

    @property
    def records(self) -> List[PatientRetinalFundusRecord]:
        return self._records

    def add_record(self, record: PatientRetinalFundusRecord):
        self.record_adding.emit(record)
        self.records.append(record)
        self.record_added.emit(record)


class PreviewTableColumn(TableColumn):
    TITLE = 'Preview'


class NameTableColumn(TableColumn):
    TITLE = 'Name'


class PatientRetinalFundusJournalTableModel(RecordTableModel):
    def __init__(
            self,
            record_storage: PatientRetinalFundusJournal = None,
            preview_height: int | None = None,
            parent: QObject = None
    ):
        super().__init__(record_storage, PatientRetinalFundusRecord, (PreviewTableColumn, NameTableColumn), parent)

        self._preview_height = preview_height

        # Store numpy array's data for preview images, because QImage uses it without copying,
        # and QImage will crash if it's data buffer will be deleted
        self._preview_data_buffer_by_record = {}

    @property
    def storage_records(self) -> List[PatientRetinalFundusRecord]:
        return self.record_storage.records

    def _record_data(self, record: PatientRetinalFundusRecord, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if role == Qt.DisplayRole:
            if index.column() == self.column_number(NameTableColumn):
                return record.image.path_name
        elif role == Qt.DecorationRole:
            if index.column() == self.column_number(PreviewTableColumn):
                preview_rgba_pixels = image_converter.converted_to_rgba(record.image.array)
                # Keep reference to numpy data, otherwise QImage will crash
                self._preview_data_buffer_by_record[record] = preview_rgba_pixels.data

                qimage_format = QImage.Format_RGBA8888_Premultiplied if preview_rgba_pixels.itemsize == 1 \
                    else QImage.Format_RGBA64_Premultiplied
                preview_qimage = image_converter.numpy_rgba_image_to_qimage(preview_rgba_pixels, qimage_format)
                if self._preview_height is not None:
                    preview_qimage = preview_qimage.scaledToHeight(self._preview_height, Qt.SmoothTransformation)
                return preview_qimage

    def _on_record_storage_changing(self):
        self.record_storage.record_adding.disconnect(self._on_storage_record_adding)
        self.record_storage.record_added.disconnect(self._on_storage_record_added)
        self.record_storage.record_removing.disconnect(self._on_storage_record_removing)
        self.record_storage.record_removed.disconnect(self._on_storage_record_removed)

    def _on_record_storage_changed(self):
        self.record_storage.record_adding.connect(self._on_storage_record_adding)
        self.record_storage.record_added.connect(self._on_storage_record_added)
        self.record_storage.record_removing.connect(self._on_storage_record_removing)
        self.record_storage.record_removed.connect(self._on_storage_record_removed)


class ImageCenterAlignmentDelegate(QStyledItemDelegate):
    def __init__(self, table_view: QTableView, parent: QObject = None):
        super().__init__(parent)

        self._table_view = table_view

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex):
        super().initStyleOption(option, index)

        option.decorationSize = QSize(self._table_view.columnWidth(index.column()),
                                      self._table_view.verticalHeader().defaultSectionSize())
        # option.decorationAlignment = Qt.AlignCenter


class PatientRetinalFundusJournalTableView(QTableView):
    record_selected = Signal(PatientRetinalFundusRecord)

    def __init__(self, row_height: int | None = None, parent: QWidget = None):
        super().__init__(parent)

        if row_height is not None:
            vertical_header = self.verticalHeader()
            vertical_header.setSectionResizeMode(QHeaderView.Fixed)
            vertical_header.setDefaultSectionSize(row_height)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def setModel(self, model: QAbstractItemModel):
        super().setModel(model)

        if model is None:
            return

        self.setItemDelegateForColumn(self.model().column_number(PreviewTableColumn),
                                      ImageCenterAlignmentDelegate(self))

        self.selectionModel().currentRowChanged.connect(self._on_current_row_changed)

    def _on_current_row_changed(self, current: QModelIndex, previous: QModelIndex):
        self.record_selected.emit(self.model().row_record(current.row()))


class PatientRetinalFundusJournalViewer(DataViewer):
    record_selected = Signal(PatientRetinalFundusRecord)

    def __init__(self, data: PatientRetinalFundusJournal = None):
        super().__init__(data)

        row_height = 64
        self._table_model = PatientRetinalFundusJournalTableModel(data, preview_height=row_height - 4)
        self._table_view = PatientRetinalFundusJournalTableView(row_height=row_height)
        self._table_view.setModel(self._table_model)
        self._table_view.record_selected.connect(self.record_selected)

        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self._table_view)
        self.setLayout(grid_layout)

    def select_record(self, record: PatientRetinalFundusRecord):
        row = self._table_model.record_row(record)
        self._table_view.selectRow(row)


class PatientRetinalFundusIllustratedJournalViewer(DataViewer):
    def __init__(self, data: PatientRetinalFundusJournal = None, parent: QWidget = None):
        self._journal_viewer = PatientRetinalFundusJournalViewer(data)
        self._journal_viewer.record_selected.connect(self._on_journal_record_selected)

        super().__init__(parent)

        self._layered_image_viewer = LayeredFlatImageViewer()
        self._layer_visibility_by_name = {}

        self._splitter = QSplitter()
        self._splitter.addWidget(self._journal_viewer)
        self._splitter.addWidget(self._layered_image_viewer)
        # Divide the width equally between the two widgets
        splitter_widget_size = max(
            self._journal_viewer.minimumSizeHint().width(), self._layered_image_viewer.minimumSizeHint().width())
        self._splitter.setSizes([splitter_widget_size, splitter_widget_size])

        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self._splitter)
        self.setLayout(grid_layout)

    @property
    def journal_viewer(self) -> PatientRetinalFundusJournalViewer:
        return self._journal_viewer

    @property
    def layered_image_viewer(self) -> LayeredFlatImageViewer:
        return self._layered_image_viewer

    @property
    def data(self) -> Data:
        return self._journal_viewer.data

    @data.setter
    def data(self, value: Data):
        self._journal_viewer.data = value

    @property
    def data_path_name(self):
        return self._journal_viewer.data_path_name

    def _on_journal_record_selected(self, record: PatientRetinalFundusRecord):
        # Save previous visibility of layers
        for layer_view in self.layered_image_viewer.layer_views:
            layer_view_visibility = Visibility(layer_view.visible, layer_view.opacity)
            self._layer_visibility_by_name[layer_view.name] = layer_view_visibility

        self._layered_image_viewer.data = record.layered_image

        # Restore previous visibility of layers
        for layer_view in self.layered_image_viewer.layer_views:
            prev_layer_visibility = self._layer_visibility_by_name.get(layer_view.name)
            if prev_layer_visibility is not None:
                layer_view.visible = prev_layer_visibility.visible
                layer_view.opacity = prev_layer_visibility.opacity

        self.layered_image_viewer.fit_image_in()


class IllustratedJournalSubWindow(DataViewerSubWindow):
    def __init__(self, viewer: DataViewer):
        super().__init__(viewer)

    @property
    def layered_image_viewer(self) -> LayeredImageViewer:
        return self.viewer.layered_image_viewer


class RetinalFundusTableVisualizer(QObject):
    def __init__(
            self,
            visualization_manager: DataVisualizationManager,  #% Temp
            mdi: Mdi,
            disk_segmenter_model_params: DnnModelParams
    ):
        super().__init__()

        self._visualization_manager = visualization_manager
        self._mdi = mdi

        self._segmenter = DnnSegmenter(disk_segmenter_model_params)

        self._mask_palette = Palette.default_soft([0, 255, 0])

        self._journal = PatientRetinalFundusJournal()
        self._journal.add_record(PatientRetinalFundusRecord.from_flat_image(FlatImage(
            array=np.random.randint(low=0, high=256, size=(50, 50), dtype=np.uint8),
            path=Path(r'D:\Temp\Void-1.png'))))
        self._journal.add_record(PatientRetinalFundusRecord.from_flat_image(FlatImage(
            array=np.random.randint(low=0, high=256, size=(50, 50), dtype=np.uint8),
            path=Path(r'D:\Temp\Void-2.png'))))

        self._image_sub_windows_by_record = {}

        self._illustrated_journal_viewer = PatientRetinalFundusIllustratedJournalViewer(self._journal)

        self._journal_sub_window = IllustratedJournalSubWindow(self._illustrated_journal_viewer)
        self._journal_sub_window.setWindowFlag(Qt.FramelessWindowHint)

        self._mdi.addSubWindow(self._journal_sub_window)
        self._journal_sub_window.showMaximized()

    @property
    def journal(self) -> PatientRetinalFundusJournal:
        return self._journal

    @property
    def illustrated_journal_viewer(self) -> PatientRetinalFundusIllustratedJournalViewer:
        return self._illustrated_journal_viewer

    @property
    def journal_viewer(self) -> PatientRetinalFundusJournalViewer:
        return self._illustrated_journal_viewer.journal_viewer

    @property
    def layered_image_viewer(self) -> LayeredFlatImageViewer:
        return self._illustrated_journal_viewer.layered_image_viewer

    def visualize_retinal_fundus_data(self, data: Data):
        if not isinstance(data, LayeredImage):
            return

        first_layer = data.layers[0]
        image = first_layer.image
        mask_pixels = self._segmenter.segment(image.array, segmenter.largest_connected_component_soft_mask)
        # mask_palette = Palette.from_sparse_index_list([[0, 0, 0, 0, 0],
        #                                                [1, 0, 255, 0, 100]])
        print('bef mask_pixels', mask_pixels.dtype, mask_pixels.min(), mask_pixels.max(), np.unique(mask_pixels))
        mask_pixels = image_converter.normalized_uint8(mask_pixels)
        print('aft mask_pixels', mask_pixels.dtype, mask_pixels.min(), mask_pixels.max(), np.unique(mask_pixels))

        mask_layer = data.add_layer_from_image(
            FlatImage(array=mask_pixels, palette=self._mask_palette), name='mask')

        record = PatientRetinalFundusRecord(data)
        self.journal.add_record(record)

        self.journal_viewer.select_record(record)

        # mask_layer_view = self.layered_image_viewer.layer_view_by_model(mask_layer)
        # mask_layer_view.opacity = 0.4

    def raise_journal_sub_window(self):
        self._journal_sub_window.show_normal()

        self._mdi.setActiveSubWindow(self._journal_sub_window)

        # self.journal_sub_window.raise_()

    def _on_journal_record_selected(self, record: PatientRetinalFundusRecord):
        image_sub_windows = self._image_sub_windows_by_record.get(record, [])
        for image_sub_window in image_sub_windows:
            image_sub_window.show_normal()

            image_sub_window.raise_()
