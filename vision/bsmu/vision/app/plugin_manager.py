from __future__ import annotations

import importlib
import re
from typing import List, Union

from PySide2.QtCore import QObject, Signal

from bsmu.vision.app.plugin import Plugin


class PluginManager(QObject):
    plugin_enabled = Signal(Plugin)
    plugin_disabled = Signal(Plugin)

    def __init__(self, app: App):
        super().__init__()

        self.app = app

        ### self._plugin_expression_pattern_str = r'((?P<alias>.+)=)?(?P<full_name>[^=\(]+)(\((?P<params>.*)\))?'
        self._plugin_expression_pattern_str = \
            r'((?P<alias>.+)=)?(?P<full_name>[^->\(]+)(\((?P<params>.*)\))?\s*(->(?P<replace_full_name>.+))?'
        self._plugin_expression_pattern = re.compile(self._plugin_expression_pattern_str)

        self._created_plugins = {}  # { full_name: Plugin }
        self._enabled_plugins = {}  # { full_name: Plugin }
        self._aliases_plugins = {}  # { alias: Plugin }

    def _enable_created_plugin(self, plugin: Plugin, replace_full_name: str = None):
        full_name = replace_full_name or plugin.full_name()

        assert full_name in self._created_plugins, \
            f'Plugin {full_name} have to be in |self._created_plugins|'

        plugin.enabled.connect(self.plugin_enabled)
        plugin.disabled.connect(self.plugin_disabled)

        plugin.enable()
        self._enabled_plugins[full_name] = plugin

    def _create_plugin(self, full_name: str, params: str, replace_full_name: str):
        plugin = self._created_plugins.get(full_name)   #### or self._aliases_plugins.get(full_name)
        if plugin is None:
            module_name, class_name = full_name.rsplit(".", 1)
            plugin_class = getattr(importlib.import_module(module_name), class_name)

            plugins_as_params = []
            if params is not None:
                params = params.split(',')
                for p in params:
                    p = p.replace(' ', '')
                    plugin_as_param = self._aliases_plugins.get(p)
                    plugins_as_params.append(plugin_as_param or p)

            plugin = plugin_class(self.app, *plugins_as_params)
            self._created_plugins[replace_full_name or plugin.full_name()] = plugin

        return plugin

    def _enable_plugin_created_from_expression(self, plugin_expression: str):
        plugin_expression = plugin_expression.replace(' ', '')

        match = self._plugin_expression_pattern.match(plugin_expression)
        alias = match.group('alias')
        full_name = match.group('full_name')
        params = match.group('params')
        replace_full_name = match.group('replace_full_name')

        plugin = self._enabled_plugins.get(full_name)
        if plugin is None:
            if replace_full_name is not None:
                replace_full_name = replace_full_name.replace(' ', '')
            plugin = self._create_plugin(full_name, params, replace_full_name)
            self._enable_created_plugin(plugin, replace_full_name)

        if alias is not None:
            self._aliases_plugins[alias] = plugin

        return plugin

    def enable_plugin(self, plugin_expression: Union[str, Plugin]):
        if isinstance(plugin_expression, Plugin):
            self._enable_created_plugin(plugin_expression)
            return plugin_expression

        return self._enable_plugin_created_from_expression(plugin_expression)

    def enable_plugins(self, plugin_expressions: List[str]):
        for plugin_expression in plugin_expressions:
            self.enable_plugin(plugin_expression)

    def enabled_plugin(self, full_name):
        return self._enabled_plugins.get(full_name)
