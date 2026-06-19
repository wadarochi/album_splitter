"""TUI smoke tests for cue-finder."""

import asyncio
import pytest

pytest.importorskip("textual")

from textual.widgets import Button, Input

from cue_finder.tui.app import CueFinderApp, FilePickerScreen, launch_tui


class TestTUIInstantiation:
    def test_app_instantiation(self):
        """CueFinderApp can be instantiated without a running event loop."""
        app = CueFinderApp()
        assert app is not None

    def test_app_bindings(self):
        """CueFinderApp defines the expected key bindings."""
        keys = {binding.key for binding in CueFinderApp.BINDINGS}
        assert "ctrl+s" in keys
        assert "ctrl+r" in keys
        assert "ctrl+q" in keys

    def test_file_picker_screen(self):
        """FilePickerScreen composes with an Input and two Buttons."""

        async def _run():
            app = CueFinderApp()
            async with app.run_test() as pilot:
                _ = app.push_screen(FilePickerScreen())
                await pilot.pause()
                screen = app.screen
                input_widget = screen.query_one(Input)
                buttons = list(screen.query(Button))
                assert input_widget is not None
                assert len(buttons) == 2

        asyncio.run(_run())

    def test_launch_function_exists(self):
        """launch_tui is callable from cue_finder.tui.app."""
        assert callable(launch_tui)
