"""Collect the latest headlines from free news RSS feeds and save them to data/news.json.

Run by the "Update news headlines" GitHub Actions workflow. No API key needed.
A feed that fails is skipped (and reported in the log); the run only fails if every feed fails.
"""
import email.utils
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

FEEDS = [
    ("NBC News", "https://feeds.nbcnews.com/nbcnews/public/news"),
    ("CBS News", "https://www.cbsnews.com/latest/rss/main"),
    ("ABC News", "https://abcnews.go.com/abcnews/topstories"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("Fox News", "https://moxie.foxnews.com/google-publisher/latest.xml"),
    ("ESPN", "https://www.espn.com/espn/rss/news"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
    ("New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("Wall Street Journal", "https://feeds.content.dowjones.io/public/rss/RSSWorldNews"),
]
PER_FEED = 8          # headlines kept from each source
SUMMARY_CHARS = 300   # summaries are trimmed to this length
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")
ATOM = "{http://www.w3.org/2005/Atom}"


def clean(text):
    """Strip HTML tags and entities and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def trim(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def parse_date(value):
    """Return an ISO-8601 UTC timestamp, or None if the date can't be read."""
    if not value:
        return None
    value = value.strip()
    try:
        dt = email.utils.parsedate_to_datetime(value)  # RSS style: "Wed, 25 Nov 2026 14:03:00 GMT"
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))  # Atom style
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; headline-collector/1.0)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
    })
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def parse_feed(source, xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.iter("item"):  # RSS 2.0
        items.append({
            "title": clean(item.findtext("title")),
            "url": (item.findtext("link") or "").strip(),
            "summary": clean(item.findtext("description")),
            "published": parse_date(item.findtext("pubDate")),
        })
    for entry in root.iter(ATOM + "entry"):  # Atom
        link = entry.find(ATOM + "link[@rel='alternate']")
        if link is None:
            link = entry.find(ATOM + "link")
        items.append({
            "title": clean(entry.findtext(ATOM + "title")),
            "url": (link.get("href") if link is not None else "").strip(),
            "summary": clean(entry.findtext(ATOM + "summary") or entry.findtext(ATOM + "content")),
            "published": parse_date(entry.findtext(ATOM + "updated") or entry.findtext(ATOM + "published")),
        })

    kept = []
    for it in items:
        if not it["title"] or not it["url"].startswith(("http://", "https://")):
            continue
        if it["summary"] == it["title"]:
            it["summary"] = ""
        it["summary"] = trim(it["summary"], SUMMARY_CHARS)
        it["source"] = source
        kept.append(it)
        if len(kept) == PER_FEED:
            break
    return kept


def main():
    headlines, sources, failed = [], [], []
    for source, url in FEEDS:
        try:
            items = parse_feed(source, fetch(url))
            if not items:
                raise ValueError("no headlines in feed")
            headlines.extend(items)
            sources.append(source)
            print(f"OK    {source}: {len(items)} headlines")
        except Exception as err:
            failed.append(source)
            print(f"SKIP  {source}: {err}")

    if not headlines:
        sys.exit("Every feed failed; keeping the previous data/news.json.")

    # Newest first; headlines without a date go last.
    headlines.sort(key=lambda h: h["published"] or "", reverse=True)

    # Skip writing if the headlines are unchanged, so the workflow doesn't make an empty commit.
    data = {"sources": sources, "headlines": headlines}
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            old = json.load(f)
        if {k: old.get(k) for k in data} == data:
            print("Headlines unchanged.")
            return
    except (OSError, ValueError):
        pass

    data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"Saved {len(headlines)} headlines from {len(sources)} sources"
          + (f"; skipped {', '.join(failed)}" if failed else ""))


if __name__ == "__main__":
    main()
