"""
MercadoLibre Real Estate scraper.

Uses the public MercadoLibre API (no auth required for search):
  https://api.mercadolibre.com/sites/MLA/search?category=MLA1459&...

Category IDs for Argentina real estate:
  MLA1459 = Inmuebles (root)
  MLA1467 = Departamentos
  MLA1472 = Casas
  MLA1475 = PHs
"""

import uuid
from typing import Optional
import httpx

from scrapers.base import BaseScraper
from models import Property, PropertySource, PropertyType, OperationType


API_BASE = "https://api.mercadolibre.com"


def get_access_token(client_id: str, client_secret: str) -> str:
    """Fetch an OAuth2 app token via client credentials grant."""
    resp = httpx.post(
        f"{API_BASE}/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]
CATEGORY_MAP = {
    PropertyType.DEPARTAMENTO: "MLA1467",
    PropertyType.CASA: "MLA1472",
    PropertyType.PH: "MLA1475",
}

# MercadoLibre neighborhood IDs for CABA (subset)
NEIGHBORHOOD_IDS: dict[str, str] = {
    "palermo": "TUxBUFBBTDQzNTM1",
    "belgrano": "TUxBUEJFTDQ2MzU1",
    "recoleta": "TUxBUFJFQzQyOTU1",
    "caballito": "TUxBUENBQjQ3NDU1",
    "flores": "TUxBUEZMTzQ3NTU1",
    "almagro": "TUxBUEFMTTQ2OTU1",
    "villa_crespo": "TUxBUFZJTDQ2MTU1",
    "san_telmo": "TUxBUFNBTjQyMTU1",
    "nunez": "TUxBUE5VTjQ0NTU1",
    "colegiales": "TUxBUENPTDQ2MjU1",
    "chacarita": "TUxBUENIQTQ2NjU1",
    "boedo": "TUxBUEJPRTQ3MzU1",
}


def _extract_attribute(attributes: list[dict], attr_id: str) -> Optional[str]:
    for a in attributes:
        if a.get("id") == attr_id:
            return a.get("value_name") or str(a.get("value_struct", {}).get("number", ""))
    return None


def _parse_surface(attributes: list[dict]) -> tuple[Optional[float], Optional[float]]:
    total = _extract_attribute(attributes, "TOTAL_AREA")
    covered = _extract_attribute(attributes, "COVERED_AREA")
    try:
        total_f = float(total) if total else None
    except ValueError:
        total_f = None
    try:
        covered_f = float(covered) if covered else None
    except ValueError:
        covered_f = None
    return total_f, covered_f


def _item_to_property(item: dict) -> Optional[Property]:
    try:
        item_id = item.get("id", str(uuid.uuid4()))
        permalink = item.get("permalink", "")
        title = item.get("title", "Sin título")

        # Price
        currency = item.get("currency_id", "USD")
        price = item.get("price")
        price_usd = float(price) if currency == "USD" and price else None
        price_ars = float(price) if currency == "ARS" and price else None

        attributes = item.get("attributes", [])
        surface_total, surface_covered = _parse_surface(attributes)

        rooms_raw = _extract_attribute(attributes, "ROOMS")
        bedrooms_raw = _extract_attribute(attributes, "BEDROOMS")
        bathrooms_raw = _extract_attribute(attributes, "FULL_BATHROOMS")
        try:
            rooms = int(rooms_raw) if rooms_raw else None
            bedrooms = int(bedrooms_raw) if bedrooms_raw else None
            bathrooms = int(bathrooms_raw) if bathrooms_raw else None
        except ValueError:
            rooms = bedrooms = bathrooms = None

        # Location
        location = item.get("location", {})
        city_data = location.get("city", {})
        state_data = location.get("state", {})
        neighborhood_data = location.get("neighborhood", {})
        address_line = location.get("address_line", "")
        neighborhood = neighborhood_data.get("name", "") or city_data.get("name", "")
        city = state_data.get("name", "Buenos Aires")

        address = address_line or neighborhood or "Sin dirección"

        # Property type from category
        cat_id = item.get("category_id", "")
        if cat_id == "MLA1472":
            prop_type = PropertyType.CASA
        elif cat_id == "MLA1475":
            prop_type = PropertyType.PH
        else:
            prop_type = PropertyType.DEPARTAMENTO

        # Amenities from attributes
        amenities = []
        for attr in attributes:
            attr_id = attr.get("id", "")
            val = attr.get("value_name", "")
            if attr_id == "HAS_BALCONY" and val == "Si":
                amenities.append("balcón")
            elif attr_id == "HAS_POOL" and val == "Si":
                amenities.append("pileta")
            elif attr_id == "HAS_GYM" and val == "Si":
                amenities.append("gimnasio")
            elif attr_id == "PARKING_LOTS" and val not in ("0", "No", ""):
                amenities.append("cochera")
            elif attr_id == "HAS_GRILL" and val == "Si":
                amenities.append("parrilla")

        parking = "cochera" in amenities
        photos_count = len(item.get("pictures", []))

        # Antiquity
        antiquity_raw = _extract_attribute(attributes, "PROPERTY_AGE")
        try:
            antiquity = int(antiquity_raw) if antiquity_raw else None
        except ValueError:
            antiquity = None

        return Property(
            id=item_id,
            source=PropertySource.MERCADOLIBRE,
            url=permalink,
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
            city=city,
            property_type=prop_type,
            operation_type=OperationType.VENTA,
            description=item.get("description", ""),
            parking=parking,
            amenities=amenities,
            photos_count=photos_count,
            antiquity_years=antiquity,
            raw_data=item,
        )
    except Exception:
        return None


class MercadoLibreScraper(BaseScraper):
    """Scrape property listings from MercadoLibre using their public API."""

    def __init__(self, access_token: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.client.headers.update({"Accept": "application/json"})
        if access_token:
            self.client.headers.update({"Authorization": f"Bearer {access_token}"})

    def _search_api(
        self,
        neighborhood: str,
        prop_type: PropertyType = PropertyType.DEPARTAMENTO,
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        category = CATEGORY_MAP.get(prop_type, "MLA1467")
        nb_display = neighborhood.replace("_", " ")
        params: dict = {
            "category": category,
            "q": f"departamento venta {nb_display} capital federal",
            "limit": limit,
            "offset": offset,
            "sort": "price_asc",
        }

        url = f"{API_BASE}/sites/MLA/search"
        response = self._get(url, params=params)
        return response.json()

    def search(
        self,
        neighborhood: str,
        max_results: int = 50,
        prop_type: PropertyType = PropertyType.DEPARTAMENTO,
    ) -> list[Property]:
        properties: list[Property] = []
        offset = 0
        page_size = min(50, max_results)

        while len(properties) < max_results:
            try:
                data = self._search_api(neighborhood, prop_type, offset, page_size)
            except Exception as e:
                print(f"[MercadoLibre] Error en offset {offset}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for item in results:
                prop = _item_to_property(item)
                if prop:
                    properties.append(prop)

            paging = data.get("paging", {})
            total = paging.get("total", 0)
            offset += page_size

            if offset >= total or offset >= max_results:
                break

        return properties[:max_results]

    def get_item_details(self, item_id: str) -> Optional[dict]:
        """Fetch full item details including description."""
        try:
            item_resp = self._get(f"{API_BASE}/items/{item_id}")
            desc_resp = self._get(f"{API_BASE}/items/{item_id}/description")
            data = item_resp.json()
            data["description"] = desc_resp.json().get("plain_text", "")
            return data
        except Exception:
            return None
