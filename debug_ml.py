"""Debug MercadoLibre listing page structure."""
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json, re

URL = "https://inmuebles.mercadolibre.com.ar/departamentos/venta/capital-federal/palermo/"

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
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, "lxml")
print(f"Title: {soup.title.string if soup.title else 'N/A'}")
print(f"HTML length: {len(html)}")

# Find listing cards
for selector in [
    ".ui-search-result__wrapper",
    ".ui-search-result",
    ".andes-card",
    "[class*='result']",
    "[class*='listing']",
]:
    items = soup.select(selector)
    if items:
        print(f"\nSelector '{selector}': {len(items)} items found")
        print("First item classes:", items[0].get("class"))
        print("First item HTML (500 chars):", str(items[0])[:500])
        break

# Look for price elements
print("\n=== Price elements ===")
for sel in ["[class*='price']", ".price-tag", ".andes-money-amount"]:
    els = soup.select(sel)
    if els:
        print(f"{sel}: {len(els)} found, first: {els[0].get_text(strip=True)[:80]}")

# Look for links to listings
print("\n=== Listing links ===")
links = soup.select("a[href*='MLA']")
print(f"Links with MLA: {len(links)}")
if links:
    print("First 3:", [l.get("href", "")[:80] for l in links[:3]])
