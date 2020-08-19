from __future__ import annotations

from abc import ABC, abstractmethod
from functools import partial
from pathlib import Path
from typing import List, Type
from typing import TYPE_CHECKING

import numpy as np
import skimage.transform
from PySide2.QtCore import QObject, Qt, QSysInfo, Signal, QDate
from PySide2.QtWidgets import QTableWidget, QTableWidgetItem, QGridLayout, QAbstractItemView, QHeaderView, QMenu, \
    QActionGroup, QAction

from bsmu.vision.app.plugin import Plugin
from bsmu.vision.plugins.bone_age.predictor import Predictor, DnnModelParams
from bsmu.vision.widgets.date import DateEditWidget
from bsmu.vision.widgets.gender import GenderWidget
from bsmu.vision.widgets.layer_visibility import LayerVisibilityWidget
from bsmu.vision.widgets.mdi.windows.base import DataViewerSubWindow
from bsmu.vision.widgets.viewers.base import DataViewer
from bsmu.vision_core import date
from bsmu.vision_core.converters import color as color_converter
from bsmu.vision_core.converters import image as image_converter
from bsmu.vision_core.data import Data
from bsmu.vision_core.image.base import FlatImage
from bsmu.vision_core.image.layered import LayeredImage
from bsmu.vision_core.transfer_functions.color import ColorTransferFunction

if TYPE_CHECKING:
    from bsmu.vision.app import App


class BoneAgeTableVisualizerPlugin(Plugin):
    def __init__(self, app: App):
        super().__init__(app)

        self.data_visualization_manager = app.enable_plugin(
            'bsmu.vision.plugins.visualizers.manager.DataVisualizationManagerPlugin').data_visualization_manager
        mdi = app.enable_plugin('bsmu.vision.plugins.doc_interfaces.mdi.MdiPlugin').mdi
        self.table_visualizer = BoneAgeTableVisualizer(self.data_visualization_manager, mdi)

    def _enable(self):
        self.data_visualization_manager.data_visualized.connect(self.table_visualizer.visualize_bone_age_data)

    def _disable(self):
        self.data_visualization_manager.data_visualized.disconnect(self.table_visualizer.visualize_bone_age_data)


class PatientBoneAgeRecord(QObject):
    male_changed = Signal(bool)
    birthdate_changed = Signal(QDate)
    image_date_changed = Signal(QDate)
    age_in_image_changed = Signal(float)
    bone_age_changed = Signal(float)

    def __init__(self, image: FlatImage, male: bool, birthdate: QDate, image_date: QDate, bone_age: float):
        super().__init__()

        self.image = image
        self._male = male
        self._birthdate = birthdate
        self._image_date = image_date
        self._bone_age = bone_age  # in days

        self._age_in_image = self._calculate_age_in_image()  # in days
        self.birthdate_changed.connect(self._update_age_in_image)
        self.image_date_changed.connect(self._update_age_in_image)

    @property
    def male(self) -> bool:
        return self._male

    @male.setter
    def male(self, value: bool):
        if self._male != value:
            self._male = value
            self.male_changed.emit(self._male)

    @property
    def birthdate(self) -> QDate:
        return self._birthdate

    @birthdate.setter
    def birthdate(self, value: QDate):
        if self._birthdate != value:
            self._birthdate = value
            self.birthdate_changed.emit(self._birthdate)

    @property
    def image_date(self) -> QDate:
        return self._image_date

    @image_date.setter
    def image_date(self, value: QDate):
        if self._image_date != value:
            self._image_date = value
            self.image_date_changed.emit(self._image_date)

    @property
    def age_in_image(self) -> float:
        return self._age_in_image

    @property
    def bone_age(self) -> float:
        return self._bone_age

    @bone_age.setter
    def bone_age(self, value: float):
        if self._bone_age != value:
            self._bone_age = value
            self.bone_age_changed.emit(self._bone_age)

    def _calculate_age_in_image(self):
        return self.birthdate.daysTo(self.image_date)

    def _update_age_in_image(self):
        self._age_in_image = self._calculate_age_in_image()
        self.age_in_image_changed.emit(self.age_in_image)


