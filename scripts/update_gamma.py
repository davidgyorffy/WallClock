from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

URLS = [
    "https://www.katasztrofavedelem.hu/modules/hattersugarzas/aktualis_adatsor",
    "https://www.katasztrofavedelem.hu/modules/hattersugarzas/terkep",
]

STATION = "Budapest II. ker. THHE"
STATION_CODE = "HU0350"
OUT = Path("gamma.json")


def plausible(value: float) -> bool:
    return math.isfinite(value) and 20 <= value < 2000


def extract_from_row_text(text: str) -> float | None:
    normalized = re.sub(r"\s+", " ", text).strip()
    if STATION not in normalized and STATION_CODE not in normalized:
        return None

    # Prefer explicit nSv/h value.
    m = re.search(r"(\d{2,4}(?:[.,]\d+)?)\s*nSv\s*/?\s*h", normalized, re.I)
    if m:
        value = float(m.group(1).replace(",", "."))
        if plausible(value):
            return value

    # Split after the station name/code and inspect likely numeric fields.
    marker_pos = normalized.find(STATION)
    marker_len = len(STATION)
    if marker_pos < 0:
        marker_pos = normalized.find(STATION_CODE)
        marker_len = len(STATION_CODE)

    tail = normalized[marker_pos + marker_len :]
    nums = re.findall(r"\b\d{2,4}(?:[.,]\d+)?\b", tail)

    for raw in nums:
        value = float(raw.replace(",", "."))
        # Avoid known threshold values and dates.
        if value in (250, 500):
            continue
        if plausible(value) and value <= 700:
            return value

    return None


def extract_from_page(page) -> float | None:
    # First try actual table rows.
    rows = page.locator("tr")
    for i in range(rows.count()):
        try:
            text = rows.nth(i).inner_text(timeout=1000)
        except Exception:
            continue
        value = extract_from_row_text(text)
        if value is not None:
            return value

    # Then try any element containing station text.
    for needle in (STATION, STATION_CODE):
        loc = page.get_by_text(needle, exact=False)
        count = min(loc.count(), 10)
        for i in range(count):
            try:
                el = loc.nth(i)
                text = el.inner_text(timeout=1000)
                parent_text = el.locator("xpath=..").inner_text(timeout=1000)
            except Exception:
                continue

            value = extract_from_row_text(parent_text)
            if value is not None:
                return value
            value = extract_from_row_text(text)
            if value is not None:
                return value

    # Last fallback: inspect rendered body text around the station.
    try:
        body = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return None

    for needle in (STATION, STATION_CODE):
        pos = body.find(needle)
        if pos >= 0:
            chunk = body[max(0, pos - 200) : pos + 1200]
            value = extract_from_row_text(chunk)
            if value is not None:
                return value

    return None


def main() -> None:
    errors: list[str] = []
    value: float | None = None
    used_url: str | None = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1200},
            locale="hu-HU",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 Chrome/131 Safari/537.36"
            ),
        )

        for url in URLS:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                # Give the site's JavaScript time to populate radiation data.
                page.wait_for_timeout(6000)

                # A second wait often catches late XHR rendering.
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                value = extract_from_page(page)
                if value is not None:
                    used_url = url
                    break
                errors.append(f"No {STATION} value found on {url}")
            except Exception as exc:
                errors.append(f"{url}: {exc}")

        browser.close()

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if value is None:
        # Preserve last good reading if available, but mark it stale.
        if OUT.exists():
            try:
                previous = json.loads(OUT.read_text(encoding="utf-8"))
                if isinstance(previous.get("value"), (int, float)):
                    previous["last_attempt_utc"] = now
                    previous["stale"] = True
                    previous["error"] = " | ".join(errors)[-1500:]
                    OUT.write_text(
                        json.dumps(previous, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    print("No new reading; preserved previous gamma.json")
                    return
            except Exception:
                pass
        raise RuntimeError("Could not obtain gamma value: " + " | ".join(errors))

    payload = {
        "station": STATION,
        "station_code": STATION_CODE,
        "value": round(value, 1),
        "unit": "nSv/h",
        "updated_utc": now,
        "source": used_url,
        "stale": False,
    }

    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
