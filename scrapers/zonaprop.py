"""
ZonaProp scraper.

ZonaProp renders its listing data inside a <script id="__NEXT_DATA__"> JSON blob,
so a plain HTTP GET is sufficient (no headless browser needed).

URL pattern:
  https://www.zonaprop.com.ar/departamentos-venta-{neighborhood}.html
  https://www.zonaprop.com.ar/departamentos-venta-{neighborhood}-pagina-{n}.html
"""

import json
import re
import uuid
from typing import Optional
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
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
    """Return (price_usd, price_ars)."""
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
    if features.get("balcony"):
        amenities.append("balcón")
    if features.get("terrace"):
        amenities.append("terraza")
    if features.get("pool"):
        amenities.append("pileta")
    if features.get("gym"):
        amenities.append("gimnasio")
    if features.get("laundry"):
        amenities.append("laundry")
    if features.get("barbecue"):
        amenities.append("parrilla")
    if features.get("elevator"):
        amenities.append("ascensor")
    if features.get("security"):
        amenities.append("seguridad 24hs")
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

        surface_total = posting.get("totalArea") or posting.get("totalSurface")
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

        title = posting.get("title", "") or f"Prop. {prop_id}"
        description = posting.get("descriptionNormalized", "") or posting.get("description", "")
        rooms = posting.get("rooms")
        bedrooms = posting.get("bedrooms")
        bathrooms = posting.get("bathrooms")
        floor_data = posting.get("postingFloor") or {}
        floor = floor_data.get("floor")
        total_floors = floor_data.get("totalFloors")
        parking = bool(posting.get("parkingLots"))
        amenities = _extract_amenities(posting)
        photos_count = len(posting.get("photos", []))
        antiquity = posting.get("antiquity")
        expenses = posting.get("expenses")

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


class ZonaPropScraper(BaseScraper):
    """Scrape property listings from ZonaProp."""

    def _build_url(self, neighborhood: str, page: int = 1) -> str:
        slug = _slug(neighborhood)
        base = f"{BASE_URL}/departamentos-venta-{slug}"
        if page > 1:
            return f"{base}-pagina-{page}.html"
        return f"{base}.html"

    def _parse_page(self, html: str) -> tuple[list[Property], bool]:
        """Parse a listing page. Returns (properties, has_next_page)."""
        soup = BeautifulSoup(html, "lxml")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            # Fallback: try JSON in script tags
            scripts = soup.find_all("script", type="application/json")
            for s in scripts:
                try:
                    data = json.loads(s.string or "")
                    if "postings" in str(data):
                        script = s
                        break
                except Exception:
                    continue

        if not script or not script.string:
            return [], False

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return [], False

        # Navigate Next.js data structure
        props = (
            data.get("props", {})
            .get("pageProps", {})
            .get("initialResultData", {})
        )
        if not props:
            # Try alternative path
            props = data.get("props", {}).get("pageProps", {})

        postings = (
            props.get("listingData", {}).get("postings", [])
            or props.get("postings", [])
            or []
        )

        properties = []
        for p in postings:
            prop = _posting_to_property(p)
            if prop:
                properties.append(prop)

        pagination = props.get("pagination", {}) or {}
        total_pages = pagination.get("totalPages", 1)
        current_page = pagination.get("currentPage", 1)
        has_next = current_page < total_pages

        return properties, has_next

    def search(self, neighborhood: str, max_results: int = 50) -> list[Property]:
        properties: list[Property] = []
        page = 1

        while len(properties) < max_results:
            url = self._build_url(neighborhood, page)
            try:
                response = self._get(url)
                page_props, has_next = self._parse_page(response.text)
            except Exception as e:
                print(f"[ZonaProp] Error en página {page}: {e}")
                break

            properties.extend(page_props)

            if not has_next or not page_props:
                break
            page += 1

        return properties[:max_results]
