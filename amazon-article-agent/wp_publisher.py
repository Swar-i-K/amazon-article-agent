"""
wp_publisher.py
----------------
Publishes generated articles to WordPress as DRAFTS (never auto-published)
using the built-in, free WordPress REST API + an "Application Password"
(WordPress core feature since 5.6, no plugin needed, no cost).

How to get WP_USERNAME / WP_APP_PASSWORD (free, 2 minutes):
  WP Admin -> Users -> Profile -> Application Passwords -> create one.

Set these as GitHub Actions secrets:
  WP_URL            e.g. https://yoursite.com   (no trailing slash)
  WP_USERNAME        your WP admin username
  WP_APP_PASSWORD    the generated application password
"""

import os
import requests
from typing import Optional


def _auth():
    user = os.environ.get("WP_USERNAME")
    app_pw = os.environ.get("WP_APP_PASSWORD")
    if not user or not app_pw:
        raise RuntimeError("WP_USERNAME / WP_APP_PASSWORD env vars not set.")
    return (user, app_pw)


def _base_url():
    url = os.environ.get("WP_URL")
    if not url:
        raise RuntimeError("WP_URL env var not set.")
    return url.rstrip("/")


def upload_featured_image(image_url: str, filename: str) -> Optional[int]:
    """Downloads an image from image_url and uploads it to the WP media
    library, returning the media ID (or None if it fails — non-fatal)."""
    try:
        img_resp = requests.get(image_url, timeout=20)
        img_resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return None

    try:
        media_endpoint = f"{_base_url()}/wp-json/wp/v2/media"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}.jpg"',
            "Content-Type": "image/jpeg",
        }
        resp = requests.post(
            media_endpoint,
            headers=headers,
            data=img_resp.content,
            auth=_auth(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception:  # noqa: BLE001
        return None


def create_draft_post(
    title: str,
    html_content: str,
    featured_media_id: Optional[int] = None,
    categories: Optional[list] = None,
    tags: Optional[list] = None,
) -> dict:
    """Creates a DRAFT post in WordPress. Returns the created post's JSON."""
    endpoint = f"{_base_url()}/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": html_content,
        "status": "draft",  # NEVER auto-publish
    }
    if featured_media_id:
        payload["featured_media"] = featured_media_id
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags

    resp = requests.post(endpoint, json=payload, auth=_auth(), timeout=30)
    resp.raise_for_status()
    return resp.json()
