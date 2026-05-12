"""Debug script: shows what ZonaProp actually returns."""
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json

URL = "https://www.zonaprop.com.ar/departamentos-venta-palermo.html"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="es-AR",
    )
    page = context.new_page()
    resp = page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    print(f"Status: {resp.status}")
    print(f"Final URL: {page.url}")
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, "lxml")
title = soup.title.string if soup.title else "(no title)"
print(f"Page title: {title}")
print(f"HTML length: {len(html)} chars")

script = soup.find("script", id="__NEXT_DATA__")
if script:
    print("__NEXT_DATA__ found!")
    try:
        data = json.loads(script.string)
        props = (
            data.get("props", {}).get("pageProps", {}).get("initialResultData", {})
            or data.get("props", {}).get("pageProps", {})
        )
        postings = (
            props.get("listingData", {}).get("postings", [])
            or props.get("postings", [])
            or []
        )
        print(f"Postings found: {len(postings)}")
        # Show top-level keys to understand structure
        print("pageProps keys:", list(data.get("props", {}).get("pageProps", {}).keys())[:10])
        if props:
            print("initialResultData keys:", list(props.keys())[:10])
    except Exception as e:
        print(f"JSON parse error: {e}")
else:
    print("NO __NEXT_DATA__ found!")
    print("First 2000 chars of HTML:")
    print(html[:2000])
