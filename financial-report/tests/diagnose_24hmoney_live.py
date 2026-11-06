"""One-shot read-only source rejection counters. No markup is emitted to logs."""
import collections
import html
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

sys.path.insert(0, "financial-report/scripts")
import news_intelligence as ni

url = "https://24hmoney.vn/news/live"
now = datetime.now(timezone.utc)
agents = {
    "collector": "FinQuery/1.0 public financial dashboard",
    "browser": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
}
for agent_name, user_agent in agents.items():
    try:
        request = Request(url, headers={
            "User-Agent": user_agent,
            "Accept": "application/json, application/xml, text/xml, */*"
        })
        with urlopen(request, timeout=18) as response:
            raw = response.read()
            print("FETCH", agent_name, response.status, len(raw),
                  response.headers.get("Content-Type"), response.url, flush=True)
        text = raw.decode("utf-8-sig", errors="ignore")
        matches = list(re.finditer(
            r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, re.I | re.S
        ))
        counts = collections.Counter()
        distances = []
        sample_kinds = []
        for match in matches:
            href = html.unescape(match.group(1)).strip()
            title = ni.compact(match.group(2))
            if "/news/" not in href.lower():
                continue
            counts["news_href"] += 1
            if len(title) < 24:
                counts["short_anchor"] += 1
                continue
            counts["eligible_anchor"] += 1
            host = urlsplit(urljoin(url, href)).hostname or ""
            if not host.endswith("24hmoney.vn"):
                counts["wrong_host"] += 1
                continue
            context, anchor, _ = ni._24hmoney_plain_context(
                text, match.start(), match.end()
            )
            stamp, precision, verified = ni._24hmoney_timestamp(context, now, anchor)
            category, topics = ni._24hmoney_context_category(context, anchor)
            time_marks = list(re.finditer(
                r"(?<!\d)(\d{1,3})\s*(phút|giờ|ngày)(?:\s+trước)?(?!\w)",
                context, re.I,
            ))
            nearest = min(
                [ni._marker_distance(m, anchor) for m in time_marks],
                default=-1,
            )
            distances.append(nearest)
            sample_kinds.append(category)
            if nearest >= 0:
                counts["time_marker_somewhere"] += 1
            if nearest > 180:
                counts["time_marker_outside_180"] += 1
            if stamp is None:
                counts["timestamp_missing"] += 1
                continue
            if stamp < now - timedelta(days=7):
                counts["stale_over_7days"] += 1
                continue
            if stamp > now + timedelta(minutes=10):
                counts["future"] += 1
                continue
            counts["timestamp_ok"] += 1
            semantic, evidence = ni.classify_semantics(
                title, "", {"vietnam", "market"} | topics
            )
            relevant, reason = ni._24hmoney_financial_relevance(
                title, [], semantic, evidence, category
            )
            counts["finance_ok" if relevant else "finance_filtered"] += 1
        all_rows = ni.parse_24hmoney_live(
            raw, now, [], {}, financial_only=False
        )
        fin_rows = ni.parse_24hmoney_live(
            raw, now, [], {}, financial_only=True
        )
        print("COUNTS", agent_name, dict(counts), flush=True)
        print("NEAREST_DISTANCE", agent_name, distances[:20], flush=True)
        print("CATEGORIES", agent_name, sample_kinds[:20], flush=True)
        print("FINAL", agent_name, {
            "raw_rows": len(all_rows),
            "financial_rows": len(fin_rows),
            "anchors": ni.count_24hmoney_article_anchors(raw),
            "relative_markers": len(re.findall(
                r"\b(?:phút|giờ|ngày)\b", ni.compact(text), re.I
            )),
        }, flush=True)
    except Exception as exc:
        print("FETCH_ERROR", agent_name, type(exc).__name__,
              str(exc)[:180], flush=True)
