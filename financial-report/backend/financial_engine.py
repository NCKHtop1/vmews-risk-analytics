from .vnstock_connector import VNStockConnector
from .excel_builder import ExcelBuilder

def build_report(ticker,start_year=None,end_year=None,years=None,report_ids=None):
    data=VNStockConnector().fetch(ticker)
    selected=years if years is not None else list(range(int(start_year),int(end_year)+1))
    return ExcelBuilder().build_bytes(data,selected,report_ids)
