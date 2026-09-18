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

import os
import re
import json
from typing import List

import requests

from scraper import Product

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.3-70b-versatile"  # strong quality, free-tier friendly


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
    """Calls the Groq chat completions endpoint and returns the text."""
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(GROQ_ENDPOINT, headers=_headers(), json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


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


def _make_title(subject: str, focus_keyword: str, kind: str) -> str:
    prompt = f"""
Write ONE single SEO-optimized WordPress post title (plain text, no quotes,
no HTML, max 65 characters) for a {"single-product review" if kind=="single" else "product comparison"}
article. Subject: {subject}. It must naturally include this focus keyword:
"{focus_keyword}". Return only the title text, nothing else.
"""
    title = _chat(prompt, temperature=0.6, max_tokens=60).strip().strip('"').strip()
    return title[:70]
