"""VNStock connector layer for financial reports."""

class VNStockConnector:
    def __init__(self):
        self.source = "vnstock"

    def get_financial_data(self, ticker, start_year, end_year):
        # Production hook for vnstock financial APIs
        # Returns normalized structure for Excel builder
        return {
            "ticker": ticker,
            "period": list(range(start_year, end_year + 1)),
            "balance_sheet": {},
            "income_statement": {},
            "cash_flow": {},
            "ratios": {}
        }

    def available_period(self, ticker):
        # Replace with database/cache lookup
        return {
            "start": 2007,
            "end": 2025
        }
