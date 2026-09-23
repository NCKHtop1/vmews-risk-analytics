"""Callable API, returning real XLSX bytes rather than a fictitious filename."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.financial_engine import build_report

def generate_report(ticker,start_year,end_year):
    return build_report(ticker,start_year,end_year)
