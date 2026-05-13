"""
ZonaProp scraper using Playwright (headless Chromium) to bypass 403 blocks.

ZonaProp no longer embeds __NEXT_DATA__; listing data is in HTML cards
with data-qa attributes and supplementary JSON-LD scripts.

URL pattern:
  https://www.zonaprop.com.ar/departamentos-venta-{neighborhood}.html
  https://www.zonaprop.com.ar/departamentos-venta-{neighborhood}-pagina-{n}.html
"""

import json
import re
import uuid
from typing import Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Property, PropertySource, PropertyType, OperationType


NEIGHBORHOOD_SLUGS: dict[str, str] = {
    "palermo": "palermo",
    "belgrano": "belgrano",
    "recoleta": "recoleta",
    "villa_crespo": "villa-crespo",
    "caballito": "caballito",
    "flores": "flores",
    "almagro": "almagro",
    "san_telmo": "san-telmo",
    "puerto_madero": "puerto-madero",
    "nunez": "nunez",
    "villa_urquiza": "villa-urquiza",
    "colegiales": "colegiales",
    "chacarita": "chacarita",
    "boedo": "boedo",
    "liniers": "liniers",
    "saavedra": "saavedra",
}

BASE_URL = "https://www.zonaprop.com.ar"


def _slug(neighborhood: str) -> str:
    slug = neighborhood.lower().replace(" ", "-").replace("_", "-")
    return NEIGHBORHOOD_SLUGS.get(neighborhood.lower().replace(" ", "_"), slug)


def _parse_price_text(text: str) -> tuple[Optional[float], Optional[float]]:
    """Parse strings like 'USD 280.000' or '$ 1.200.000' → (usd, ars)."""
    text = text.strip()
    # Remove thousands separators (dots in es-AR) and currency symbols
    is_usd = text.upper().startswith("USD")
    digits = re.sub(r'[^\d]', '', text)
    if not digits:
        return None, None
    try:
        amount = float(digits)
    except ValueError:
        return None, None
    if is_usd:
        return amount, None
    return None, amount


def _parse_features(spans) -> dict:
    """Parse feature spans: '98 m² tot.', '5 amb.', '3 dorm.', '2 baños', '1 cochera'."""
    result: dict = {}
    for span in spans:
        text = span.get_text(strip=True).lower()
        m = re.search(r'([\d.]+)\s*m²\s*tot', text)
        if m:
            result['surface_total'] = float(m.group(1).replace('.', ''))
        m = re.search(r'([\d.]+)\s*m²\s*cub', text)
        if m:
            result['surface_covered'] = float(m.group(1).replace('.', ''))
        # bare "m²" with no qualifier → treat as total if not already set
        if 'surface_total' not in result and 'surface_covered' not in result:
            m = re.search(r'([\d.]+)\s*m²', text)
            if m:
                result['surface_total'] = float(m.group(1).replace('.', ''))
        m = re.search(r'(\d+)\s*amb', text)
        if m:
            result['rooms'] = int(m.group(1))
        m = re.search(r'(\d+)\s*dorm', text)
        if m:
            result['bedrooms'] = int(m.group(1))
        m = re.search(r'(\d+)\s*ba[ñn]', text)
        if m:
            result['bathrooms'] = int(m.group(1))
        if 'cochera' in text or 'garage' in text:
            result['parking'] = True
    return result


def _build_desc_map(soup: BeautifulSoup) -> dict[str, str]:
    """Build url_path → description from JSON-LD mainEntity blocks."""
    desc_map: dict[str, str] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            for entity in data.get("mainEntity", []):
                raw_url = entity.get("url", "")
                if ".com.ar/" in raw_url:
                    path = "/" + raw_url.split(".com.ar/", 1)[1]
                else:
                    path = raw_url
                desc = entity.get("description", "")
                if path and desc:
                    desc_map[path] = desc
        except Exception:
            pass
    return desc_map