class PatientBoneAgeJournal(Data):
    record_added = Signal(PatientBoneAgeRecord)

    def __init__(self):
        super().__init__()

        self.records = []

    def add_record(self, record: PatientBoneAgeRecord):
        self.records.append(record)
        self.record_added.emit(record)


class PatientBoneAgeJournalTableRecord(QObject):
    def __init__(self, record: PatientBoneAgeRecord):
        super().__init__()

        self.record = record


class AgeFormat(ABC):
    NAME = ''
    ABBR = ''

    age_decimals = 2

    @classmethod
    @abstractmethod
    def format(cls, age: float) -> str:
        pass


class MonthsAgeFormat(AgeFormat):
    NAME = 'Months'
    ABBR = 'M'

    @classmethod
    def format(cls, age_in_days: float) -> str:
        return f'{date.days_to_months(age_in_days):.{cls.age_decimals}f}'


class YearsMonthsAgeFormat(AgeFormat):
    NAME = 'Years / Months'
    ABBR = 'Y / M'

    @classmethod
    def format(cls, age_in_days: float) -> str:
        years, months = date.days_to_years_months(age_in_days)
        return f'{int(years)} / {months:.{cls.age_decimals}f}'


class TableColumn:
    TITLE = ''


class TableNameColumn(TableColumn):
    TITLE = 'Name'


class TableGenderColumn(TableColumn):
    TITLE = 'Gender'


class TableBirthdateColumn(TableColumn):
    TITLE = 'Date of Birth'


class TableImageDateColumn(TableColumn):
    TITLE = 'Image Date'


class TableAgeColumn(TableColumn):
    TITLE = 'Age'

    RECORD_PROPERTY = None

    @classmethod
    def value(cls, record: PatientBoneAgeRecord):
        return cls.RECORD_PROPERTY.__get__(record)


class TableAgeInImageColumn(TableAgeColumn):
    TITLE = 'Age in Image'

    RECORD_PROPERTY = PatientBoneAgeRecord.age_in_image


class TableDenseNetBoneAgeColumn(TableAgeColumn):
    TITLE = 'Bone Age'

    RECORD_PROPERTY = PatientBoneAgeRecord.bone_age


class TableActivationMapColumn(TableColumn):
    TITLE = 'Activation Map Visibility'


class PatienBoneAgeRecordAction(QAction):
    triggered_on_record = Signal(PatientBoneAgeRecord)

    def __init__(self, text: str):
        super().__init__(text)


