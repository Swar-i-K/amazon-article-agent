"""
doc_writer.py
-------------
Converts a generated article (title + HTML string) into an editable
Word (.docx) file using python-docx. Runs fully offline/free — no
external service, no WordPress needed. The person can open the .docx
in Word, Google Docs, or LibreOffice, edit it, and paste it into
WordPress (or anywhere else) themselves.
"""

import os
import re
import io
from typing import Optional

import requests
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Inches


def safe_filename(title: str, idx: int) -> str:
    name = re.sub(r"[^\w\s-]", "", title or "").strip()
    name = re.sub(r"\s+", "_", name)
    name = name[:60] or f"article_{idx}"
    return f"{idx:02d}_{name}.docx"


def _add_table(doc: Document, table_tag) -> None:
    rows = table_tag.find_all("tr")
    if not rows:
        return
    n_cols = max(len(r.find_all(["td", "th"])) for r in rows)
    if n_cols == 0:
        return
    t = doc.add_table(rows=0, cols=n_cols)
    try:
        t.style = "Light Grid Accent 1"
    except KeyError:
        pass  # style not available in this template, skip styling
    for r in rows:
        cells = r.find_all(["td", "th"])
        row_cells = t.add_row().cells
        for i, c in enumerate(cells):
            if i < n_cols:
                row_cells[i].text = c.get_text(strip=True)


def _render_element(doc: Document, el) -> None:
    name = getattr(el, "name", None)
    if name == "h1":
        doc.add_heading(el.get_text(strip=True), level=1)
    elif name == "h2":
        doc.add_heading(el.get_text(strip=True), level=2)
    elif name == "h3":
        doc.add_heading(el.get_text(strip=True), level=3)
    elif name == "p":
        text = el.get_text(strip=True)
        if text:
            doc.add_paragraph(text)
    elif name == "ul":
        for li in el.find_all("li", recursive=False):
            doc.add_paragraph(li.get_text(strip=True), style="List Bullet")
    elif name == "ol":
        for li in el.find_all("li", recursive=False):
            doc.add_paragraph(li.get_text(strip=True), style="List Number")
    elif name == "table":
        _add_table(doc, el)
    elif name in (None,):
        text = str(el).strip()
        if text:
            doc.add_paragraph(text)
    else:
        text = el.get_text(strip=True)
        if text:
            doc.add_paragraph(text)


def _embed_image(doc: Document, image_url: str) -> None:
    """Best-effort: download and embed a product image at the top of the
    doc. Never raises — if it fails, the doc is still created without it."""
    try:
        resp = requests.get(image_url, timeout=15)
        resp.raise_for_status()
        stream = io.BytesIO(resp.content)
        doc.add_picture(stream, width=Inches(3.5))
    except Exception:  # noqa: BLE001
        pass


def html_to_docx(
    title: str,
    html: str,
    output_path: str,
    image_urls: Optional[list] = None,
) -> None:
    doc = Document()
    doc.add_heading(title, level=0)

    for url in (image_urls or []):
        if url:
            _embed_image(doc, url)

    soup = BeautifulSoup(html, "html.parser")
    top_level = soup.find_all(recursive=False)
    for el in top_level:
        _render_element(doc, el)

    doc.save(output_path)
