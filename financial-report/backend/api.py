from .financial_engine import build_report

def generate_report(ticker,start_year=None,end_year=None,**options):
    return build_report(ticker,start_year,end_year,**options)
