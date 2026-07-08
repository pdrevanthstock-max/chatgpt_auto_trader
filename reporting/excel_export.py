"""
Excel Export
──────────────
§10: Automatic Excel export of completed trades and P&L statements.
     "Not yet built in either prior repo — no openpyxl/xlsxwriter/to_excel
      usage found anywhere in either codebase."

Now it exists.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Dict

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from loguru import logger

from config.settings import REPORTS_DIR
from backtest.results import BacktestResults


class ExcelExporter:
    """
    Exports trade data and P&L summaries to formatted Excel workbooks.
    """

    # Style constants
    HEADER_FONT = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
    HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    POSITIVE_FILL = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    NEGATIVE_FILL = PatternFill(start_color="FCE4EC", end_color="FCE4EC", fill_type="solid")
    BORDER = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    @classmethod
    def export_backtest(
        cls,
        results: BacktestResults,
        filename: str = None,
    ) -> Path:
        """
        Export backtest results to Excel.

        Creates 3 sheets:
          1. Trade Journal — every individual trade
          2. Daily P&L — summary per trading day
          3. Summary — overall statistics

        Returns the path to the generated file.
        """
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_report_{ts}.xlsx"

        filepath = REPORTS_DIR / filename

        wb = openpyxl.Workbook()

        # Sheet 1: Trade Journal
        cls._write_trade_journal(wb.active, results)

        # Sheet 2: Daily P&L
        ws_daily = wb.create_sheet("Daily P&L")
        cls._write_daily_pnl(ws_daily, results)

        # Sheet 3: Summary
        ws_summary = wb.create_sheet("Summary")
        cls._write_summary(ws_summary, results)

        wb.save(filepath)
        logger.info(f"Excel report saved: {filepath}")
        return filepath

    @classmethod
    def _write_trade_journal(cls, ws, results: BacktestResults) -> None:
        """Sheet 1: Individual trade records."""
        ws.title = "Trade Journal"

        headers = [
            "Trade ID", "Date", "Direction", "Strike",
            "Entry CE", "Entry PE", "Exit CE", "Exit PE",
            "Qty (lots)", "Lot Size",
            "Combined P&L (₹)", "Exit Reason",
            "Entry Time", "Exit Time",
            "Capital Allocated",
        ]

        # Write headers
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = cls.HEADER_FONT
            cell.fill = cls.HEADER_FILL
            cell.alignment = Alignment(horizontal="center")
            cell.border = cls.BORDER

        # Write trades
        for row_idx, trade in enumerate(results.closed_trades, 2):
            data = [
                trade.id,
                trade.entry_time.strftime("%Y-%m-%d") if trade.entry_time else "",
                trade.direction.value,
                trade.strike,
                trade.entry_ce_price,
                trade.entry_pe_price,
                trade.exit_ce_price,
                trade.exit_pe_price,
                trade.quantity,
                trade.lot_size,
                trade.combined_pnl,
                trade.exit_reason.value if trade.exit_reason else "",
                trade.entry_time.strftime("%H:%M:%S") if trade.entry_time else "",
                trade.exit_time.strftime("%H:%M:%S") if trade.exit_time else "",
                trade.capital_allocated,
            ]

            for col, value in enumerate(data, 1):
                cell = ws.cell(row=row_idx, column=col, value=value)
                cell.border = cls.BORDER

                # Color PnL column
                if col == 11:  # Combined P&L
                    if isinstance(value, (int, float)):
                        if value > 0:
                            cell.fill = cls.POSITIVE_FILL
                        elif value < 0:
                            cell.fill = cls.NEGATIVE_FILL
                    cell.number_format = "₹#,##0.00"

        # Auto-width columns
        cls._auto_width(ws)

    @classmethod
    def _write_daily_pnl(cls, ws, results: BacktestResults) -> None:
        """Sheet 2: Daily P&L summary."""
        headers = [
            "Date", "Trades", "P&L (₹)",
            "Cumulative P&L (₹)", "Circuit Breaker",
        ]

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = cls.HEADER_FONT
            cell.fill = cls.HEADER_FILL
            cell.alignment = Alignment(horizontal="center")
            cell.border = cls.BORDER

        cumulative = 0.0
        for row_idx, day in enumerate(results.daily_pnl, 2):
            cumulative += day["realized_pnl"]
            data = [
                day["date"].strftime("%Y-%m-%d") if day["date"] else "",
                day["trades"],
                day["realized_pnl"],
                round(cumulative, 2),
                "YES" if day["circuit_breaker"] else "",
            ]

            for col, value in enumerate(data, 1):
                cell = ws.cell(row=row_idx, column=col, value=value)
                cell.border = cls.BORDER

                if col in (3, 4) and isinstance(value, (int, float)):
                    cell.number_format = "₹#,##0.00"
                    if value > 0:
                        cell.fill = cls.POSITIVE_FILL
                    elif value < 0:
                        cell.fill = cls.NEGATIVE_FILL

        cls._auto_width(ws)

    @classmethod
    def _write_summary(cls, ws, results: BacktestResults) -> None:
        """Sheet 3: Overall statistics."""
        summary = results.summary()

        title_font = Font(name="Calibri", bold=True, size=14)
        label_font = Font(name="Calibri", bold=True, size=11)
        value_font = Font(name="Calibri", size=11)

        ws.cell(row=1, column=1, value="Backtest Summary").font = title_font
        ws.cell(row=2, column=1, value=f"Period: {results.start_date} to {results.end_date}")

        row = 4
        for key, value in summary.items():
            label = key.replace("_", " ").title()
            ws.cell(row=row, column=1, value=label).font = label_font
            ws.cell(row=row, column=2, value=str(value)).font = value_font
            ws.cell(row=row, column=1).border = cls.BORDER
            ws.cell(row=row, column=2).border = cls.BORDER
            row += 1

        # Config snapshot
        row += 2
        ws.cell(row=row, column=1, value="Configuration Used").font = title_font
        row += 1

        config = results.config_snapshot
        for key, value in config.items():
            ws.cell(row=row, column=1, value=key).font = label_font
            ws.cell(row=row, column=2, value=str(value)).font = value_font
            row += 1

        cls._auto_width(ws)

    @staticmethod
    def _auto_width(ws) -> None:
        """Auto-fit column widths to content."""
        for col in ws.columns:
            max_length = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except Exception:
                    pass
            ws.column_dimensions[col_letter].width = min(max_length + 3, 40)
