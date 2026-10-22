#!/usr/bin/env python3
"""Regenerate the site favicon PNGs from docs/favicon.svg (#favicon).

Design: stylised garden tree - mint #51b89a on navy #101f5b, the site's
own palette (administration-style, no official logo usage).
Renders docs/favicon.svg to docs/favicon-32.png and docs/apple-touch-icon.png
via headless Chromium (playwright). Run: python scripts/make_favicon.py
"""
import pathlib

from playwright.sync_api import sync_playwright

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"


def render(size: int, out: pathlib.Path) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": size, "height": size})
        page.goto((DOCS / "favicon.svg").as_uri())
        page.screenshot(path=str(out), omit_background=False)
        browser.close()


if __name__ == "__main__":
    render(32, DOCS / "favicon-32.png")
    render(180, DOCS / "apple-touch-icon.png")
    from PIL import Image
    Image.open(DOCS / "apple-touch-icon.png").convert("RGBA").save(
        DOCS / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("wrote PNG, Apple and multi-size ICO icons")
