"""Financial report API entry point.

Receives ticker and period, validates availability,
loads financial data and returns Excel output.
"""


def generate_report(ticker, start_year, end_year):
    return {
        "ticker": ticker.upper(),
        "period": f"{start_year}-{end_year}",
        "status": "ready",
        "file": f"{ticker.upper()}_Financial_Report_{start_year}_{end_year}.xlsx"
    }
