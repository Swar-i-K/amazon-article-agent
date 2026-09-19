"""
main.py
-------
Orchestrator. Reads jobs.csv (you control which job is "single" and which
is "vs", and which ASINs go with it), then for each job:

  1. Scrapes each ASIN's product data (scraper.py)
  2. Generates an SEO article with the free Groq API (llm_generator.py)
  3. Saves the article as an editable Word (.docx) file in output/
     (doc_writer.py) — no WordPress connection needed.

Runs once, top to bottom, then exits (the GitHub Actions runner shuts down
automatically when the job finishes — nothing runs in the background).

After a run, go to the GitHub Actions run page -> "Artifacts" section at
the bottom -> download "generated-articles" -> unzip -> open each .docx
in Word / Google Docs / LibreOffice, edit as needed, and paste into
WordPress (or anywhere else) yourself.

jobs.csv format:
  type,focus_keyword,asins
  single,best wireless earbuds under 50,B0CHWRXH8B
  vs,budget blender comparison,B08P29T3WW;B0018UI4T6

Failed ASINs/jobs are logged and skipped — they do not stop the rest of
the run. A summary is printed (and written to run_summary.json) at the end.
"""

import csv
import json
import os
import time
from datetime import datetime, timezone

from scraper import scrape_asin
from llm_generator import generate_single_article, generate_vs_article
from doc_writer import html_to_docx, safe_filename

JOBS_FILE = "jobs.csv"
OUTPUT_DIR = "output"
MAX_JOBS_PER_RUN = 10  # safety cap: matches your 5-10/day plan


def load_jobs(path=JOBS_FILE):
    jobs = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["asins"] = [a.strip() for a in row["asins"].split(";") if a.strip()]
            jobs.append(row)
    return jobs


def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    jobs = load_jobs()
    if not jobs:
        print("jobs.csv is empty. Nothing to do.")
        return

    jobs = jobs[:MAX_JOBS_PER_RUN]
    summary = []

    for idx, job in enumerate(jobs, start=1):
        job_type = job["type"].strip().lower()
        keyword = job["focus_keyword"].strip()
        asins = job["asins"]

        print(f"\n=== Job {idx}/{len(jobs)}: type={job_type} "
              f"keyword='{keyword}' asins={asins} ===")

        if job_type == "single" and len(asins) != 1:
            print(f"  SKIP: 'single' job must have exactly 1 ASIN, got {len(asins)}")
            summary.append({"job": idx, "status": "skipped", "reason": "bad_asin_count"})
            continue
        if job_type == "vs" and not (2 <= len(asins) <= 3):
            print(f"  SKIP: 'vs' job must have 2-3 ASINs, got {len(asins)}")
            summary.append({"job": idx, "status": "skipped", "reason": "bad_asin_count"})
            continue

        # 1. Scrape
        products = []
        for asin in asins:
            print(f"  Scraping {asin} ...")
            p = scrape_asin(asin)
            if not p.ok:
                print(f"    FAILED ({p.error}). Skipping this job.")
            else:
                print(f"    OK: {p.title[:60]}...")
            products.append(p)
            time.sleep(3)

        if not all(p.ok for p in products):
            summary.append({"job": idx, "status": "failed",
                             "reason": "scrape_failed",
                             "asins": asins})
            continue

        # 2. Generate article
        try:
            if job_type == "single":
                article = generate_single_article(products[0], keyword)
            else:
                article = generate_vs_article(products, keyword)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED to generate article: {e}")
            summary.append({"job": idx, "status": "failed",
                             "reason": f"llm_error: {e}"})
            continue

        # 3. Save as editable Word document
        try:
            filename = safe_filename(article["title"], idx)
            out_path = os.path.join(OUTPUT_DIR, filename)
            image_urls = [p.image_url for p in products if p.image_url]
            html_to_docx(article["title"], article["html"], out_path, image_urls)
            print(f"  Saved: {out_path}")
            summary.append({
                "job": idx, "status": "success",
                "file": filename,
                "title": article["title"],
            })
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED to save .docx: {e}")
            summary.append({"job": idx, "status": "failed",
                             "reason": f"docx_error: {e}"})
            continue

        # be polite to Amazon between jobs
        time.sleep(5)

    print("\n=== RUN SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    with open("run_summary.json", "w", encoding="utf-8") as f:
        json.dump({
            "run_at": datetime.now(timezone.utc).isoformat(),
            "results": summary,
        }, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    run()
