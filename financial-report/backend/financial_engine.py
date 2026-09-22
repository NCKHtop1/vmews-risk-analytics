"""Financial report engine.

Pipeline:
Ticker -> VNStock connector -> validation -> Excel builder
"""


def validate_period(available_start, available_end, request_start, request_end):
    if request_start < available_start or request_end > available_end:
        return False
    return True


def build_report(ticker, start_year, end_year):
    return {
        'ticker': ticker,
        'period': f'{start_year}-{end_year}',
        'status': 'ready'
    }
