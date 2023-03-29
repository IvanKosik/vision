from __future__ import annotations

import argparse
import locale
import logging
import sys
import traceback
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QCoreApplication
from PySide6.QtWidgets import QApplication

from bsmu.vision.app.plugin_manager import PluginManager
from bsmu.vision.core.concurrent import ThreadPool
from bsmu.vision.core.config.united import UnitedConfig
from bsmu.vision.core.data_file import DataFileProvider
from bsmu.vision.core.freeze import is_app_frozen
from bsmu.vision.core.plugins.base import Plugin
from bsmu.vision.dnn.config import OnnxConfig

if TYPE_CHECKING:
    from typing import List


class App(QObject, DataFileProvider):
    plugin_enabled = Signal(Plugin)
    plugin_disabled = Signal(Plugin)

    def __init__(self, name: str, version: str):
        name_version = f'{name} {version}'

        arg_parser = argparse.ArgumentParser(prog=name_version)
        arg_parser.add_argument('-l', '--log-level', default=logging.getLevelName(logging.INFO))
        self._args = arg_parser.parse_args()

        self._init_logging()

        # Call the base method after the logging initialization
        super().__init__()

        logging.info(name_version)
        if not is_app_frozen():
            logging.info(f'Prefix: {sys.prefix}')
        logging.info(f'Executable: {sys.executable}')

        # Set to users preferred locale to output correct decimal point (comma or point):
        locale.setlocale(locale.LC_NUMERIC, '')

        self._config = UnitedConfig(type(self), App)

        self._gui_enabled = self._config.value('enable-gui')
        self._qApp = QApplication(sys.argv) if self._gui_enabled else QCoreApplication(sys.argv)
        self._qApp.setApplicationName(name)
        self._qApp.setApplicationVersion(version)

        ThreadPool.init_executor(self._config.value('max_thread_count'))

        if self._config.value('warn-with-traceback'):
            warnings.showwarning = warn_with_traceback
            warnings.simplefilter('always')

        OnnxConfig.providers = self._config.value('onnx_providers')

        self._plugin_manager = PluginManager(self)
        self._plugin_manager.plugin_enabled.connect(self.plugin_enabled)
        self._plugin_manager.plugin_disabled.connect(self.plugin_disabled)

        configured_plugins = self._config.value('plugins')
        if configured_plugins is not None:
            self._plugin_manager.enable_plugins(configured_plugins)

    @property
    def gui_enabled(self) -> bool:
        return self._gui_enabled

    def enabled_plugins(self) -> List[Plugin]:
        return self._plugin_manager.enabled_plugins

    def run(self):
        sys.exit(self._qApp.exec())

    def _init_logging(self):
        log_level_str = self._args.log_level
        log_level = getattr(logging, log_level_str.upper(), None)
        if not isinstance(log_level, int):
            raise ValueError(f'Invalid log level: {log_level_str}')
        log_format = '\t\t\t\t\t%(asctime)s %(levelname)s\t\t%(filename)s %(lineno)d\t\t%(funcName)s\n' \
                     '%(message)s'
        if is_app_frozen():
            log_path = Path('logs')
            try:
                log_path.mkdir(exist_ok=True)
            except:
                # Create log files without common directory
                # if the application has no rights to create the directory
                log_path = Path('.')
            logging.basicConfig(
                filename=log_path / f'log-{log_level_str.lower()}.log',
                format=log_format,
                level=log_level,
                encoding='utf-8')
        else:
            logging.basicConfig(format=log_format, level=log_level, stream=sys.stdout)


def warn_with_traceback(message, category, filename, lineno, file=None, line=None):
    log = file if hasattr(file, 'write') else sys.stderr
    traceback.print_stack(file=log)
    log.write(warnings.formatwarning(message, category, filename, lineno, line))
