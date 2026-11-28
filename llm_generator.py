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
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"

# Primary provider first; Gemini and Mistral are automatic fallbacks.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

# GitHub Actions secrets expected: GROQ_API_KEY, GEMINI_API_KEY, MISTRAL_API_KEY.
# Optional model overrides: GROQ_MODEL, GEMINI_MODEL, MISTRAL_MODEL.
SHOW_PRICE_AND_RATING = True
ASSOCIATE_TAG_ENV = "AMAZON_ASSOCIATE_TAG"


def _post_json(url: str, headers: dict, payload: dict) -> dict:
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def _chat_groq(prompt: str, temperature: float, max_tokens: int) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_error = None
    # Keep retries short; if Groq is rate-limited, move on to the fallback providers.
    for attempt in range(2):
        try:
            data = _post_json(
                GROQ_ENDPOINT,
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                payload,
            )
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            if content.strip():
                return content.strip()
            raise RuntimeError("Groq returned an empty response")
        except Exception as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status not in (429, 500, 502, 503, 504) or attempt == 1:
                break
            retry_after = getattr(exc.response, "headers", {}).get("Retry-After", "2")
            try:
                wait = min(5.0, max(1.0, float(retry_after)))
            except (TypeError, ValueError):
                wait = 2.0
            print(f"    Groq temporarily unavailable (HTTP {status}); retrying in {wait:.0f}s.")
            time.sleep(wait)
    raise RuntimeError(f"Groq failed: {last_error}")


def _chat_gemini(prompt: str, temperature: float, max_tokens: int) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    url = f"{GEMINI_ENDPOINT}/{GEMINI_MODEL}:generateContent?key={key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    data = _post_json(url, {"Content-Type": "application/json"}, payload)
    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    content = "".join(part.get("text", "") for part in parts).strip()
    if not content:
        raise RuntimeError("Gemini returned an empty response")
    return content


def _chat_mistral(prompt: str, temperature: float, max_tokens: int) -> str:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY is not configured")
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = _post_json(
        MISTRAL_ENDPOINT,
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload,
    )
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    if not content.strip():
        raise RuntimeError("Mistral returned an empty response")
    return content.strip()


def _chat(prompt: str, temperature: float = 0.7, max_tokens: int = 2500) -> str:
    """Try Groq first, then Gemini, then Mistral; each provider is used only if its secret exists."""
    providers = (
        ("Groq", _chat_groq),
        ("Gemini", _chat_gemini),
        ("Mistral", _chat_mistral),
    )
    failures = []
    for name, call in providers:
        env_key = {"Groq": "GROQ_API_KEY", "Gemini": "GEMINI_API_KEY",
                   "Mistral": "MISTRAL_API_KEY"}[name]
        if not os.environ.get(env_key):
            print(f"    {name} fallback skipped: {env_key} is not configured.")
            continue
        try:
            print(f"    Trying {name}...")
            result = call(prompt, temperature, max_tokens)
            print(f"    Generated successfully with {name}.")
            return result
        except Exception as exc:
            # Do not print request URLs or credentials; report provider and error only.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"HTTP {status}" if status else str(exc)
            failures.append(f"{name}: {detail}")
            print(f"    {name} failed ({detail}); trying next provider.")
    raise RuntimeError("All configured LLM providers failed. " + " | ".join(failures))


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
