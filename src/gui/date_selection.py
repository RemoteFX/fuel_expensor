"""Tkinter interface for selecting travel dates by expense week."""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, ttk
from typing import Dict, List, Set

from src.expense_weeks import (
    DEFAULT_SELECTION_PATH,
    create_selection,
    get_week_bounds,
    save_selection,
    toggle_week_dates,
    weekdays_in_week,
)
from src.receipt_matching import run_matching_step


class DateSelectionApp:
    """Interactive three-month calendar and expense-details window."""

    BG = "#f3f6fd"
    CARD = "#ffffff"
    INK = "#101b3d"
    MUTED = "#71809e"
    BLUE = "#1769e8"
    PALE_BLUE = "#e8f0ff"
    BORDER = "#d8e0ef"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Fuel Expensor - Select Dates")
        self.root.geometry("1120x760")
        self.root.minsize(1000, 690)
        self.root.configure(bg=self.BG)

        today = date.today()
        self.first_month = today.replace(day=1)
        self.display_start = self.first_month
        self.display_end = self._month_end(self._add_months(self.first_month, 2))
        self.selected_dates: Set[str] = set()
        self.day_buttons: Dict[str, ttk.Button] = {}
        self.day_frames: Dict[str, ttk.Frame] = {}
        self.week_receipt_status: Dict[str, bool] = {}
        self.mode = tk.StringVar(value="weeks")
        self.trip_am = tk.BooleanVar(value=True)
        self.trip_pm = tk.BooleanVar(value=True)
        # Placeholder settings for the mock-up; Step 4 persists selected dates only.
        self.fuel_type = tk.StringVar(value="Petrol")
        self.vehicle = tk.StringVar(value="Clio 172")
        self.additional_options_open = tk.BooleanVar(value=False)

        self._configure_styles()
        self._build_layout()
        self._set_mode(self.mode.get())
        self._render_calendars()

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        """Return the first day of a month offset from ``value``."""
        month_index = value.year * 12 + value.month - 1 + months
        year, month = divmod(month_index, 12)
        return date(year, month + 1, 1)

    @staticmethod
    def _month_end(value: date) -> date:
        """Return the last day in the month containing ``value``."""
        return DateSelectionApp._add_months(value, 1) - timedelta(days=1)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 9), foreground=self.INK)
        style.configure("App.TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD)
        style.configure("DayBorder.TFrame", background=self.CARD, padding=0)
        style.configure(
            "MatchedBorder.TFrame", background="#16803c", padding=2
        )
        style.configure(
            "UnmatchedBorder.TFrame", background="#d97706", padding=2
        )
        style.configure("Header.TLabel", background=self.BG, foreground=self.INK,
                        font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED,
                        font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=self.CARD, foreground=self.INK,
                        font=("Segoe UI", 11, "bold"))
        style.configure("Body.TLabel", background=self.CARD, foreground=self.INK)
        style.configure("Muted.TLabel", background=self.CARD, foreground=self.MUTED)
        style.configure("Weekday.TLabel", background=self.CARD, foreground=self.MUTED,
                        font=("Segoe UI", 8))
        style.configure("Month.TLabel", background=self.CARD, foreground=self.INK,
                        font=("Segoe UI", 10, "bold"))
        style.configure("Selected.TButton", background=self.BLUE, foreground="white",
                        padding=4, borderwidth=0)
        style.map("Selected.TButton", background=[("active", "#0f56c5")],
                  foreground=[("active", "white")])
        style.configure("Day.TButton", background=self.CARD, foreground=self.INK,
                        padding=4, borderwidth=0)
        style.map("Day.TButton", background=[("active", self.PALE_BLUE)])
        style.configure("MutedDay.TButton", background=self.CARD,
                        foreground="#aab4c8", padding=4, borderwidth=0)
        style.configure("Primary.TButton", background=self.BLUE, foreground="white",
                        padding=(12, 9), borderwidth=0, font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton", background=[("active", "#0f56c5")],
                  foreground=[("active", "white")])
        style.configure("Mode.TButton", padding=(9, 6), borderwidth=1)
        style.configure("ModeActive.TButton", background=self.BLUE, foreground="white",
                        padding=(9, 6), borderwidth=0)
        style.map("ModeActive.TButton", background=[("active", "#0f56c5")],
                  foreground=[("active", "white")])
        style.configure("TEntry", padding=7)
        style.configure("TCombobox", padding=6)
        style.configure("TCheckbutton", background=self.CARD)
        style.configure("TSeparator", background=self.BORDER)

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=(18, 14))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="▣  Fuel Expensor", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Select your dates and configure your expense details",
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=(38, 0), pady=(0, 2))

        content = ttk.Frame(outer, style="App.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=7, uniform="content")
        content.columnconfigure(1, weight=3, uniform="content")
        content.rowconfigure(0, weight=1)
        self.calendar_card = ttk.Frame(
            content, style="Card.TFrame", padding=12, relief="solid"
        )
        self.calendar_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.settings_card = ttk.Frame(
            content, style="Card.TFrame", padding=14, relief="solid"
        )
        self.settings_card.grid(row=0, column=1, sticky="nsew", padx=(0, 0))
        self._build_calendar_panel()
        self._build_settings_panel()
        self._build_footer(outer)

    def _build_calendar_panel(self) -> None:
        heading = ttk.Frame(self.calendar_card, style="Card.TFrame")
        heading.pack(fill="x", pady=(0, 10))
        ttk.Label(heading, text="▦  Select Dates", style="CardTitle.TLabel").pack(
            side="left"
        )

        toolbar = ttk.Frame(self.calendar_card, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="‹", width=3, command=lambda: self._shift_months(-3)).pack(
            side="left"
        )
        self.period_label = ttk.Label(
            toolbar, style="Body.TLabel", anchor="center", width=22
        )
        self.period_label.pack(side="left", padx=6)
        ttk.Button(toolbar, text="›", width=3, command=lambda: self._shift_months(3)).pack(
            side="left"
        )

        self.mode_buttons: Dict[str, ttk.Button] = {}
        for value, label in (
            ("weeks", "▦  Select Weeks"),
            ("custom", "✎  Custom"),
        ):
            button = ttk.Button(
                toolbar,
                text=label,
                style="ModeActive.TButton" if value == self.mode.get() else "Mode.TButton",
                command=lambda selected=value: self._set_mode(selected),
            )
            button.pack(side="left", padx=(8 if value == "weeks" else 4, 0))
            self.mode_buttons[value] = button

        self.mode_hint = tk.StringVar()
        ttk.Label(
            self.calendar_card,
            textvariable=self.mode_hint,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 4))

        self.months_frame = ttk.Frame(self.calendar_card, style="Card.TFrame")
        self.months_frame.pack(fill="both", expand=True)
        for column in range(3):
            self.months_frame.columnconfigure(column, weight=1, uniform="months")
        self.months_frame.rowconfigure(0, weight=1)

        legend = ttk.Frame(self.calendar_card, style="Card.TFrame")
        legend.pack(fill="x", pady=(10, 0))
        ttk.Label(legend, text="● Selected day", style="Muted.TLabel").pack(
            side="left", padx=(2, 12)
        )
        ttk.Label(legend, text="○ Available day", style="Muted.TLabel").pack(
            side="left", padx=12
        )
        ttk.Label(
            legend, text="Green outline: receipt found", style="Muted.TLabel"
        ).pack(side="left", padx=12)
        ttk.Label(
            legend, text="Orange outline: no receipt", style="Muted.TLabel"
        ).pack(side="left", padx=12)
        ttk.Label(legend, text="Clear Selection", style="Muted.TLabel").pack(
            side="right"
        )
        ttk.Button(
            legend, text="⌫", width=3, command=self._clear_selection
        ).pack(side="right", padx=(0, 6))

        self.match_status_var = tk.StringVar()
        self.match_status_label = ttk.Label(
            self.calendar_card,
            textvariable=self.match_status_var,
            style="Muted.TLabel",
            justify="left",
            wraplength=900,
        )

        self.summary_var = tk.StringVar()
        self.summary_label = tk.Label(
            self.calendar_card,
            textvariable=self.summary_var,
            bg=self.PALE_BLUE,
            fg=self.INK,
            anchor="w",
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        )
        self.summary_label.pack(fill="x", pady=(10, 0))

    def _build_settings_panel(self) -> None:
        heading = ttk.Frame(self.settings_card, style="Card.TFrame")
        heading.pack(fill="x", pady=(0, 12))
        ttk.Label(heading, text="⚙  Settings", style="CardTitle.TLabel").pack(
            side="left"
        )
        ttk.Button(
            heading,
            text="☷  Manage Settings",
            command=self._show_settings_placeholder,
        ).pack(side="right")

        self._field_label(self.settings_card, "Start Postcode")
        # Placeholder only: this fake postcode is for the visual mock-up, not a real address.
        self._placeholder_entry(self.settings_card, "ZZ99 9ZZ")
        self._field_label(self.settings_card, "Finish Postcode")
        # Placeholder only: this fake postcode is for the visual mock-up, not a real address.
        self._placeholder_entry(self.settings_card, "ZZ99 9ZY")

        self._field_label(self.settings_card, "Fuel Type")
        ttk.Combobox(
            self.settings_card,
            textvariable=self.fuel_type,
            values=("Petrol", "Diesel", "Electric"),
            state="readonly",
        ).pack(fill="x", pady=(0, 9))
        self._field_label(self.settings_card, "Vehicle (optional)")
        ttk.Combobox(
            self.settings_card,
            textvariable=self.vehicle,
            values=("Clio 172", "Other"),
            state="readonly",
        ).pack(fill="x", pady=(0, 12))

        ttk.Separator(self.settings_card).pack(fill="x", pady=(0, 12))
        ttk.Checkbutton(
            self.settings_card,
            text="🚘  AM Trip (home → work)",
            variable=self.trip_am,
            command=self._refresh_counts,
        ).pack(anchor="w", pady=4)
        ttk.Checkbutton(
            self.settings_card,
            text="▣  PM Trip (work → home)",
            variable=self.trip_pm,
            command=self._refresh_counts,
        ).pack(anchor="w", pady=4)

        options = ttk.Frame(self.settings_card, style="Card.TFrame")
        options.pack(fill="x", pady=(14, 0))
        ttk.Checkbutton(
            options,
            text="Additional Options",
            variable=self.additional_options_open,
            command=self._toggle_additional_options,
        ).pack(anchor="w")
        self.additional_options = ttk.Label(
            options,
            text="Settings shown here are visual placeholders.\nThey are not included in the date-selection file.",
            style="Muted.TLabel",
            wraplength=250,
            justify="left",
        )
        self.additional_options.pack(anchor="w", pady=(6, 0))
        self.additional_options.pack_forget()

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent, style="App.TFrame", padding=(0, 12, 0, 0))
        footer.pack(fill="x")
        ttk.Separator(footer).pack(fill="x", pady=(0, 12))
        self.total_var = tk.StringVar(value="Total: 0 days • 0 journeys")
        ttk.Button(footer, text="↻  Reset Selection", command=self._clear_selection).pack(
            side="left"
        )
        ttk.Button(
            footer,
            text="Match receipts",
            command=self._match_receipts,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            footer, textvariable=self.total_var, style="Subtitle.TLabel", anchor="center"
        ).pack(side="left", fill="x", expand=True)
        self.submit_button = ttk.Button(
            footer,
            text="▣  Submit Expense  →",
            style="Primary.TButton",
            command=self._save_selection,
            state="disabled",
        )
        self.submit_button.pack(side="right")

    @staticmethod
    def _field_label(parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text, style="Body.TLabel").pack(
            anchor="w", pady=(0, 4)
        )

    @staticmethod
    def _placeholder_entry(parent: ttk.Frame, value: str) -> None:
        entry = ttk.Entry(parent)
        entry.insert(0, value)
        entry.pack(fill="x", pady=(0, 9))

    def _toggle_additional_options(self) -> None:
        if self.additional_options_open.get():
            self.additional_options.pack(anchor="w", pady=(6, 0))
        else:
            self.additional_options.pack_forget()

    def _show_settings_placeholder(self) -> None:
        messagebox.showinfo(
            "Settings",
            "The expense details are visual placeholders and are not saved yet.",
            parent=self.root,
        )

    def _set_mode(self, mode: str) -> None:
        self.mode.set(mode)
        labels = {
            "weeks": "Click any date to select or clear that week's Monday–Friday workdays.",
            "custom": "Click dates individually to select or clear them, including weekends.",
        }
        self.mode_hint.set(labels[mode])
        for value, button in self.mode_buttons.items():
            button.configure(
                style="ModeActive.TButton" if value == mode else "Mode.TButton"
            )

    def _shift_months(self, amount: int) -> None:
        self.first_month = self._add_months(self.first_month, amount)
        self.display_start = self.first_month
        self.display_end = self._month_end(self._add_months(self.first_month, 2))
        self._render_calendars()

    def _render_calendars(self) -> None:
        for child in self.months_frame.winfo_children():
            child.destroy()
        self.day_buttons.clear()
        self.day_frames.clear()
        last_month = self._add_months(self.first_month, 2)
        self.period_label.configure(
            text="{} – {}".format(
                self.first_month.strftime("%b %Y"), last_month.strftime("%b %Y")
            )
        )
        for column in range(3):
            month = self._add_months(self.first_month, column)
            self._build_month(self.months_frame, month, column)
        self._refresh_calendar_buttons()

    def _build_month(self, parent: ttk.Frame, month: date, column: int) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=(4, 6))
        panel.grid(row=0, column=column, sticky="nsew")
        if column:
            ttk.Separator(parent, orient="vertical").grid(
                row=0, column=column, sticky="nsw"
            )
        ttk.Label(
            panel, text=month.strftime("%B %Y"), style="Month.TLabel", anchor="center"
        ).grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 10))
        for weekday, label in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            ttk.Label(
                panel, text=label, style="Weekday.TLabel", anchor="center"
            ).grid(row=1, column=weekday, sticky="ew", pady=(0, 4))
            panel.columnconfigure(weekday, weight=1, uniform="days")

        calendar_month = calendar.Calendar(firstweekday=calendar.MONDAY)
        weeks = calendar_month.monthdayscalendar(month.year, month.month)
        for row_index, week in enumerate(weeks, start=2):
            for weekday, day_number in enumerate(week):
                if day_number == 0:
                    continue
                current = date(month.year, month.month, day_number)
                self._add_day_button(panel, current, row_index, weekday)

    def _add_day_button(
        self, parent: ttk.Frame, current: date, row: int, column: int
    ) -> None:
        date_text = current.isoformat()
        selected = date_text in self.selected_dates
        day_frame = ttk.Frame(parent, style="DayBorder.TFrame")
        day_frame.grid(row=row, column=column, sticky="nsew", padx=1, pady=2)
        button = ttk.Button(
            day_frame,
            text=str(current.day),
            width=3,
            style="Selected.TButton" if selected else "Day.TButton",
            command=lambda value=current: self._on_date_click(value),
        )
        button.pack(fill="both", expand=True)
        self.day_buttons[date_text] = button
        self.day_frames[date_text] = day_frame

    def _on_date_click(self, selected_date: date) -> None:
        date_text = selected_date.isoformat()
        if self.mode.get() == "weeks":
            week_start, _ = get_week_bounds(selected_date)
            enabled = self._enabled_dates_in_week(week_start)
            self.selected_dates = toggle_week_dates(
                self.selected_dates, week_start, enabled
            )
        else:
            if date_text in self.selected_dates:
                self.selected_dates.remove(date_text)
            else:
                self.selected_dates.add(date_text)
        self.week_receipt_status.clear()
        self.match_status_var.set("")
        self.match_status_label.pack_forget()
        self._refresh_calendar_buttons()

    def _enabled_dates_in_week(self, week_start: date) -> List[str]:
        """List visible Monday-to-Friday dates in an expense week."""
        return [
            current.isoformat()
            for current in weekdays_in_week(week_start)
            if self.display_start
            <= current
            <= self.display_end
        ]

    def _refresh_calendar_buttons(self) -> None:
        for date_text, button in self.day_buttons.items():
            is_selected = date_text in self.selected_dates
            button.configure(
                style=(
                    "Selected.TButton"
                    if is_selected
                    else "Day.TButton"
                )
            )
            week_id = get_week_bounds(date_text)[0].isoformat()
            has_receipt = self.week_receipt_status.get(week_id)
            frame_style = "DayBorder.TFrame"
            if is_selected and has_receipt is True:
                frame_style = "MatchedBorder.TFrame"
            elif is_selected and has_receipt is False:
                frame_style = "UnmatchedBorder.TFrame"
            self.day_frames[date_text].configure(style=frame_style)
        self._refresh_counts()

    def _refresh_counts(self) -> None:
        selected_count = len(self.selected_dates)
        selected_weeks = len(
            {get_week_bounds(value)[0].isoformat() for value in self.selected_dates}
        )
        journeys_per_day = int(self.trip_am.get()) + int(self.trip_pm.get())
        journeys = selected_count * journeys_per_day
        self.summary_var.set(
            "ⓘ  {} weeks selected  •  {} expense days  •  {} journeys (AM + PM)".format(
                selected_weeks, selected_count, journeys
            )
        )
        self.total_var.set(
            "Total: {} days  •  {} journeys ({} AM + {} PM)".format(
                selected_count,
                journeys,
                selected_count if self.trip_am.get() else 0,
                selected_count if self.trip_pm.get() else 0,
            )
        )
        self.submit_button.configure(
            state="normal" if selected_count else "disabled"
        )

    def _clear_selection(self) -> None:
        self.selected_dates.clear()
        self.week_receipt_status.clear()
        self.match_status_var.set("")
        self.match_status_label.pack_forget()
        self._refresh_calendar_buttons()

    def _save_selection(self) -> None:
        if not self.selected_dates:
            self.submit_button.configure(state="disabled")
            return
        selection = create_selection(self.selected_dates)
        try:
            saved_path = save_selection(selection, DEFAULT_SELECTION_PATH)
        except OSError as error:
            messagebox.showerror(
                "Could not save selection", str(error), parent=self.root
            )
            return
        messagebox.showinfo(
            "Selection saved",
            "Expense dates saved to:\n{}".format(saved_path.resolve()),
            parent=self.root,
        )

    def _match_receipts(self) -> None:
        """Save the current step-4 selection and run step 5."""
        try:
            if self.selected_dates:
                selection = create_selection(self.selected_dates)
                save_selection(selection, DEFAULT_SELECTION_PATH)
            result, output_path = run_matching_step(
                selection_path=DEFAULT_SELECTION_PATH,
            )
        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Could not match receipts", str(error), parent=self.root
            )
            return

        self.selected_dates = {
            selected_date
            for week in result.weeks
            for selected_date in week.selected_dates
        }
        self.week_receipt_status = {
            week.week_id: week.receipt_count > 0 for week in result.weeks
        }
        self._refresh_calendar_buttons()

        lines = [
            "Receipt matching complete. Green outlines indicate a receipt; "
            "orange outlines indicate none."
        ]
        lines.extend(
            "{}: {} receipt(s)".format(week.week_id, week.receipt_count)
            for week in result.weeks
        )
        if result.unmatched_receipts:
            lines.append(
                "Unmatched: {}".format(
                    ", ".join(
                        "{} ({})".format(receipt.receipt_id, receipt.reason)
                        for receipt in result.unmatched_receipts
                    )
                )
            )
        else:
            lines.append("Unmatched: none.")
        lines.append("Match result: {}".format(output_path.resolve()))
        self.match_status_var.set("\n".join(lines))
        self.match_status_label.pack(
            fill="x", pady=(8, 0), before=self.summary_label
        )


def main() -> None:
    """Launch the date-selection window."""
    root = tk.Tk()
    DateSelectionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
