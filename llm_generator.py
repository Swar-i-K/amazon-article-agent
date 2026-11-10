"""
llm_generator.py
-----------------
Generates an SEO-friendly article (HTML, ready for WordPress) from scraped
product data, using Groq's **free** OpenAI-compatible API (super fast
inference, no credit card, generous free-tier daily limits — plenty for
5-10 articles/day).

Get a free key: https://console.groq.com/keys
Set it as a GitHub Actions secret named GROQ_API_KEY.
"""

import html as htmllib
import os
import re
import json
import time
from typing import List

import requests

from scraper import Product

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile was decommissioned by Groq on Aug 16, 2026

# list articles: show price + rating columns in the quick-comparison table (same data the "vs" articles use).
SHOW_PRICE_AND_RATING = True
# optional: set this env var to your Associates tracking ID (e.g. mysite-20) to add ?tag= to the product links.
ASSOCIATE_TAG_ENV = "AMAZON_ASSOCIATE_TAG"


def _headers():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable not set. "
            "Get a free key at https://console.groq.com/keys"
        )
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _chat(prompt: str, temperature: float = 0.7, max_tokens: int = 2500) -> str:
    """Calls the Groq chat completions endpoint and returns the text.
    Waits and retries on rate limits (429) and temporary server errors, because a 10-product article
    needs about a dozen calls in a row."""
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last = ""
    for attempt in range(6):
        resp = requests.post(GROQ_ENDPOINT, headers=_headers(), json=payload, timeout=90)
        if resp.status_code == 429 and "per day" in resp.text.lower():
            raise RuntimeError("Groq daily limit reached for this model. Try again later (the limit resets "
                               "on a rolling 24 hours). " + resp.text[:200])
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 5:
            try:
                wait = float(resp.headers.get("retry-after") or 0)
            except ValueError:
                wait = 0.0
            wait = min(65.0, (wait or 8 + attempt * 8) + 1)
            print(f"    Groq busy ({resp.status_code}), waiting {wait:.0f}s ...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        if text:
            return text
        last = "empty reply"
    raise RuntimeError(f"Groq returned no text ({last})")


def _product_block(p: Product, label: str) -> str:
    feats = "\n".join(f"- {f}" for f in p.features) or "- (no bullet points found)"
    return f"""
Product {label}:
- ASIN: {p.asin}
- Title: {p.title}
- Price: {p.price or "Not available, do not invent a number"}
- Rating: {p.rating or "Not available"}
- Review count: {p.review_count or "Not available"}
- Amazon URL: {p.url}
- Key features:
{feats}
""".strip()


def _extract_html(raw: str) -> str:
    """Model sometimes wraps output in ```html fences — strip them."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:html)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def generate_single_article(product: Product, focus_keyword: str) -> dict:
    prompt = f"""
You are an expert Amazon affiliate SEO content writer. Write a single-product
review article in clean HTML (only the tags below — no <html>/<head>/<body>,
this will be pasted straight into WordPress).

Focus keyword to rank for: "{focus_keyword}"

{_product_block(product, "under review")}

Requirements:
- Use ONLY the facts given above. Never invent a price, rating, or spec that
  wasn't provided. If price/rating is "Not available", write around it
  naturally (e.g. "check the current price on Amazon") instead of guessing.
- SEO structure: one <h1> title containing the focus keyword naturally, then
  <h2>/<h3> subheadings (e.g. Overview, Key Features, Pros & Cons,
  Who Should Buy This, FAQs, Final Verdict).
  Do not use markdown, only html tags.
- Include a short <ul> pros list and <ul> cons list (infer reasonable,
  honest pros/cons from the given features — do not fabricate defects or
  benefits not implied by the data).
- Include a 3-question FAQ section using the focus keyword and related
  long-tail phrases naturally (<h3> per question).
- Natural keyword usage — no keyword stuffing.
- 900-1300 words.
- End with a short, clearly-labelled affiliate disclosure sentence and a
  call-to-action linking the Amazon URL given above.
- Return ONLY the HTML body content, nothing else, no commentary, no
  markdown code fences.
"""
    html = _extract_html(_chat(prompt))
    title = _make_title(product.title, focus_keyword, kind="single")
    return {"title": title, "html": html}


def generate_vs_article(products: List[Product], focus_keyword: str) -> dict:
    blocks = "\n\n".join(
        _product_block(p, f"{i+1}") for i, p in enumerate(products)
    )
    names = " vs ".join(p.title or p.asin for p in products)

    prompt = f"""
You are an expert Amazon affiliate SEO content writer. Write a comparison
("X vs Y" style) article in clean HTML (only body tags — no
<html>/<head>/<body>, this goes straight into WordPress) comparing these
{len(products)} products:

{blocks}

Focus keyword to rank for: "{focus_keyword}"

Requirements:
- Use ONLY the facts given above for each product. Never invent a price,
  rating, or spec. If a field is "Not available", handle it gracefully in
  the text instead of guessing a number.
- SEO structure: one <h1> title containing the focus keyword naturally.
- Include an HTML <table> comparing the products side by side (columns:
  Product, Price, Rating, Key Features) using only the given data.
- Add an <h2> section per product with a short honest mini-review
  (strengths based on its features).
- Add an <h2> "Which One Should You Buy?" section giving practical
  guidance for different types of buyers (budget-conscious, best overall,
  etc.) based only on the given data.
- Include a 3-question FAQ section (<h3> per question) using the focus
  keyword and related long-tail phrases naturally.
- Natural keyword usage — no keyword stuffing.
- 1100-1600 words.
- End with a short, clearly-labelled affiliate disclosure and clear
  call-to-action links using each product's Amazon URL given above.
- Return ONLY the HTML body content, nothing else, no commentary, no
  markdown code fences.
"""
    html = _extract_html(_chat(prompt))
    title = _make_title(names, focus_keyword, kind="vs")
    return {"title": title, "html": html}


def _make_title(subject: str, focus_keyword: str, kind: str, count: int = 0) -> str:
    label = {"single": "single-product review", "vs": "product comparison",
             "list": f"ranked top-{count} product roundup"}.get(kind, "product comparison")
    prompt = f"""
Write ONE single SEO-optimized WordPress post title (plain text, no quotes,
no HTML, max 65 characters) for a {label}
article. Subject: {subject}. It must naturally include this focus keyword:
"{focus_keyword}". Return only the title text, nothing else.
"""
    title = _chat(prompt, temperature=0.6, max_tokens=400).strip().strip('"').strip()
    return title[:70]


# ---------------------------------------------------------------------------
# 10-product list article (3-10 products), written section by section so it stays
# under ~2,500 words and never runs into the model's output limit.
# ---------------------------------------------------------------------------

LIST_MAX_WORDS = 2450
DISCLOSURE = ("Disclosure: As an Amazon Associate I earn from qualifying purchases. Prices, ratings and "
              "availability can change, so check the Amazon listing for current details.")


def _short_name(p: Product, limit: int = 70) -> str:
    t = (p.title or p.asin or "").strip()
    t = re.split(r"\s[-|\u2013\u2014]\s|,", t)[0].strip() or t
    return t[:limit].rstrip()


def _link(p: Product) -> str:
    url = p.url or f"https://www.amazon.com/dp/{p.asin}"
    tag = os.environ.get(ASSOCIATE_TAG_ENV, "").strip()
    if tag and "tag=" not in url:
        url += ("&" if "?" in url else "?") + f"tag={tag}"
    return url


def _words(html: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", html).split())


def _quick_table(products: List[Product]) -> str:
    head = ["Rank", "Product"] + (["Price", "Rating"] if SHOW_PRICE_AND_RATING else [])
    rows = ["<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for i, p in enumerate(products, start=1):
        cells = [f"#{i}", htmllib.escape(_short_name(p, 60))]
        if SHOW_PRICE_AND_RATING:
            cells += [htmllib.escape(str(p.price or "Check on Amazon")), htmllib.escape(str(p.rating or "Not available"))]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return "<h2>Quick Comparison</h2><table>" + "".join(rows) + "</table>"


_RULES = """Rules:
- Use ONLY the facts given. Never invent a price, rating, spec, material, size or feature.
- Do not claim the author tested, owns or used the product. Describe what the listing says it offers.
- Do not write any price or rating numbers (a table shows them).
- No markdown, no code fences. Return only the HTML requested, nothing else."""


def _intro(products: List[Product], keyword: str, n: int) -> str:
    names = "; ".join(f"#{i}. {_short_name(p, 50)}" for i, p in enumerate(products, start=1))
    return _extract_html(_chat(f"""
You are an expert Amazon affiliate SEO content writer. Write the introduction of a "{n} best" roundup article.
Focus keyword: "{keyword}" (use it naturally in the first sentence).
Products, in the author's order of preference: {names}
Write exactly 2 short <p> paragraphs, about 90-110 words in total. Say the list is the author's own ranking,
not a lab test or a sales ranking, and tell the reader what to look for when choosing.
{_RULES}""", max_tokens=1500))


def _product_section(p: Product, rank: int, n: int, keyword: str) -> str:
    body = _extract_html(_chat(f"""
You are an expert Amazon affiliate SEO content writer. Write ONE section of a roundup article for product #{rank} of {n}.
Focus keyword of the article (use it only if it fits naturally): "{keyword}"

{_product_block(p, str(rank))}

Write exactly this HTML and nothing else:
<p>(an overview of 85-100 words based on the key features)</p>
<h3>Pros</h3><ul><li>..</li><li>..</li></ul>   (2-3 short items)
<h3>Cons</h3><ul><li>..</li></ul>   (1-2 short, honest items that follow from the features or from what is missing; do not invent defects)
<p><strong>Best for:</strong> (one short sentence)</p>
{_RULES}""", max_tokens=1800))
    head = f"<h2>#{rank}. {htmllib.escape(_short_name(p))}</h2>"
    link = f"<p>Check it on Amazon: {_link(p)}</p>"
    return head + body + link


def _closing(products: List[Product], keyword: str, n: int) -> str:
    names = "; ".join(f"#{i}. {_short_name(p, 50)}" for i, p in enumerate(products, start=1))
    return _extract_html(_chat(f"""
You are an expert Amazon affiliate SEO content writer. Write the end of a "{n} best" roundup article.
Focus keyword: "{keyword}". Products: {names}
Write exactly this HTML, about 300 words in total:
<h2>How to Choose</h2> then 2 short <p> (about 120 words total) with practical buying criteria for this kind of product
<h2>FAQs</h2> then 3 questions, each an <h3> followed by a <p> answer of at most 40 words, using the keyword and related phrases naturally
<h2>Final Verdict</h2> then one <p> of about 50 words that points readers to the table and the sections above
{_RULES}""", max_tokens=2500))


def generate_list_article(products: List[Product], focus_keyword: str) -> dict:
    """Roundup of 3-10 products, ranked in the order given. Returns {title, html, word_count}."""
    n = len(products)
    names = ", ".join(_short_name(p, 40) for p in products[:3])
    title = _make_title(f"{n} products including {names}", focus_keyword, kind="list", count=n)

    parts = [_intro(products, focus_keyword, n), _quick_table(products)]
    for i, p in enumerate(products, start=1):
        print(f"    writing section {i}/{n}: {_short_name(p, 50)}")
        parts.append(_product_section(p, i, n, focus_keyword))
    parts.append(_closing(products, focus_keyword, n))
    parts.append(f"<p><em>{DISCLOSURE}</em></p>")

    html = "\n".join(parts)
    wc = _words(html)
    if wc > LIST_MAX_WORDS:
        print(f"    WARNING: article is {wc} words (target under 2,500). Trim it by hand if needed.")
    return {"title": title, "html": html, "word_count": wc}