class PatientBoneAgeJournalTable(QTableWidget):
    record_selected = Signal(PatientBoneAgeRecord)

    RECORD_REF_ROLE = Qt.UserRole

    def __init__(self, data: PatientBoneAgeJournal = None):
        super().__init__()

        self.data = data

        self._records_rows = {}  # {PatientBoneAgeRecord: row}

        self._age_formats = [MonthsAgeFormat, YearsMonthsAgeFormat]
        self._age_format = YearsMonthsAgeFormat

        self._columns = [TableNameColumn, TableGenderColumn, TableBirthdateColumn, TableImageDateColumn,
                         TableAgeInImageColumn, TableDenseNetBoneAgeColumn, TableActivationMapColumn]
        self._columns_numbers = {column: number for number, column in enumerate(self._columns)}
        self._age_columns = {column for column in self._columns if issubclass(column, TableAgeColumn)}
        self._age_column_numbers = {self._columns_numbers[column] for column in self._age_columns}

        self._age_column_context_menu_actions = []

        self.setColumnCount(len(self._columns))
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        horizontal_header_labels = [self._create_column_title(column) for column in self._columns]
        self.setHorizontalHeaderLabels(horizontal_header_labels)
        # self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        if QSysInfo.windowsVersion() == QSysInfo.WV_WINDOWS10:
            # Add border under the header
            self.setStyleSheet(
                'QHeaderView::section { '
                'border-top: 0px solid #D8D8D8; '
                'border-left: 0px solid #D8D8D8; '
                'border-right: 1px solid #D8D8D8; '
                'border-bottom: 1px solid #D8D8D8; '
                '}'
                'QTableCornerButton::section { '
                'border-top: 0px solid #D8D8D8; '
                'border-left: 0px solid #D8D8D8; '
                'border-right: 1px solid #D8D8D8; '
                'border-bottom: 1px solid #D8D8D8; '
                '}')
            self.verticalHeader().setStyleSheet('QHeaderView::section { padding-left: 4px; }')

        self.itemSelectionChanged.connect(self._on_item_selection_changed)

        for record in self.data.records:
            self._add_record_view(record)

        self.data.record_added.connect(self._add_record_view)

        # Configure a custom context menu for the horizontal header
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._display_header_context_menu)

        # Configure a custom context menu for the table
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._display_context_menu)

    def column_number(self, column: Type[TableColumn]) -> int:
        return self._columns_numbers[column]

    @property
    def age_format(self) -> Type[AgeFormat]:
        return self._age_format

    @age_format.setter
    def age_format(self, value: Type[AgeFormat]):
        if self._age_format != value:
            self._age_format = value
            self._update_age_column_headers()
            self._update_age_column_contents()

    def add_record_activation_map_visibility_widget(
            self, record: PatientBoneAgeRecord, layer_visibility_widget: LayerVisibilityWidget):
        row = self._records_rows[record]
        self.setCellWidget(row, self.column_number(TableActivationMapColumn), layer_visibility_widget)

    def add_age_column_context_menu_action(self, action: PatienBoneAgeRecordAction):
        self._age_column_context_menu_actions.append(action)

    def remove_age_column_context_menu_action(self, action: PatienBoneAgeRecordAction):
        self._age_column_context_menu_actions.remove(action)

    def _row_record(self, row: int) -> PatientBoneAgeRecord:
        return self.item(row, self.column_number(TableNameColumn)).data(self.RECORD_REF_ROLE)

    def _create_column_title(self, column: Type[TableColumn]) -> str:
        column_title = column.TITLE
        if issubclass(column, TableAgeColumn):
            column_title += f' ({self._age_format.ABBR})'
        return column_title

    def _add_record_view(self, record: PatientBoneAgeRecord):
        row = self.rowCount()
        self.insertRow(row)
        self._records_rows[record] = row

        name = '' if record.image is None else record.image.path.stem
        name_item = QTableWidgetItem(name)
        name_item.setTextAlignment(Qt.AlignCenter)
        # Add the |record| reference to the |name_item|
        name_item.setData(self.RECORD_REF_ROLE, record)
        self.setItem(row, self.column_number(TableNameColumn), name_item)

        gender_widget = GenderWidget(embedded=True)
        gender_widget.man = record.male
        gender_widget.gender_changed.connect(partial(self._on_gender_changed, record))
        record.male_changed.connect(partial(self._on_record_male_changed, gender_widget))
        self.setCellWidget(row, self.column_number(TableGenderColumn), gender_widget)

        birthdate_edit_widget = DateEditWidget(record.birthdate, embedded=True)
        birthdate_edit_widget.dateChanged.connect(partial(self._on_birthdate_changed, record))
        self.setCellWidget(row, self.column_number(TableBirthdateColumn), birthdate_edit_widget)

        image_date_edit_widget = DateEditWidget(record.image_date, embedded=True)
        image_date_edit_widget.dateChanged.connect(partial(self._on_image_date_changed, record))
        self.setCellWidget(row, self.column_number(TableImageDateColumn), image_date_edit_widget)

        age_in_image_item = QTableWidgetItem()
        age_in_image_item.setFlags(age_in_image_item.flags() & ~Qt.ItemIsEditable)
        age_in_image_item.setTextAlignment(Qt.AlignCenter)
        record.age_in_image_changed.connect(partial(self._set_age_to_table_item, age_in_image_item))
        self.setItem(row, self.column_number(TableAgeInImageColumn), age_in_image_item)

        bone_age_item = QTableWidgetItem()
        bone_age_item.setFlags(bone_age_item.flags() & ~Qt.ItemIsEditable)
        bone_age_item.setTextAlignment(Qt.AlignCenter)
        record.bone_age_changed.connect(partial(self._set_age_to_table_item, bone_age_item))
        self.setItem(row, self.column_number(TableDenseNetBoneAgeColumn), bone_age_item)

        self._update_age_column_contents()

    def _on_item_selection_changed(self):
        selected_ranges = self.selectedRanges()
        if selected_ranges:
            bottom_selected_row = selected_ranges[-1].bottomRow()
            selected_record = self._row_record(bottom_selected_row)
            self.record_selected.emit(selected_record)

    def _on_gender_changed(self, record: PatientBoneAgeRecord, man: bool):
        record.male = man

    def _on_record_male_changed(self, gender_widget: GenderWidget, male: bool):
        gender_widget.man = male

    def _on_birthdate_changed(self, record: PatientBoneAgeRecord, date: QDate):
        record.birthdate = date

    def _on_image_date_changed(self, record: PatientBoneAgeRecord, date: QDate):
        record.image_date = date

    def _set_age_to_table_item(self, age_table_item: QTableWidgetItem, age: float):
        age_table_item.setText(self._age_format.format(age))

    def _display_header_context_menu(self, point: QPoint):
        column_number = self.horizontalHeader().logicalIndexAt(point)
        if column_number in self._age_column_numbers:
            self._display_age_column_header_context_menu(point)

    def _display_age_column_header_context_menu(self, point: QPoint):
        menu = QMenu(self)
        format_menu = menu.addMenu('Format')
        format_action_group = QActionGroup(self)
        for age_format in self._age_formats:
            format_action = format_menu.addAction(age_format.NAME)
            format_action.age_format = age_format
            format_action.setCheckable(True)

            if self._age_format == age_format:
                format_action.setChecked(True)

            format_action_group.addAction(format_action)

        triggered_action = menu.exec_(self.horizontalHeader().viewport().mapToGlobal(point))
        if triggered_action:
            self.age_format = triggered_action.age_format

    def _display_context_menu(self, point: QPoint):
        column_number = self.horizontalHeader().logicalIndexAt(point)
        if column_number in self._age_column_numbers:
            self._display_age_column_context_menu(point)

    def _display_age_column_context_menu(self, point: QPoint):
        if not self._age_column_context_menu_actions:
            return

        menu = QMenu(self)
        for action in self._age_column_context_menu_actions:
            menu.insertAction(None, action)

        triggered_action = menu.exec_(self.viewport().mapToGlobal(point))
        if triggered_action:
            menu_patient_record = self._row_record(self.itemAt(point).row())
            triggered_action.triggered_on_record.emit(menu_patient_record)

    def _update_age_column_headers(self):
        for age_column in self._age_columns:
            header_label = self._create_column_title(age_column)
            age_column_number = self._columns_numbers[age_column]
            self.horizontalHeaderItem(age_column_number).setText(header_label)

    def _update_age_column_contents(self):
        for row in range(self.rowCount()):
            record = self._row_record(row)
            for age_column in self._age_columns:
                age_column_number = self._columns_numbers[age_column]
                age_item = self.item(row, age_column_number)
                self._set_age_to_table_item(age_item, age_column.value(record))


