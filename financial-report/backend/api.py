"""Financial Report API entry point."""

from datetime import datetime


def generate_report(ticker: str, start_year: int, end_year: int):
    return {
        "ticker": ticker.upper(),
        "period": f"{start_year}-{end_year}",
        "status": "ready",
        "generated_at": datetime.now().isoformat(),
        "file": f"{ticker.upper()}_Financial_Report_{start_year}_{end_year}.xlsx"
    }
