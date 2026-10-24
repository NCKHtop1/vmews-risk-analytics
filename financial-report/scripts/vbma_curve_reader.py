"""Parse VBMA's publicly served curve exports without guessing missing market values.

Supports CSV/TSV (including Vietnamese decimal marks) and XLSX responses with a
.csv URL. Date and tenor must both be present in the original source. Unlabeled
values are not presented as interest rates or swap points.
"""
from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
import zipfile
from datetime import date, datetime
from xml.etree import ElementTree as ET

VBMA_CURVES = {
    "swap": ("fx_swap_curve", "USD/VND FX Swap"),
    "fi_bond": ("fi_bond_yield_curve", "FI Bond & CD"),
    "gov_bond": ("government_bond_yield", "Government Bond Yield"),
    "short_benchmark": ("short_term_benchmark_rate", "Repo Short-term Benchmark"),
}
BASE_URL = "https://vbma.org.vn/csv/markets/charts/vi/"
VBMA_URLS = {key: BASE_URL + filename + ".csv" for key, (filename, _) in VBMA_CURVES.items()}
MAX_SOURCE_BYTES = 1_500_000
TENOR_RE = re.compile(r"^(?:ON|O/N|TN|T/N|SN|S/N|SPOT|[1-9]\d*(?:[.,]\d+)?\s*(?:D|W|M|Y|DAY|WEEK|MONTH|YEAR|NGAY|TUAN|THANG|NAM)S?)$", re.I)
DATE_RE = re.compile(r"(?:20\d\d[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d\d)")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def norm(value):
    value = unicodedata.normalize("NFD", str(value or "").strip().lower().replace("đ", "d"))
    return re.sub(r"\s+", " ", "".join(c for c in value if unicodedata.category(c) != "Mn"))


def tenor_label(value):
    s = re.sub(r"\s+", "", norm(value).upper())
    s = s.replace("NGAY", "D").replace("TUAN", "W").replace("THANG", "M").replace("NAM", "Y")
    s = s.replace("DAYS", "D").replace("DAY", "D").replace("WEEKS", "W").replace("WEEK", "W")
    s = s.replace("MONTHS", "M").replace("MONTH", "M").replace("YEARS", "Y").replace("YEAR", "Y")
    return s.replace(",", ".") if TENOR_RE.fullmatch(s) else None


def tenor_order(label):
    if label in ("SPOT",): return -1
    if label in ("ON", "O/N", "TN", "T/N", "SN", "S/N"): return 0
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([DWMY])", label)
    if not match: return 100000
    return float(match.group(1)) * {"D": 1, "W": 7, "M": 30, "Y": 365}[match.group(2)]


def parse_day(value):
    s = str(value or "").strip()
    match = DATE_RE.search(s)
    if not match: return None
    part = match.group()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try: return datetime.strptime(part, fmt).date()
        except ValueError: continue
    return None


def parse_number(value):
    if isinstance(value, (int, float)) and math.isfinite(value): return float(value)
    s = str(value or "").strip().replace("\u00a0", "").replace(" ", "").replace("%", "")
    if not s or s.lower() in ("nan", "na", "n/a", "null", "-", "—"): return None
    if not re.fullmatch(r"[+-]?[0-9][0-9.,]*", s): return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try: v = float(s)
    except ValueError: return None
    return v if math.isfinite(v) and abs(v) < 1_000_000 else None


def xlsx_grid(raw):
    """Read sheet-one XLSX cell strings and inline strings with Python stdlib."""
    if len(raw) > MAX_SOURCE_BYTES: raise ValueError("VBMA source too large")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.namelist()) > 200 or sum(e.file_size for e in z.infolist()) > 8_000_000:
            raise ValueError("Unsafe or oversized XLSX source")
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in tree.findall("m:si", NS)]
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not sheets: raise ValueError("XLSX has no data sheet")
        root = ET.fromstring(z.read(sheets[0]))
        result = []
        for row in root.findall(".//m:sheetData/m:row", NS)[:600]:
            cells = {}
            for cell in row.findall("m:c", NS):
                ref = cell.get("r", "")
                letters = re.match(r"[A-Z]+", ref)
                if not letters: continue
                column = 0
                for char in letters.group(): column = column * 26 + ord(char) - 64
                if column > 150: continue
                v = cell.find("m:v", NS)
                inline = cell.find("m:is", NS)
                value = v.text if v is not None else ""
                if cell.get("t") == "s" and value and value.isdigit():
                    i = int(value)
                    value = shared[i] if i < len(shared) else ""
                elif inline is not None:
                    value = "".join(x.text or "" for x in inline.findall(".//m:t", NS))
                cells[column - 1] = value or ""
            if cells: result.append([cells.get(i, "") for i in range(max(cells) + 1)])
        return result


