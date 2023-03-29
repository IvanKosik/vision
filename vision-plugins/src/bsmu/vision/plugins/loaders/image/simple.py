from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import skimage.io

from bsmu.vision.core.image.base import FlatImage
from bsmu.vision.plugins.loaders.image.base import ImageFileLoaderPlugin, ImageFileLoader

if TYPE_CHECKING:
    from pathlib import Path


class SimpleImageFileLoaderPlugin(ImageFileLoaderPlugin):
    def __init__(self):
        super().__init__(SimpleImageFileLoader)


class SimpleImageFileLoader(ImageFileLoader):
    _FORMATS = ('png', 'jpg', 'jpeg', 'bmp', 'tiff', 'tif')

    def _load_file(self, path: Path, palette=None, as_gray=False, **kwargs):
        logging.info('Load Simple Image')

        pixels = skimage.io.imread(str(path), as_gray=as_gray or palette is not None, **kwargs)
        flat_image = FlatImage(pixels, palette, path)
        if palette is not None:
            flat_image.pixels = np.rint(flat_image.pixels).astype(np.uint8)
        return flat_image
