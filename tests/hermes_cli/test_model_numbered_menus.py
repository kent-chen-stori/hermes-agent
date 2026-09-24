"""The SSH-safe model picker bypasses native ncurses without changing other menus."""

import argparse
from types import SimpleNamespace
from unittest.mock import Mock


def test_model_parser_accepts_numbered_option():
    from hermes_cli.subcommands.model import build_model_parser
    parser = argparse.ArgumentParser()
    build_model_parser(parser.add_subparsers(dest="command"), cmd_model=lambda args: None)
    assert parser.parse_args(["model", "--numbered"]).numbered is True
    assert parser.parse_args(["model"]).numbered is False


def test_numbered_model_command_bypasses_curses_and_restores_scope(monkeypatch):
    import hermes_cli.curses_ui as ui
    import hermes_cli.main as main

    monkeypatch.setattr(main, "_require_tty", lambda command: None)
    monkeypatch.setattr(ui.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")
    wrapper = Mock(side_effect=AssertionError("curses should not be loaded"))
    import curses
    monkeypatch.setattr(curses, "wrapper", wrapper)
    chosen = []

    def select_provider_and_model(args=None):
        chosen.append(ui.curses_radiolist("Provider", ["Nous", "Codex"], selected=0))

    monkeypatch.setattr(main, "select_provider_and_model", select_provider_and_model)
    main.cmd_model(SimpleNamespace(numbered=True, refresh=False))

    assert chosen == [1]
    assert not ui._numbered_menus.get()
    wrapper.assert_not_called()


def test_numbered_menu_scope_restored_on_exception():
    from hermes_cli.curses_ui import _numbered_menus, numbered_menus
    try:
        with numbered_menus():
            assert _numbered_menus.get()
            raise ValueError("interrupted")
    except ValueError:
        pass
    assert not _numbered_menus.get()
