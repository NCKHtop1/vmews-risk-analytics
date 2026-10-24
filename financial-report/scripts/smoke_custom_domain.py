#!/usr/bin/env python3
"""FinQuery auth-aware production smoke: HTTPS, private dashboard, Pages data.

The Vercel custom domain REQUIRES login. Anonymous stock quote access returning
401 is a security success, not a publication failure. The public Pages mirror
is the validated read-only source used to check upstream snapshot freshness.
"""
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from finquery_ops_health import probe_production
from guard_public_quotes import (
    SOURCE as PRICE_SOURCE, PAGES as PAGE_PRICES, read as read_prices,
    compare as compare_prices, probe_domain_anonymous
)

DOMAIN = "https://finquery.info.vn"
PAGES = "https://nckhtop1.github.io/vmews-risk-analytics"
HUB_PATH = "/financial-report/data-hub.html"
USER_AGENT = "FinQuery-AuthAware-LiveSmoke/2.0"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_no_redirect(url, opener=None):
    client = opener or build_opener(NoRedirect)
    request = Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,application/json",
        "Cache-Control": "no-cache",
    })
    try:
        response = client.open(request, timeout=16)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers.get("Location") or "", response.read(300_000)


def protected_page(status, location, intended_path):
    if status not in (302, 303, 307, 308):
        return False
    destination = unquote(str(location or ""))
    parts = urlsplit(destination)
    if parts.scheme and parts.hostname not in ("finquery.info.vn", "www.finquery.info.vn"):
        return False
    return parts.path.startswith("/login") and intended_path in destination


def verify_hub_page(content):
    text = content.decode("utf-8", "replace")
    required = [
        "FinQuery", "Kho dữ liệu", "Hợp đồng tương lai VN30",
        "Hợp đồng tương lai VN100", "39.543", "203 hợp đồng",
        "không bổ sung cổ phiếu niêm yết HNX",
        "HNX chỉ là nguồn công bố chính thức của dữ liệu phái sinh",
    ]
    # Real text has HTML nodes separating words: use a semantic rather than
    # an exact adjacent phrase match on company names and displayed numbers.
    for literal in required:
        if literal not in text:
            raise AssertionError("Deployed Data Hub lacks " + literal)
    return len(content)


def main():
    try:
        production = probe_production(DOMAIN)
        required_flags = ("ok", "sessionAnonymous", "adminProtected", "dashboardProtected")
        missing = [key for key in required_flags if production.get(key) is not True]
        if missing:
            raise AssertionError("FinQuery health or authentication regression: " + str(missing))
        print("AUTH_PRODUCTION_PASS", json.dumps(production, ensure_ascii=False))

        src = read_prices(PRICE_SOURCE)
        pages = read_prices(PAGE_PRICES)
        print("PAGES_PRICE_PASS", json.dumps(compare_prices(src, pages, "pages")))
        print("DOMAIN_PRICE_AUTH_PASS", json.dumps(probe_domain_anonymous()))

        status, location, _ = request_no_redirect(DOMAIN + HUB_PATH)
        if not protected_page(status, location, HUB_PATH):
            raise AssertionError("Data Hub route must require login; status=" + str(status) + " target=" + location[:160])
        print("HUB_AUTH_GUARD_PASS", status, location[:160])

        hub = Request(PAGES + HUB_PATH + "?smoke=" + str(int(time.time())), headers={"User-Agent": USER_AGENT})
        with urlopen(hub, timeout=20) as response:
            if response.status != 200:
                raise AssertionError("Pages Data Hub unavailable HTTP " + str(response.status))
            content = response.read(800_000)
        print("HUB_PAGES_PASS", verify_hub_page(content), PAGES + HUB_PATH)

        login_status, _, login_bytes = request_no_redirect(DOMAIN + "/login.html")
        if login_status != 200 or b"FinQuery" not in login_bytes:
            raise AssertionError("Login page unavailable via custom domain")
        print("LOGIN_PAGE_PASS", login_status)

        print("FINQUERY_AUTH_AWARE_PRODUCTION_SMOKE_PASS")
        return 0
    except Exception as exc:
        print("::error::FINQUERY_AUTH_AWARE_PRODUCTION_SMOKE_FAIL", type(exc).__name__, str(exc)[:400])
        return 1


if __name__ == "__main__":
    sys.exit(main())
