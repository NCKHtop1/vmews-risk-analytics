"""Validate the actual periods of each report, including gaps and zero values."""
import math
import re

CORE = ('balance_sheet', 'income_statement', 'cash_flow')


def valid_ticker(value):
    value = str(value).strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9]{1,7}', value):
        raise ValueError('Mã chứng khoán không hợp lệ.')
    return value


def report_periods(section, period_type='year'):
    pattern = r'(19|20)\d{2}-Q[1-4]' if period_type == 'quarter' else r'(19|20)\d{2}'
    return sorted({str(y) if period_type == 'quarter' else int(y)
                   for row in section.get('rows', []) for y, v in row.get('values', {}).items()
                   if re.fullmatch(pattern, str(y)) and isinstance(v, (int, float))
                   and not isinstance(v, bool) and math.isfinite(v)})


def report_years(section):
    return report_periods(section)


def available_years(data, report_ids=None):
    sections = {s['id']: s for s in data.get('sections', [])}
    requested = list(report_ids or CORE)
    sets = [set(report_periods(sections.get(k, {}), data.get('periodType', 'year'))) for k in requested]
    return sorted(set.intersection(*sets)) if sets else []


def validate_period(data, years, report_ids=None):
    if not isinstance(years, (list, tuple)) or not years:
        raise ValueError('Chọn ít nhất một kỳ báo cáo.')
    quarter = data.get('periodType') == 'quarter'
    invalid = any(not isinstance(y,str) or not re.fullmatch(r'(19|20)\d{2}-Q[1-4]',y) for y in years) if quarter else any(isinstance(y,bool) or not isinstance(y,int) for y in years)
    if invalid:
        raise ValueError('Kỳ báo cáo không hợp lệ.')
    supported = available_years(data, report_ids)
    if any(y not in supported for y in years):
        period = ', '.join(map(str, supported)) or 'chưa có năm phù hợp'
        raise ValueError(f"{data.get('symbol', '')} chỉ có dữ liệu cho các kỳ: {period}.")
    return sorted(set(years))


def validate_dataset(data):
    valid_ticker(data['symbol'])
    if not data.get('sections'):
        raise ValueError('Chưa có dữ liệu báo cáo.')
    quarter = data.get('periodType') == 'quarter'
    pattern = r'(19|20)\d{2}-Q[1-4]' if quarter else r'(19|20)\d{2}'
    section_ids = set()
    for section in data['sections']:
        if section['id'] in section_ids:
            raise ValueError('Báo cáo trùng định danh.')
        section_ids.add(section['id'])
        seen = set()
        for row in section['rows']:
            if not row.get('label') or row['id'] in seen:
                raise ValueError('Chỉ tiêu trống hoặc trùng định danh.')
            seen.add(row['id'])
            for year, value in row['values'].items():
                if not re.fullmatch(pattern, str(year)):
                    raise ValueError('Không trộn dữ liệu quý với dữ liệu năm.')
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value)):
                    raise ValueError('Số liệu không hợp lệ.')
        section['periods'] = report_periods(section, data.get('periodType','year'))
        section['years'] = section['periods']
    data['periods'] = available_years(data)
    data['years'] = data['periods']
    if data.get('quarterly'):
        validate_dataset(data['quarterly'])
    return data
