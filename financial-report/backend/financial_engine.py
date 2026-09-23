from .vnstock_connector import VNStockConnector
from .excel_builder import ExcelBuilder

def build_report(ticker,start_year=None,end_year=None,years=None,report_ids=None,period_type="year",periods=None):
    data=VNStockConnector().fetch(ticker)
    if period_type not in ('year','quarter'):raise ValueError('Kỳ báo cáo không hợp lệ.')
    if period_type=='quarter':
        data=data.get('quarterly')
        if not data:raise ValueError('Chưa có dữ liệu quý.')
    selected=periods if periods is not None else years if years is not None else list(range(int(start_year),int(end_year)+1)) if start_year is not None and end_year is not None else data.get('periods',data['years'])
    return ExcelBuilder().build_bytes(data,selected,report_ids)
