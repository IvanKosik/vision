from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject, Signal

from bsmu.vision.core.bbox import BBox
from bsmu.vision.core.data import Data
from bsmu.vision.core.image.base import Image
from bsmu.vision.core.visibility import Visibility

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Type, List

    from bsmu.vision.core.palette import Palette


class ImageLayer(QObject):
    max_id = 0

    image_updated = Signal(Image)

    image_shape_changed = Signal(object, object)
    image_pixels_modified = Signal(BBox)

    def __init__(self, image: Image | None = None, name: str = '', visibility: Visibility = None):
        super().__init__()
        self.id = ImageLayer.max_id
        ImageLayer.max_id += 1

        self.path = None
        self.palette = None

        self._image = None
        self.image = image  # if image is not None else Image()
        self.name = name if name else 'Layer ' + str(self.id)

        self._visibility = Visibility() if visibility is None else visibility

    @property
    def image_path(self) -> Path | None:
        return self.image.path if self.image is not None else None

    @property
    def image_palette(self) -> Palette:
        return self.image.palette

    @property
    def image_pixels(self) -> np.ndarray:
        return self.image.pixels

    @property
    def image_path_name(self) -> str:
        return self.image_path.name if self.image_path is not None else ''

    @property  # TODO: this is slow. If we need only setter, there are alternatives without getter
    def image(self) -> Image:
        return self._image

    @image.setter
    def image(self, value: Image):
        if self._image == value:
            return

        if self._image is not None:
            self._image.pixels_modified.disconnect(self.image_pixels_modified)
            self._image.shape_changed.disconnect(self.image_shape_changed)

        self._image = value
        self._on_image_updated()

        if self._image is not None:
            if self._image.path is not None:
                self.path = self._image.path.parent
            self.palette = self._image.palette
            self._image.pixels_modified.connect(self.image_pixels_modified)
            self._image.shape_changed.connect(self.image_shape_changed)

    @property
    def is_indexed(self) -> bool:
        return self._image.is_indexed

    @property
    def is_image_pixels_valid(self) -> bool:
        return self.image is not None and self.image.is_pixels_valid

    @property
    def visibility(self) -> Visibility:
        return self._visibility

    def _on_image_updated(self):
        self.image_updated.emit(self.image)


class LayeredImage(Data):
    layer_adding = Signal(ImageLayer, int)
    layer_added = Signal(ImageLayer, int)
    layer_removing = Signal(ImageLayer, int)
    layer_removed = Signal(ImageLayer, int)

    def __init__(self, path: Path = None):
        super().__init__(path)

        self._layers = []
        self._layer_by_name = {}

    @property
    def layers(self) -> List[ImageLayer]:
        return self._layers

    def layer_by_name(self, name: str) -> ImageLayer | None:
        return self._layer_by_name.get(name)

    def add_layer(self, layer: ImageLayer):
        layer_index = len(self._layers)
        self.layer_adding.emit(layer, layer_index)
        self._layers.append(layer)
        self._layer_by_name[layer.name] = layer
        self.layer_added.emit(layer, layer_index)

    def add_layer_from_image(
            self, image: Image | None, name: str = '', visibility: Visibility = None) -> ImageLayer:
        image_layer = ImageLayer(image, name, visibility)
        self.add_layer(image_layer)
        return image_layer

    def add_layer_or_modify_image(self, name: str, image: Image) -> ImageLayer:
        layer = self.layer_by_name(name)
        if layer is None:
            layer = self.add_layer_from_image(image, name)
        else:
            layer.image = image
        return layer

    def add_layer_or_modify_pixels(
            self,
            name: str,
            pixels: np.array,
            image_type: Type[Image],
            palette: Palette = None,
            visibility: Visibility = None,
    ) -> ImageLayer:
        layer = self.layer_by_name(name)
        if layer is None:
            layer = self.add_layer_from_image(image_type(pixels, palette), name, visibility)
        elif layer.image is None:
            layer.image = image_type(pixels, palette)
        else:
            layer.image.pixels = pixels
            layer.image.emit_pixels_modified()
        return layer

    def remove_layer(self, layer: ImageLayer):
        layer_index = self._layers.index(layer)
        self.layer_removing.emit(layer, layer_index)
        self._layers.remove(layer)
        del self._layer_by_name[layer.name]
        self.layer_removed.emit(layer, layer_index)

    def contains_layer(self, name: str) -> bool:
        return self.layer_by_name(name) is not None

    def print_layers(self):
        for index, layer in enumerate(self.layers):
            print(f'Layer {index}: {layer.name}')

'''
class LayerImageDependencyController(QObject):
    def __init__(self, master_layer: ImageLayer, slave_layers: List[ImageLayer]):
        super().__init__()

        self.master_layer = master_layer
        self.slave_layers = slave_layers

        self.master_layer.image_updated(self._update_slave_layers)

    def is_corresponding_layer_image(self, slave_layer: ImageLayer):
        return self.master_layer.path /
        return file_path = layer.path
        ...

    def corresponding_layer_image(self, slave_layer: ImageLayer):
        file_path = layer.path / next_file_name
        layer.image = self.file_loading_manager.load_file(file_path, palette=layer.palette)

    def _update_slave_layer_image(self, slave_layer: ImageLayer):


    def _update_slave_layers(self):
        for slave_layer in self.slave_layers:
            self._update_slave_layer_image(slave_layer)
'''
