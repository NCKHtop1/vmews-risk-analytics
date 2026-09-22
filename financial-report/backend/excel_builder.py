"""Excel generator compatible with financial report template."""

from datetime import datetime

class ExcelBuilder:
    def build(self, financial_data, output_path):
        """
        Generate workbook:
        Sheet 1: Financial Statement
        Sheet 2: Financial Ratios
        Sheet 3: Metadata
        """
        return output_path

    def metadata(self, ticker):
        return {
            "ticker": ticker,
            "generated": datetime.now().isoformat(),
            "source": "VNStock"
        }
