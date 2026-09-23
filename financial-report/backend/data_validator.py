"""Validate the actual periods of each report, including gaps and zero values."""
import math
import re

CORE = ('balance_sheet', 'income_statement', 'cash_flow')


def valid_ticker(value):
    value = str(value).strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9]{1,7}', value):
        raise ValueError('Mã chứng khoán không hợp lệ.')
    return value


def report_years(section):
    return sorted({int(y) for row in section.get('rows', []) for y, v in row.get('values', {}).items()
                   if re.fullmatch(r'20\d{2}|19\d{2}', str(y)) and isinstance(v, (int, float))
                   and not isinstance(v, bool) and math.isfinite(v)})


def available_years(data, report_ids=None):
    sections = {s['id']: s for s in data.get('sections', [])}
    requested = list(report_ids or CORE)
    sets = [set(report_years(sections.get(k, {}))) for k in requested]
    return sorted(set.intersection(*sets)) if sets else []


def validate_period(data, years, report_ids=None):
    if not isinstance(years, (list, tuple)) or not years:
        raise ValueError('Chọn ít nhất một năm.')
    if any(isinstance(y, bool) or not isinstance(y, int) for y in years):
        raise ValueError('Năm phải là số nguyên.')
    supported = available_years(data, report_ids)
    if any(y not in supported for y in years):
        period = ', '.join(map(str, supported)) or 'chưa có năm phù hợp'
        raise ValueError(f"{data.get('symbol', '')} chỉ có dữ liệu cho các năm: {period}.")
    return sorted(set(years))


def validate_dataset(data):
    valid_ticker(data['symbol'])
    if not data.get('sections'):
        raise ValueError('Chưa có dữ liệu báo cáo.')
    for section in data['sections']:
        seen = set()
        for row in section['rows']:
            if not row.get('label') or row['id'] in seen:
                raise ValueError('Chỉ tiêu trống hoặc trùng định danh.')
            seen.add(row['id'])
            for year, value in row['values'].items():
                if not re.fullmatch(r'(19|20)\d{2}', str(year)):
                    raise ValueError('Không trộn dữ liệu quý với dữ liệu năm.')
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value)):
                    raise ValueError('Số liệu không hợp lệ.')
        section['years'] = report_years(section)
    data['years'] = available_years(data)
    return data
