from __future__ import annotations

from typing import TYPE_CHECKING

from bsmu.vision.plugins.windows.main import MainWindowPlugin, MainWindow, MenuBar, FileMenu, ViewMenu, ToolsMenu, \
    WindowsMenu, HelpMenu

if TYPE_CHECKING:
    from bsmu.vision.plugins.windows.main import MainMenu
    from typing import Tuple, Type


class RetinalFundusMenuBar(MenuBar):
    def __init__(self, menu_order: Tuple[MainMenu] = (FileMenu, ViewMenu, ToolsMenu, WindowsMenu, HelpMenu)):
        super().__init__(menu_order)


class RetinalFundusMainWindow(MainWindow):
    def __init__(self, title: str = '', menu_bar: MenuBar = None):
        super().__init__(title, RetinalFundusMenuBar() if menu_bar is None else menu_bar)


class RetinalFundusMainWindowPlugin(MainWindowPlugin):
    def __init__(self, main_window_cls: Type[MainWindow] | None = None):
        super().__init__(RetinalFundusMainWindow if main_window_cls is None else main_window_cls)