def _parse_html(html: str, searched_neighborhood: str = "") -> tuple[list[Property], bool]:
    soup = BeautifulSoup(html, "lxml")
    desc_map = _build_desc_map(soup)

    cards = soup.find_all(attrs={"data-qa": re.compile(r'^posting ')})
    properties: list[Property] = []

    for card in cards:
        try:
            prop_id = card.get("data-id") or str(uuid.uuid4())
            url_path = card.get("data-to-posting", "")
            url = f"{BASE_URL}{url_path}" if url_path.startswith("/") else url_path

            # Price
            price_el = card.find(attrs={"data-qa": "POSTING_CARD_PRICE"})
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_usd, price_ars = _parse_price_text(price_text)

            # Expenses
            expenses: Optional[float] = None
            exp_el = card.find(attrs={"data-qa": "expensas"})
            if exp_el:
                exp_digits = re.sub(r'[^\d]', '', exp_el.get_text(strip=True))
                if exp_digits:
                    try:
                        expenses = float(exp_digits)
                    except ValueError:
                        pass

            # Surface, rooms, bedrooms, bathrooms, parking
            feat_el = card.find(attrs={"data-qa": "POSTING_CARD_FEATURES"})
            features: dict = {}
            if feat_el:
                features = _parse_features(feat_el.find_all("span"))

            # Address / location
            loc_el = card.find(attrs={"data-qa": "POSTING_CARD_LOCATION"})
            if not loc_el:
                loc_el = card.find(class_=re.compile(r'location|address|direction', re.I))
            address = loc_el.get_text(strip=True) if loc_el else "Sin dirección"
            neighborhood = searched_neighborhood or "Desconocido"

            # Title from img alt (contains "Departamento · Xm² · N Ambientes ...")
            img = card.find("img")
            title = img.get("alt", f"Prop. {prop_id}") if img else f"Prop. {prop_id}"

            # Description from JSON-LD
            description = desc_map.get(url_path, "")

            # Property type
            title_lower = title.lower()
            if "casa" in title_lower:
                prop_type = PropertyType.CASA
            elif " ph" in title_lower or title_lower.startswith("ph"):
                prop_type = PropertyType.PH
            else:
                prop_type = PropertyType.DEPARTAMENTO

            # Photos count from gallery images
            photos_count = len(card.find_all("img"))

            properties.append(Property(
                id=prop_id,
                source=PropertySource.ZONAPROP,
                url=url,
                title=title,
                price_usd=price_usd,
                price_ars=price_ars,
                surface_total=features.get('surface_total'),
                surface_covered=features.get('surface_covered'),
                rooms=features.get('rooms'),
                bedrooms=features.get('bedrooms'),
                bathrooms=features.get('bathrooms'),
                address=address,
                neighborhood=neighborhood,
                property_type=prop_type,
                operation_type=OperationType.VENTA,
                description=description,
                expenses=expenses,
                parking=features.get('parking', False),
                amenities=[],
                photos_count=photos_count,
                raw_data={"id": prop_id, "url_path": url_path},
            ))
        except Exception:
            continue

    # Pagination: next-page button or 30 results means more pages likely exist
    next_btn = soup.find(attrs={"data-qa": "PAGING_NEXT"})
    if next_btn is None:
        next_btn = soup.find("a", string=re.compile(r'siguiente|next', re.I))
    has_next = next_btn is not None or len(properties) >= 30

    return properties, has_next


class ZonaPropScraper:
    """Scrape ZonaProp using a headless Chromium browser to bypass bot detection."""

    def _build_url(self, neighborhood: str, page: int = 1) -> str:
        slug = _slug(neighborhood)
        base = f"{BASE_URL}/departamentos-venta-{slug}"
        return f"{base}-pagina-{page}.html" if page > 1 else f"{base}.html"

    def search(self, neighborhood: str, max_results: int = 50) -> list[Property]:
        properties: list[Property] = []

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
            page_obj = context.new_page()
            pg = 1

            while len(properties) < max_results:
                url = self._build_url(neighborhood, pg)
                try:
                    page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
                    html = page_obj.content()
                except Exception as e:
                    raise RuntimeError(f"Error cargando página {pg}: {e}") from e

                page_props, has_next = _parse_html(html, neighborhood)
                properties.extend(page_props)

                if not has_next or not page_props:
                    break
                pg += 1

            browser.close()

        return properties[:max_results]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
