"""
main.py
-------
Reads jobs.csv, retrieves product facts (manual_data.csv first, Amazon scraper
second), generates articles with Groq, and saves editable Word documents.
"""

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from scraper import Product, scrape_asin
from llm_generator import generate_list_article, generate_single_article, generate_vs_article
from doc_writer import html_to_docx, safe_filename

JOBS_FILE = "jobs.csv"
MANUAL_DATA_FILE = "manual_data.csv"
OUTPUT_DIR = "output"
MAX_JOBS_PER_RUN = 10


def load_jobs(path=JOBS_FILE):
    jobs = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"type", "focus_keyword", "asins"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"{path} must have columns: type,focus_keyword,asins")
        for row in reader:
            row["asins"] = [a.strip().upper() for a in (row.get("asins") or "").split(";") if a.strip()]
            jobs.append(row)
    return jobs


def load_manual_products(path=MANUAL_DATA_FILE):
    """Load verified product facts keyed by ASIN. A title is required."""
    products = {}
    if not os.path.exists(path):
        return products

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"asin", "title"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"{path} must include at least these columns: asin,title")

        for row in reader:
            asin = (row.get("asin") or "").strip().upper()
            title = (row.get("title") or "").strip()
            if not asin:
                continue
            if not re.fullmatch(r"B0[A-Z0-9]{8}", asin):
                print(f"  MANUAL DATA WARNING: invalid ASIN format '{asin}', ignoring row.")
                continue
            if not title:
                print(f"  MANUAL DATA WARNING: {asin} has no title, ignoring row.")
                continue

            raw_features = (row.get("features") or "").strip()
            features = [x.strip() for x in raw_features.split("|") if x.strip()]
            url = (row.get("url") or "").strip() or f"https://www.amazon.com/dp/{asin}"
            if not url.startswith("https://www.amazon.com/"):
                print(f"  MANUAL DATA WARNING: {asin} URL must be an Amazon.com URL; using its ASIN URL.")
                url = f"https://www.amazon.com/dp/{asin}"

            products[asin] = Product(
                asin=asin,
                title=title,
                price=(row.get("price") or "").strip() or None,
                rating=(row.get("rating") or "").strip() or None,
                review_count=(row.get("review_count") or "").strip() or None,
                image_url=(row.get("image_url") or "").strip() or None,
                features=features,
                url=url,
                ok=True,
                error=None,
            )
    return products


def get_product(asin, manual_products):
    """Prefer user-supplied verified facts; otherwise try Amazon scraping."""
    if asin in manual_products:
        print(f"    USING MANUAL DATA: {manual_products[asin].title[:60]}...")
        return manual_products[asin], "manual"

    product = scrape_asin(asin)
    if product.ok:
        print(f"    SCRAPED: {product.title[:60]}...")
        return product, "scraped"

    print(f"    SCRAPE FAILED ({product.error}); no manual facts found for {asin}.")
    return product, "failed"


def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    jobs = load_jobs()
    if not jobs:
        print("jobs.csv is empty. Nothing to do.")
        with open("run_summary.json", "w", encoding="utf-8") as f:
            json.dump({"run_at": datetime.now(timezone.utc).isoformat(), "results": []}, f, indent=2)
        return 1

    manual_products = load_manual_products()
    if manual_products:
        print(f"Loaded verified manual product data for {len(manual_products)} ASIN(s).")

    jobs = jobs[:MAX_JOBS_PER_RUN]
    summary = []
    success_count = 0

    for idx, job in enumerate(jobs, start=1):
        job_type = (job.get("type") or "").strip().lower()
        keyword = (job.get("focus_keyword") or "").strip()
        asins = job["asins"]

        print(f"\n=== Job {idx}/{len(jobs)}: type={job_type} keyword='{keyword}' asins={asins} ===")

        if not keyword or not asins:
            summary.append({"job": idx, "status": "skipped", "reason": "missing_keyword_or_asins"})
            continue
        if job_type == "single" and len(asins) != 1:
            summary.append({"job": idx, "status": "skipped", "reason": "bad_asin_count"})
            continue
        if job_type == "vs" and not (2 <= len(asins) <= 3):
            summary.append({"job": idx, "status": "skipped", "reason": "bad_asin_count"})
            continue
        if job_type == "list" and not (3 <= len(asins) <= 10):
            summary.append({"job": idx, "status": "skipped", "reason": "bad_asin_count"})
            continue
        if job_type not in {"single", "vs", "list"}:
            summary.append({"job": idx, "status": "skipped", "reason": "unknown_job_type"})
            continue

        products = []
        sources = {}
        for asin in asins:
            print(f"  Retrieving {asin} ...")
            product, source = get_product(asin, manual_products)
            products.append(product)
            sources[asin] = source
            if source == "scraped":
                time.sleep(3)

        skipped = []
        if job_type == "list":
            skipped = [p.asin for p in products if not p.ok]
            products = [p for p in products if p.ok]
            if len(products) < 3:
                print("  FAILED: fewer than 3 products have usable data.")
                summary.append({"job": idx, "status": "failed", "reason": "insufficient_product_data",
                                "asins": asins, "skipped_asins": skipped, "sources": sources})
                continue
        elif not all(p.ok for p in products):
            summary.append({"job": idx, "status": "failed", "reason": "missing_product_data",
                            "asins": asins, "sources": sources})
            continue

        try:
            if job_type == "single":
                article = generate_single_article(products[0], keyword)
            elif job_type == "list":
                article = generate_list_article(products, keyword)
            else:
                article = generate_vs_article(products, keyword)
        except Exception as e:
            print(f"  FAILED to generate article: {e}")
            summary.append({"job": idx, "status": "failed", "reason": f"llm_error: {e}", "sources": sources})
            continue

        try:
            filename = safe_filename(article["title"], idx)
            out_path = os.path.join(OUTPUT_DIR, filename)
            image_urls = [p.image_url for p in products if p.image_url]
            if job_type == "list":
                image_urls = image_urls[:1]
            html_to_docx(article["title"], article["html"], out_path, image_urls)
            print(f"  SAVED: {out_path}")
            success_count += 1
            summary.append({
                "job": idx, "status": "success", "file": filename,
                "title": article["title"], "sources": sources,
                **({"word_count": article["word_count"], "skipped_asins": skipped}
                   if job_type == "list" else {}),
            })
        except Exception as e:
            print(f"  FAILED to save .docx: {e}")
            summary.append({"job": idx, "status": "failed", "reason": f"docx_error: {e}", "sources": sources})

    print("\n=== RUN SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    with open("run_summary.json", "w", encoding="utf-8") as f:
        json.dump({"run_at": datetime.now(timezone.utc).isoformat(), "results": summary},
                  f, indent=2, ensure_ascii=False)

    if success_count == 0:
        print("\nERROR: No article was generated. Marking this workflow run as failed.")
        return 1
    print(f"\nGenerated {success_count} article(s).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
