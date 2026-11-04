"""Startup smoke test for the date-selection GUI."""

import tkinter as tk

import pytest

from src.gui import date_selection


def test_date_selection_entrypoint_starts_and_closes(monkeypatch):
    """Run the real entry point briefly to catch window-construction failures."""
    tk_root = tk.Tk
    try:
        probe = tk_root()
    except tk.TclError as error:
        pytest.skip("Tk display is unavailable: {}".format(error))
    probe.destroy()

    def create_auto_closing_root():
        root = tk_root()
        root.after(100, root.destroy)
        return root

    monkeypatch.setattr(date_selection.tk, "Tk", create_auto_closing_root)

    date_selection.main()
