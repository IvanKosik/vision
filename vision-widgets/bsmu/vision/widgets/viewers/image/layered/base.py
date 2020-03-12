from __future__ import annotations

import bsmu.vision_core.converters.image as image_converter
from PySide2.QtCore import QObject, Signal, QRectF
from PySide2.QtGui import QPainter, QImage
from PySide2.QtWidgets import QGridLayout, QGraphicsScene, QGraphicsObject, QGraphicsItem
from bsmu.vision_core.image import FlatImage

from bsmu.vision.widgets.viewers.base import DataViewer
from bsmu.vision.widgets.viewers.graphics_view import GraphicsView


class _ImageItemLayer(QObject):
    max_id = 0

    image_updated = Signal(FlatImage)
    visibility_updated = Signal()

    def __init__(self, image: FlatImage = None, name: str = '',
                 visible: bool = True, opacity: float = 1):
        super().__init__()
        self.id = _ImageItemLayer.max_id
        _ImageItemLayer.max_id += 1

        self._image = None
        self.image = image #if image is not None else Image()
        self.name = name if name else 'Layer ' + str(self.id)
        self._visible = visible
        self.opacity = opacity

        self._displayed_image_cache = None
        # Store numpy array's data, because QImage uses it without copying,
        # and QImage will crash if it's data buffer will be deleted
        self._displayed_array_data = None

    @property
    def image_path(self) -> Path:
        return self.image.path

    @property  # TODO: this is slow. If we need only setter, there are alternatives without getter
    def image(self) -> FlatImage:
        return self._image

    @image.setter
    def image(self, value: FlatImage):
        if self._image != value:
            self._image = value
            self._on_image_updated()
            # self._image.updated.connect(self._on_image_updated)
            self._image.pixels_modified.connect(self._on_image_updated)

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        if self._visible != value:
            self._visible = value
            self.visibility_updated.emit()

    @property
    def displayed_image(self):
        if self._displayed_image_cache is None:
            if self.image.palette is None:
                # displayed_rgba_array = image_converter.converted_to_normalized_uint8(self.image.array)
                # displayed_rgba_array = image_converter.converted_to_rgba(displayed_rgba_array)

                displayed_rgba_array = image_converter.converted_to_rgba(self.image.array)
            else:
                displayed_rgba_array = self.image.colored_premultiplied_array

            self._displayed_array_data = displayed_rgba_array.data
            displayed_qimage_format = QImage.Format_RGBA8888_Premultiplied if displayed_rgba_array.itemsize == 1 \
                else QImage.Format_RGBA64_Premultiplied
            self._displayed_image_cache = image_converter.numpy_rgba_image_to_qimage(
                displayed_rgba_array, displayed_qimage_format)
        return self._displayed_image_cache

    def _on_image_updated(self):
        print('_ImageItemLayer _on_image_updated (image array updated or layer image changed)')
        self._displayed_image_cache = None
        self.image_updated.emit(self.image)


class _LayeredImageItem(QGraphicsObject):
    active_layer_changed = Signal(QGraphicsObject, QGraphicsObject)

    def __init__(self, parent: QGraphicsItem = None):
        super().__init__(parent)

        self.layers = []
        self.names_layers = {}
        self.active_layer = None

        self._bounding_rect = QRectF()

    def boundingRect(self):
        return self._bounding_rect

    def add_layer(self, image: FlatImage = None, name: str = '',
                  visible: bool = True, opacity: float = 1) -> _ImageItemLayer:
        layer = _ImageItemLayer(image, name, visible, opacity)
        self.layers.append(layer)
        self.names_layers[name] = layer
        # Calling update() several times normally results in just one paintEvent() call.
        # See QWidget::update() documentation.
        layer.image_updated.connect(self._on_layer_image_updated)
        layer.visibility_updated.connect(self.update)

        if len(self.layers) == 1:  # If was added first layer
            self.active_layer = layer
            self.active_layer_changed.emit(None, self.active_layer)
            self._update_bounding_rect()  # self.prepareGeometryChange() will call update() if this is necessary.
        else:
            self.update()

        return layer

    def layer(self, name: str) -> _ImageItemLayer:
        return self.names_layers.get(name)

    def _update_bounding_rect(self):
        self.prepareGeometryChange()

        if self.layers:
            image = self.layers[0].displayed_image
            image_rect = image.rect()
            self._bounding_rect = QRectF(image_rect)  # item position will be in the top left point of image
            # Item position will be in the center of image
            # self._bounding_rect = QRectF(-image_rect.width() / 2, -image_rect.height() / 2,
            #                              image_rect.width(), image_rect.height())
        else:
            self._bounding_rect = QRectF()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        for layer in self.layers:
            if layer.image is not None and layer.visible:
                painter.setOpacity(layer.opacity)
                painter.drawImage(self._bounding_rect.topLeft(), layer.displayed_image)

    def _on_layer_image_updated(self, image: FlatImage):
        self.update()


class LayeredImageViewer(DataViewer):
    # before_image_changed = Signal()
    # image_changed = Signal()
    # colormap_active_class_changed = Signal(int)
    data_name_changed = Signal(str)

    def __init__(self, data: Image = None, zoomable: bool = True):
        super().__init__(data)

        print('FlatImageViewer __init__')

        self.layered_image_item = _LayeredImageItem()
        self.layered_image_item.active_layer_changed.connect(self._on_active_layer_changed)

        self.graphics_scene = QGraphicsScene()
        self.graphics_scene.addItem(self.layered_image_item)

        self.graphics_view = GraphicsView(self.graphics_scene, zoomable)

        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self.graphics_view)
        self.setLayout(grid_layout)

    def add_layer(self, image: FlatImage = None, name: str = '',
                  visible: bool = True, opacity: float = 1) -> _ImageItemLayer:
        return self.layered_image_item.add_layer(image, name, visible, opacity)

    def layer(self, name: str) -> _ImageItemLayer:
        return self.layered_image_item.layer(name)

    @property
    def active_layer(self):
        return self.layered_image_item.active_layer

    @property
    def layers(self):
        return self.layered_image_item.layers

    @property
    def viewport(self):
        return self.graphics_view.viewport()

    def viewport_pos_to_image_pixel_coords(self, viewport_pos: QPoint):
        scene_pos = self.graphics_view.mapToScene(viewport_pos)
        layered_image_item_pos = self.layered_image_item.mapFromScene(scene_pos)
        return [round(layered_image_item_pos.y()), round(layered_image_item_pos.x())]

    def pos_to_image_pixel_coords(self, pos: QPoint):
        graphics_view_pos = self.graphics_view.mapFrom(self, pos)
        viewport_pos = self.viewport.mapFrom(self.graphics_view, graphics_view_pos)
        return self.viewport_pos_to_image_pixel_coords(viewport_pos)

    def center(self):
        print('center')
        self.graphics_view.centerOn(self.layered_image_item)

    def _on_active_layer_changed(self, old_active_layer: _ImageItemLayer, new_active_layer: _ImageItemLayer):
        if old_active_layer is not None:
            old_active_layer.image_updated.disconnect(self._on_active_layer_image_updated)
        if new_active_layer is not None:
            new_active_layer.image_updated.connect(self._on_active_layer_image_updated)

    def _on_active_layer_image_updated(self, image: FlatImage):
        self.data_name_changed.emit(image.path.name)