class PatientBoneAgeJournalViewer(DataViewer):
    record_selected = Signal(PatientBoneAgeRecord)

    def __init__(self, data: PatientBoneAgeJournal = None):
        super().__init__(data)

        self.table = PatientBoneAgeJournalTable(self.data)
        self.table.record_selected.connect(self.record_selected)

        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self.table)
        self.setLayout(grid_layout)

    def add_record_activation_map_visibility_widget(
            self, record: PatientBoneAgeRecord, layer_visibility_widget: LayerVisibilityWidget):
        self.table.add_record_activation_map_visibility_widget(record, layer_visibility_widget)

    def add_age_column_context_menu_action(self, action: PatienBoneAgeRecordAction):
        self.table.add_age_column_context_menu_action(action)

    def remove_age_column_context_menu_action(self, action: PatienBoneAgeRecordAction):
        self.table.remove_age_column_context_menu_action(action)


class BoneAgeTableVisualizer(QObject):
    ACTIVATION_MAP_LAYER_NAME = 'Activation Map'

    def __init__(self, visualization_manager: DataVisualizationManager, mdi: Mdi):
        super().__init__()

        model_name = 'DenseNet169_500x500_b7_AllImages3_MoreAugments_Mae5.80.pb'  # 'DenseNet_withInputShape___weighted.pb'
        self.predictor = Predictor(
            DnnModelParams(Path(__file__).parent / 'dnn-models' / model_name))

        self.visualization_manager = visualization_manager
        self.mdi = mdi

        self.journal = PatientBoneAgeJournal()
        self.journal_viewer = PatientBoneAgeJournalViewer(self.journal)
        self.journal_viewer.record_selected.connect(self._on_journal_record_selected)

        self.records_image_sub_windows = {}

        self.journal_sub_window = DataViewerSubWindow(self.journal_viewer)
        self.journal_sub_window.layout_anchors = np.array([[0, 0], [0.6, 1]])
        self.mdi.addSubWindow(self.journal_sub_window)

    def visualize_bone_age_data(self, data: Data, data_viewer_sub_windows: List[DataViewerSubWindow]):
        print('visualize_bone_age_data', type(data))

        if isinstance(data, LayeredImage):
            first_layer = data.layers[0]

            default_gender_is_male = True
            image = first_layer.image
            predicted_bone_age, activation_map = self.predictor.predict(image, default_gender_is_male)
            record = PatientBoneAgeRecord(image, default_gender_is_male, QDate(2000, 1, 1), QDate.currentDate(),
                                          date.months_to_days(predicted_bone_age))
            record.male_changed.connect(partial(self._on_record_male_changed, record))
            self.journal.add_record(record)

            self.records_image_sub_windows[record] = data_viewer_sub_windows

            for sub_window in data_viewer_sub_windows:
                sub_window.layout_anchors = np.array([[0.6, 0], [1, 1]])
                sub_window.lay_out_to_anchors()

            # Add a layer with the activation map
            activation_map = skimage.transform.resize(activation_map, image.array.shape[:2], order=3)
            activation_map = image_converter.normalized_uint8(activation_map)

            activation_map_color_transfer_function = ColorTransferFunction.default_jet()
            activation_map_color_transfer_function.points[0].color_array = np.array([0, 0, 255, 0])
            activation_map_palette = color_converter.color_transfer_function_to_palette(
                activation_map_color_transfer_function)

            activation_map_layer = data.add_layer_from_image(
                FlatImage(array=activation_map, palette=activation_map_palette), name=self.ACTIVATION_MAP_LAYER_NAME)

            activation_map_layer_views = []
            for sub_window in data_viewer_sub_windows:
                activation_map_layer_view = sub_window.viewer.layer_view_by_model(activation_map_layer)
                activation_map_layer_view.opacity = 0.5
                activation_map_layer_views.append(activation_map_layer_view)
            activation_map_visibility_widget = LayerVisibilityWidget(activation_map_layer_views, embedded=True)
            # activation_map_visibility_widget.slider_bar_color = QColor(240, 206, 164)
            # activation_map_visibility_widget.toggle_button_checked_color = QColor(240, 206, 164)
            self.journal_viewer.add_record_activation_map_visibility_widget(
                record, activation_map_visibility_widget)

    def add_age_column_context_menu_action(self, action: PatienBoneAgeRecordAction):
        self.journal_viewer.add_age_column_context_menu_action(action)

    def remove_age_column_context_menu_action(self, action: PatienBoneAgeRecordAction):
        self.journal_viewer.remove_age_column_context_menu_action(action)

    def _on_record_male_changed(self, record: PatientBoneAgeRecord, male: bool):
        self._update_record_bone_age(record)

    def _update_record_bone_age(self, record: PatientBoneAgeRecord):
        predicted_bone_age, _ = self.predictor.predict(record.image, record.male, calculate_activation_map=False)
        record.bone_age = date.months_to_days(predicted_bone_age)

    def _on_journal_record_selected(self, record: PatientBoneAgeRecord):
        image_sub_windows = self.records_image_sub_windows.get(record, [])
        for image_sub_window in image_sub_windows:
            image_sub_window.raise_()
