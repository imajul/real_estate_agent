"""
MercadoLibre Real Estate scraper using Playwright (headless Chromium).

URL pattern:
  https://inmuebles.mercadolibre.com.ar/departamentos/venta/capital-federal/{neighborhood}/
  https://inmuebles.mercadolibre.com.ar/departamentos/venta/capital-federal/{neighborhood}/_Desde_{offset}
"""

import re
import uuid
from typing import Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Property, PropertySource, PropertyType, OperationType


BASE_URL = "https://inmuebles.mercadolibre.com.ar"
PAGE_SIZE = 48  # ML shows 48 results per page

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


def _slug(neighborhood: str) -> str:
    key = neighborhood.lower().replace(" ", "_")
    return NEIGHBORHOOD_SLUGS.get(key, neighborhood.lower().replace("_", "-"))


def _parse_price(text: str) -> tuple[Optional[float], Optional[float]]:
    """Parse 'US$134.100' or '$ 50.000.000' → (usd, ars)."""
    text = text.strip()
    is_usd = "US$" in text or "USD" in text.upper()
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None, None
    try:
        amount = float(digits)
    except ValueError:
        return None, None
    return (amount, None) if is_usd else (None, amount)


def _parse_int(text: str) -> Optional[int]:
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _parse_surface(texts: list[str]) -> tuple[Optional[float], Optional[float]]:
    total = covered = None
    for t in texts:
        t_low = t.lower()
        if "m²" in t_low or "m2" in t_low:
            nums = re.findall(r"[\d]+", t)
            if nums:
                val = float(nums[0])
                if "cub" in t_low:
                    covered = val
                else:
                    total = val
    return total, covered


def _card_to_property(card) -> Optional[Property]:
    try:
        # Title
        title_el = card.select_one("a.poly-component__title")
        title = title_el.get_text(strip=True) if title_el else ""
        url = title_el.get("href", "") if title_el else ""
        if not title:
            title = card.select_one("span.poly-component__headline")
            title = title.get_text(strip=True) if title else f"Prop. {uuid.uuid4()}"

        # Price
        price_el = card.select_one(".andes-money-amount")
        price_usd, price_ars = (None, None)
        if price_el:
            price_usd, price_ars = _parse_price(price_el.get_text(strip=True))

        # All text spans for attributes
        spans = [s.get_text(strip=True) for s in card.select(".poly-attributes-list__item, .poly-component__attributes span, [class*='attribute']")]
        full_text = card.get_text(separator=" ", strip=True)

        # Surface
        surface_total, surface_covered = _parse_surface(spans + [full_text])

        # Rooms
        rooms = None
        m = re.search(r"(\d+)\s*(?:a\s*\d+\s*)?amb", full_text, re.I)
        if m:
            rooms = int(m.group(1))

        # Bedrooms
        bedrooms = None
        m = re.search(r"(\d+)\s*dorm", full_text, re.I)
        if m:
            bedrooms = int(m.group(1))

        # Bathrooms
        bathrooms = None
        m = re.search(r"(\d+)\s*ba[ñn]", full_text, re.I)
        if m:
            bathrooms = int(m.group(1))

        # Address
        addr_el = card.select_one(".poly-component__location, [class*='location'], [class*='address']")
        if addr_el:
            address = addr_el.get_text(strip=True)
        else:
            m = re.search(r"([A-ZÁÉÍÓÚ][^|,]+(?:,\s*[^|]+)?Capital Federal)", full_text)
            address = m.group(0).strip() if m else "Sin dirección"

        # Neighborhood from address
        neighborhood = "Desconocido"
        for nb in NEIGHBORHOOD_SLUGS:
            if nb.replace("_", " ") in full_text.lower() or nb in full_text.lower():
                neighborhood = nb.replace("_", " ").title()
                break

        # Parking
        parking = bool(re.search(r"coch|garage|parking", full_text, re.I))

        # Amenities
        amenities = []
        for kw, label in [("pileta", "pileta"), ("piscina", "pileta"), ("gimnasio", "gimnasio"),
                           ("parrilla", "parrilla"), ("balcón", "balcón"), ("balcon", "balcón"),
                           ("terraza", "terraza"), ("amenities", "amenities")]:
            if kw in full_text.lower() and label not in amenities:
                amenities.append(label)

        # Property type
        tl = title.lower() + full_text.lower()
        if "casa" in tl:
            prop_type = PropertyType.CASA
        elif " ph " in tl or "ph " in tl:
            prop_type = PropertyType.PH
        else:
            prop_type = PropertyType.DEPARTAMENTO

        # Photos
        photos = len(card.select("img"))

        prop_id = str(uuid.uuid4())

        return Property(
            id=prop_id,
            source=PropertySource.MERCADOLIBRE,
            url=url,
            title=title,
            price_usd=price_usd,
            price_ars=price_ars,
            surface_total=surface_total,
            surface_covered=surface_covered,
            rooms=rooms,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            address=address,
            neighborhood=neighborhood,
            property_type=prop_type,
            operation_type=OperationType.VENTA,
            description="",
            parking=parking,
            amenities=amenities,
            photos_count=photos,
            raw_data={"title": title, "url": url},
        )
    except Exception:
        return None


def _parse_html(html: str) -> tuple[list[Property], bool]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".ui-search-result__wrapper")
    properties = [p for p in (_card_to_property(c) for c in cards) if p]

    # Has next page if we got a full page of results
    has_next = len(cards) >= PAGE_SIZE
    return properties, has_next


class MercadoLibreScraper:
    """Scrape MercadoLibre real estate using headless Chromium."""

    def _build_url(self, neighborhood: str, offset: int = 0) -> str:
        slug = _slug(neighborhood)
        base = f"{BASE_URL}/departamentos/venta/capital-federal/{slug}/"
        return f"{base}_Desde_{offset + 1}" if offset > 0 else base

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
            offset = 0

            while len(properties) < max_results:
                url = self._build_url(neighborhood, offset)
                try:
                    page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
                    html = page_obj.content()
                except Exception as e:
                    raise RuntimeError(f"Error cargando ML página (offset {offset}): {e}") from e

                page_props, has_next = _parse_html(html)
                properties.extend(page_props)

                if not has_next or not page_props:
                    break
                offset += PAGE_SIZE

            browser.close()

        return properties[:max_results]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# Keep get_access_token for backwards compatibility
def get_access_token(client_id: str, client_secret: str) -> str:
    raise RuntimeError(
        "MercadoLibre API requiere aprobación especial. "
        "El scraper ahora usa Playwright directamente."
    )
