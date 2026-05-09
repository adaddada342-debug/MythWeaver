from __future__ import annotations

import json

from mythweaver.core.settings import get_settings
from mythweaver.tools.facade import AgentToolFacade


def run_tui() -> None:
    """Run a lightweight Textual UI when installed, otherwise print a useful terminal view."""

    try:
        from textual.app import App, ComposeResult
        from textual.widgets import Footer, Header, Static
    except ImportError:
        facade = AgentToolFacade(get_settings())
        print("MythWeaver deterministic tools")
        print(json.dumps(facade.list_tools(), indent=2))
        print("\nInstall project dependencies to enable the interactive Textual TUI.")
        return

    class MythWeaverApp(App):
        CSS = "Screen { padding: 1 2; }"

        def compose(self) -> ComposeResult:
            facade = AgentToolFacade(get_settings())
            yield Header(show_clock=True)
            yield Static("MythWeaver: local modpack intelligence for external agents")
            yield Static(json.dumps(facade.list_tools(), indent=2))
            yield Footer()

    MythWeaverApp().run()

