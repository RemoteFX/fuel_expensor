"""Startup smoke test for the date-selection GUI."""

import sys
import tkinter as tk

import pytest

from src.gui import date_selection
from src.expense_weeks import create_selection, save_selection


def test_date_selection_entrypoint_starts_and_closes(monkeypatch, tmp_path):
    """Run the real entry point briefly to catch window-construction failures."""
    processed_directory = tmp_path / "processed"
    processed_directory.mkdir()
    monkeypatch.setattr(
        date_selection, "DEFAULT_RECEIPTS_DIRECTORY", processed_directory
    )
    monkeypatch.setattr(
        date_selection, "DEFAULT_SELECTION_PATH", processed_directory / "selection.json"
    )
    monkeypatch.setattr(sys, "argv", ["date_selection.py"])
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


def test_saved_selection_is_restored_through_validated_model(tmp_path, monkeypatch):
    selection_path = tmp_path / "selection.json"
    save_selection(
        create_selection(
            ["2025-04-02", "2025-04-08"],
            created_at="2025-04-09T10:00:00",
        ),
        selection_path,
    )
    monkeypatch.setattr(date_selection, "DEFAULT_SELECTION_PATH", selection_path)

    selected_dates, error = date_selection.DateSelectionApp._restore_saved_selection()

    assert selected_dates == {"2025-04-02", "2025-04-08"}
    assert error is None


def test_invalid_saved_selection_is_reported_instead_of_silently_cleared(
    tmp_path, monkeypatch
):
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        '{"version": 1, "week_start_day": "monday", '
        '"created_at": "2025-04-09T10:00:00", "weeks": [{"selected_dates": [42]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(date_selection, "DEFAULT_SELECTION_PATH", selection_path)

    selected_dates, error = date_selection.DateSelectionApp._restore_saved_selection()

    assert selected_dates == set()
    assert error is not None
