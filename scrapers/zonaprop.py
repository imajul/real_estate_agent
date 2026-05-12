"""
ZonaProp scraper using Playwright (headless Chromium) to bypass 403 blocks.

URL pattern:
  https://www.zonaprop.com.ar/departamentos-venta-{neighborhood}.html
  https://www.zonaprop.com.ar/departamentos-venta-{neighborhood}-pagina-{n}.html
"""

import json
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
}

BASE_URL = "https://www.zonaprop.com.ar"


def _slug(neighborhood: str) -> str:
    slug = neighborhood.lower().replace(" ", "-").replace("_", "-")
    return NEIGHBORHOOD_SLUGS.get(neighborhood.lower().replace(" ", "_"), slug)


def _parse_price(raw: dict) -> tuple[Optional[float], Optional[float]]:
    currency = raw.get("currency", "")
    amount = raw.get("price")
    if amount is None:
        return None, None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None, None
    if currency == "USD":
        return amount, None
    if currency == "ARS":
        return None, amount
    return None, None


def _extract_amenities(posting: dict) -> list[str]:
    amenities = []
    features = posting.get("generalFeatures", {}) or {}
    if features.get("balcony"):     amenities.append("balcón")
    if features.get("terrace"):     amenities.append("terraza")
    if features.get("pool"):        amenities.append("pileta")
    if features.get("gym"):         amenities.append("gimnasio")
    if features.get("laundry"):     amenities.append("laundry")
    if features.get("barbecue"):    amenities.append("parrilla")
    if features.get("elevator"):    amenities.append("ascensor")
    if features.get("security"):    amenities.append("seguridad 24hs")
    for tag in posting.get("tags", []):
        name = tag.get("label", "").lower()
        if name and name not in amenities:
            amenities.append(name)
    return amenities


def _posting_to_property(posting: dict) -> Optional[Property]:
    try:
        prop_id = str(posting.get("postingId") or posting.get("id") or uuid.uuid4())
        url_path = posting.get("url", "")
        url = f"{BASE_URL}{url_path}" if url_path.startswith("/") else url_path

        price_data = posting.get("priceOperationTypes", [{}])[0] if posting.get("priceOperationTypes") else {}
        price_usd, price_ars = _parse_price(price_data)

        surface_total   = posting.get("totalArea") or posting.get("totalSurface")
        surface_covered = posting.get("coveredArea") or posting.get("coveredSurface")

        geo = posting.get("postingLocation", {}) or {}
        address_parts = [
            geo.get("address", {}).get("name", ""),
            geo.get("location", {}).get("name", ""),
        ]
        address = ", ".join(p for p in address_parts if p) or "Sin dirección"
        neighborhood = (
            geo.get("subDivision", {}).get("name", "")
            or geo.get("location", {}).get("name", "")
            or "Desconocido"
        )

        title       = posting.get("title", "") or f"Prop. {prop_id}"
        description = posting.get("descriptionNormalized", "") or posting.get("description", "")
        rooms       = posting.get("rooms")
        bedrooms    = posting.get("bedrooms")
        bathrooms   = posting.get("bathrooms")
        floor_data  = posting.get("postingFloor") or {}
        floor       = floor_data.get("floor")
        total_floors= floor_data.get("totalFloors")
        parking     = bool(posting.get("parkingLots"))
        amenities   = _extract_amenities(posting)
        photos_count= len(posting.get("photos", []))
        antiquity   = posting.get("antiquity")
        expenses    = posting.get("expenses")

        prop_type_raw = posting.get("postingType", "").lower()
        if "casa" in prop_type_raw:
            prop_type = PropertyType.CASA
        elif "ph" in prop_type_raw:
            prop_type = PropertyType.PH
        else:
            prop_type = PropertyType.DEPARTAMENTO

        return Property(
            id=prop_id,
            source=PropertySource.ZONAPROP,
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
            description=description,
            expenses=expenses,
            floor=floor,
            total_floors=total_floors,
            parking=parking,
            amenities=amenities,
            photos_count=photos_count,
            antiquity_years=antiquity,
            raw_data=posting,
        )
    except Exception:
        return None


def _parse_html(html: str) -> tuple[list[Property], bool]:
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return [], False
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return [], False

    props = (
        data.get("props", {})
        .get("pageProps", {})
        .get("initialResultData", {})
    )
    if not props:
        props = data.get("props", {}).get("pageProps", {})

    postings = (
        props.get("listingData", {}).get("postings", [])
        or props.get("postings", [])
        or []
    )

    properties = [p for p in (_posting_to_property(x) for x in postings) if p]

    pagination   = props.get("pagination", {}) or {}
    total_pages  = pagination.get("totalPages", 1)
    current_page = pagination.get("currentPage", 1)
    has_next     = current_page < total_pages

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

                page_props, has_next = _parse_html(html)
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