def csv_grid(raw):
    if len(raw) > MAX_SOURCE_BYTES or len(raw) < 5: raise ValueError("Invalid source length")
    if raw[:2] == b"PK": return xlsx_grid(raw)
    if raw.startswith(b"\xd0\xcf\x11\xe0"): raise ValueError("Legacy XLS binary is not an accepted CSV export")
    if b"<html" in raw[:300].lower() or b"<!doctype" in raw[:300].lower():
        raise ValueError("VBMA returned HTML instead of curve data")
    chosen = None
    for encoding in ("utf-8-sig", "utf-16", "cp1258", "latin1"):
        try: s = raw.decode(encoding)
        except UnicodeError: continue
        if "\x00" in s[:1000] or s.lstrip().startswith(("<", "{", "[")): continue
        if s.lower().startswith("sep="): s = "\n".join(s.splitlines()[1:])
        for delimiter in (",", ";", "\t", "|"):
            try: rows = list(csv.reader(io.StringIO(s), delimiter=delimiter))
            except csv.Error: continue
            rows = [[v.strip() for v in row] for row in rows if any(v.strip() for v in row)]
            if len(rows) < 2: continue
            score = sum(1 for row in rows[:40] if len(row) >= 3) * 3 + sum(tenor_label(v) is not None for row in rows[:5] for v in row) * 6
            score += sum(parse_day(v) is not None for row in rows[:12] for v in row) * 4
            if max(map(len, rows)) < 3 or max(map(len, rows)) > 150: continue
            if chosen is None or score > chosen[0]: chosen = (score, rows)
    if chosen is None: raise ValueError("CSV delimiters or columns not recognized")
    return chosen[1]


def source_unit(raw, grid, kind):
    """Units are certified only by visible source labels, never by value magnitude."""
    headers = " ".join(str(v) for row in grid[:7] for v in row)
    labels = norm(headers)
    if re.search(r"(swap points?|forward points?|diem swap|pips?)", labels):
        return "swap points"
    if "%" in headers or re.search(r"(?:lai suat|yield|interest rate|%/year|%/annum)\s*\(?%?\)?", labels):
        return "%/năm"
    return None


def parse_vbma_curve(raw, kind, reference=None):
    if kind not in VBMA_CURVES: raise ValueError("Unknown VBMA curve")
    today = reference or date.today()
    grid = csv_grid(raw)
    unit = source_unit(raw, grid, kind)
    # Prefer dated observation rows with tenor columns, as in the original user's
    # DataFrame importer (whose first column is often named "Unnamed: 0").
    candidates = []
    for header_at, head in enumerate(grid[:12]):
        tenor_columns = [(i, tenor_label(h)) for i, h in enumerate(head) if tenor_label(h)]
        if len(tenor_columns) >= 2:
            for row in grid[header_at + 1:]:
                dates = [(i, parse_day(v)) for i, v in enumerate(row[:5]) if parse_day(v)]
                if not dates: continue
                obs = dates[0][1]
                pts = [{"tenor": tenor, "value": n} for col, tenor in tenor_columns
                       if col < len(row) and (n := parse_number(row[col])) is not None]
                if len(pts) >= 2: candidates.append((obs, pts))
        # Pivoted layout: tenors as rows; each dated column contains a curve.
        dated_columns = [(i, parse_day(h)) for i, h in enumerate(head) if parse_day(h)]
        if dated_columns:
            for col, obs in dated_columns:
                pts = []
                for row in grid[header_at + 1:]:
                    label = tenor_label(row[0]) if row else None
                    if label and len(row) > col:
                        n = parse_number(row[col])
                        if n is not None: pts.append({"tenor": label, "value": n})
                if len(pts) >= 2: candidates.append((obs, pts))
        # Long-form layout with explicit tenor and MID/yield columns.
        fields = [norm(h) for h in head]
        tenor_cols = [i for i, h in enumerate(fields) if h in ("tenor", "term", "maturity", "ky han")]
        date_cols = [i for i, h in enumerate(fields) if h in ("date", "ngay", "ngay giao dich", "trading date", "as of")]
        val_cols = [i for i, h in enumerate(fields) if any(key in h for key in ("mid", "yield", "rate", "gia tri", "value", "fixing"))]
        if tenor_cols and date_cols and val_cols:
            bucket = {}
            for row in grid[header_at + 1:]:
                if max(tenor_cols[0], date_cols[0], val_cols[0]) >= len(row): continue
                obs = parse_day(row[date_cols[0]])
                label = tenor_label(row[tenor_cols[0]])
                value = parse_number(row[val_cols[0]])
                if obs and label and value is not None:
                    bucket.setdefault(obs, []).append({"tenor": label, "value": value})
            candidates.extend((d, pts) for d, pts in bucket.items() if len(pts) >= 2)
    candidates = [(dt, pts) for dt, pts in candidates if dt and date(2012, 1, 1) <= dt <= today and (today - dt).days <= 14]
    if not candidates: raise ValueError("No recent dated VBMA tenor curve found")
    observed, points = max(candidates, key=lambda item: (item[0], len(item[1])))
    unique = {}
    for pt in points:
        if pt["tenor"] not in unique: unique[pt["tenor"]] = pt
    points = sorted(unique.values(), key=lambda p: (tenor_order(p["tenor"]), p["tenor"]))
    if len(points) < 2: raise ValueError("VBMA observation has fewer than two tenors")
    # Yield percentages must be plausible and cannot be mixed with FX swap
    # forward points. If source unit is missing, do not invent it.
    if unit == "%/năm" and any(abs(p["value"]) > 50 for p in points):
        raise ValueError("Yield percent outside plausible bound")
    if kind == "swap" and unit == "%/năm":
        # VBMA sometimes represents the FX swap curve as implied rates.
        measurement = "FX Swap implied yield curve"
    else:
        measurement = VBMA_CURVES[kind][1]
    return {
        "status": "verified" if unit else "unit_unverified",
        "asOf": observed.isoformat(), "unit": unit, "measurement": measurement,
        "points": points, "source": VBMA_URLS[kind],
        "lastObservationCount": len(points),
    }
