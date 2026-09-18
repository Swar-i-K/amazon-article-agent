"""
scraper.py
----------
Fetches product data (title, price, rating, review count, image, feature
bullets) directly from an Amazon product page using a headless browser
(Playwright). No Amazon PA-API / no paid scraping service is used.

IMPORTANT / HONEST DISCLAIMER (read README.md too):
Amazon does not want to be scraped and actively fights it (bot-detection,
CAPTCHAs, layout changes, IP blocking). This scraper is built to be as
resilient as reasonably possible for a $0 budget, but it WILL occasionally
fail on some ASINs. main.py is written to skip a failed ASIN/job and move
on rather than crash the whole run, and to log clearly what failed so you
can retry manually later (or paste the data by hand into manual_data.csv,
see README).
"""

import re
import random
import time
import json
from dataclasses import dataclass, field
from typing import Optional, List

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

AMAZON_DOMAIN = "https://www.amazon.com"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
]


@dataclass
class Product:
    asin: str
    title: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[str] = None
    review_count: Optional[str] = None
    image_url: Optional[str] = None
    features: List[str] = field(default_factory=list)
    url: str = ""
    ok: bool = False
    error: Optional[str] = None


def _clean(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_captcha(html: str) -> bool:
    markers = [
        "Enter the characters you see below",
        "api-services-support@amazon.com",
        "Sorry, we just need to make sure you're not a robot",
    ]
    return any(m in html for m in markers)


def scrape_asin(asin: str, retries: int = 3, headless: bool = True) -> Product:
    """Scrape a single ASIN's product page. Retries with a fresh
    browser context / user-agent on failure or CAPTCHA."""
    url = f"{AMAZON_DOMAIN}/dp/{asin}"
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    locale="en-US",
                    viewport={"width": 1366, "height": 900},
                )
                page = context.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                # small human-like pause
                time.sleep(random.uniform(1.5, 3.0))
                try:
                    page.wait_for_selector("#productTitle", timeout=8000)
                except PWTimeout:
                    pass

                html = page.content()
                browser.close()

            if _looks_like_captcha(html):
                last_error = "captcha_or_block"
                time.sleep(random.uniform(3, 6))
                continue

            product = _parse_html(asin, url, html)
            if product.title:
                product.ok = True
                return product
            else:
                last_error = "title_not_found"
                time.sleep(random.uniform(2, 4))
                continue

        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            time.sleep(random.uniform(2, 4))
            continue

    return Product(asin=asin, url=url, ok=False, error=last_error)


def _parse_html(asin: str, url: str, html: str) -> Product:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("#productTitle")
    title = _clean(title_el.get_text()) if title_el else None

    # Price: try several common selectors, Amazon changes these often.
    price = None
    for sel in [
        "span.a-price span.a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#corePrice_feature_div span.a-offscreen",
    ]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            price = _clean(el.get_text())
            break

    # Rating e.g. "4.5 out of 5 stars"
    rating = None
    rating_el = soup.select_one("span.a-icon-alt")
    if rating_el:
        m = re.search(r"[\d.]+ out of 5", rating_el.get_text())
        if m:
            rating = m.group(0)

    # Review count
    review_count = None
    rc_el = soup.select_one("#acrCustomerReviewText")
    if rc_el:
        m = re.search(r"[\d,]+", rc_el.get_text())
        if m:
            review_count = m.group(0)

    # Main image
    image_url = None
    img_el = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
    if img_el:
        if img_el.get("data-old-hires"):
            image_url = img_el["data-old-hires"]
        elif img_el.get("data-a-dynamic-image"):
            try:
                dyn = json.loads(img_el["data-a-dynamic-image"])
                if dyn:
                    image_url = list(dyn.keys())[0]
            except Exception:  # noqa: BLE001
                pass
        elif img_el.get("src"):
            image_url = img_el["src"]

    # Feature bullets
    features = []
    for li in soup.select("#feature-bullets ul li span.a-list-item"):
        txt = _clean(li.get_text())
        if txt and "asin" not in txt.lower():
            features.append(txt)
    features = features[:8]

    return Product(
        asin=asin,
        url=url,
        title=title,
        price=price,
        rating=rating,
        review_count=review_count,
        image_url=image_url,
        features=features,
    )


def scrape_many(asins: List[str], delay_range=(4, 9)) -> List[Product]:
    """Scrape a list of ASINs one-by-one with a random delay between
    requests to look less bot-like and reduce block risk."""
    results = []
    for i, asin in enumerate(asins):
        results.append(scrape_asin(asin))
        if i < len(asins) - 1:
            time.sleep(random.uniform(*delay_range))
    return results


if __name__ == "__main__":
    import sys

    test_asin = sys.argv[1] if len(sys.argv) > 1 else "B0CHWRXH8B"
    p = scrape_asin(test_asin)
    print(json.dumps(p.__dict__, indent=2, ensure_ascii=False))
