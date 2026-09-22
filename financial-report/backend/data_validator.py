"""Validate available financial periods."""

DEFAULT_LIMITS = {
    "MBB": (2010, 2025),
    "VCB": (2008, 2025),
    "VIC": (2007, 2025)
}


def validate_period(ticker, start_year, end_year):
    if ticker in DEFAULT_LIMITS:
        low, high = DEFAULT_LIMITS[ticker]
        if start_year < low or end_year > high:
            return {
                "valid": False,
                "message": f"{ticker} only supports data from {low} to {high}"
            }
    return {"valid": True}
