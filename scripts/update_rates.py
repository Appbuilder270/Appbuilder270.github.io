"""Fetch Treasury yields and the fed funds rate from FRED and save them to data/rates.json.

Run by the "Update rates data" GitHub Actions workflow. Needs the FRED API key in the
FRED_API_KEY environment variable (stored as a repository secret, never in the page).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

SERIES = ["DGS10", "DGS2", "DGS30", "DFF"]
LIMIT = 520  # about two years of daily observations
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rates.json")
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_series(series_id, api_key):
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": LIMIT,
    })
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{FRED_URL}?{params}", timeout=30) as res:
                payload = json.load(res)
            break
        except Exception as err:  # network hiccup or FRED error: retry a couple of times
            last_error = err
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"Could not fetch {series_id}: {last_error}")

    points = [
        [obs["date"], float(obs["value"])]
        for obs in payload.get("observations", [])
        if obs.get("value") not in (None, "", ".")  # "." marks a day with no data
    ]
    points.sort(key=lambda p: p[0])
    if not points:
        raise RuntimeError(f"FRED returned no observations for {series_id}")
    return points


def main():
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        sys.exit("FRED_API_KEY is not set. Add it as a repository secret.")

    data = {"source": "FRED, Federal Reserve Bank of St. Louis", "series": {}}
    for series_id in SERIES:
        data["series"][series_id] = fetch_series(series_id, api_key)
        print(f"{series_id}: {len(data['series'][series_id])} points, "
              f"latest {data['series'][series_id][-1]}")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
        f.write("\n")


if __name__ == "__main__":
    main()
