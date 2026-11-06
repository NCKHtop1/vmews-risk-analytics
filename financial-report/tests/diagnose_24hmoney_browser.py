"""Compare raw Live SSR feed vs one public browser-rendered DOM. No article text logged."""
import collections
import html
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

sys.path.insert(0, "financial-report/scripts")
import news_intelligence as ni

opts = Options()
opts.page_load_strategy = "eager"
for flag in [
    "--headless=new",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--window-size=1280,900",
]:
    opts.add_argument(flag)
path = shutil.which("chromedriver")
driver = webdriver.Chrome(service=Service(path) if path else Service(), options=opts)
driver.set_page_load_timeout(30)
url = "https://24hmoney.vn/news/live"
try:
    driver.get(url)
    for pause in [3, 7]:
        time.sleep(pause)
        raw = driver.page_source
        now = datetime.now(timezone.utc)
        txt = raw.decode("utf-8-sig", errors="ignore") if isinstance(raw, bytes) else raw
        anchor_re = re.compile(
            r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S
        )
        counts = collections.Counter()
        dates = collections.Counter()
        distinct_urls = set()
        eligible_urls = set()
        parse_reasons = collections.Counter()
        for match in anchor_re.finditer(txt):
            href = match.group(1)
            if "/news/" not in href.lower() or len(ni.compact(match.group(2))) < 24:
                continue
            counts["anchors"] += 1
            href = html.unescape(match.group(1)).strip()
            u = urlsplit(urljoin(url, href))
            clean_url = urlunsplit((u.scheme, u.netloc, u.path, "", ""))
            if clean_url in distinct_urls:
                counts["duplicate_urls"] += 1
            distinct_urls.add(clean_url)
            context, pos, _ = ni._24hmoney_plain_context(
                txt, match.start(), match.end()
            )
            stamp, precision, _ = ni._24hmoney_timestamp(context, now, pos)
            if stamp:
                dates[stamp.astimezone(ni.VIETNAM_TZ).date().isoformat()] += 1
            if stamp is None:
                counts["missing_time"] += 1
            elif stamp < now - timedelta(days=7):
                counts["older_than_7d"] += 1
            elif stamp > now + timedelta(minutes=10):
                counts["future"] += 1
            else:
                counts["recent"] += 1
                eligible_urls.add(clean_url)
                parse_reasons[str(precision)] += 1
        dom = driver.execute_script("""
            return {
              url:location.href,
              title:document.title,
              links:[...document.querySelectorAll('a[href*="/news/"]')]
                .filter(a=>a.innerText.trim().length>=24).length,
              textLength:document.body?.innerText?.length||0,
              categoryButtons:[...document.querySelectorAll('button')].length,
              ages:[...document.querySelectorAll('body *')]
                .filter(e=>e.children.length===0 && /^\d+\s*(phút|giờ|ngày)(\s+trước)?$/.test((e.innerText||'').trim()))
                .length
            };
        """)
        print("BROWSER_DOM", {
            "elapsedSeconds": pause,
            "dom": dom,
            "markupCounts": dict(counts),
            "uniqueUrls": len(distinct_urls),
            "recentUniqueUrls": len(eligible_urls),
            "validTimePrecision": dict(parse_reasons),
            "markupDates": dict(dates),
            "parseWithoutFinanceFilter": len(
                ni.parse_24hmoney_live(raw, now, [], {}, financial_only=False)
            ),
            "parseFinanceOnly": len(
                ni.parse_24hmoney_live(raw, now, [], {}, financial_only=True)
            ),
        }, flush=True)
except Exception as exc:
    print("BROWSER_ERROR", type(exc).__name__, str(exc)[:220], flush=True)
finally:
    driver.quit()
