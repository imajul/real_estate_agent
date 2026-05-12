"""
Market price analyzer.

Computes reference price/m² statistics from a list of properties
and identifies which properties are below market value.
"""

import statistics
from typing import Optional
from models import Property, MarketReference, PropertyType


# Historical reference prices (USD/m²) for CABA neighborhoods.
# Updated reference: ~2024-2025. Used as fallback when sample data is thin.
REFERENCE_PRICES: dict[str, dict[str, float]] = {
    "palermo": {
        "departamento": 2800,
        "casa": 3200,
        "ph": 2600,
    },
    "belgrano": {
        "departamento": 2700,
        "casa": 3100,
        "ph": 2500,
    },
    "recoleta": {
        "departamento": 3200,
        "casa": 3800,
        "ph": 3000,
    },
    "villa_crespo": {
        "departamento": 2200,
        "casa": 2600,
        "ph": 2000,
    },
    "caballito": {
        "departamento": 2100,
        "casa": 2400,
        "ph": 1900,
    },
    "flores": {
        "departamento": 1700,
        "casa": 2000,
        "ph": 1600,
    },
    "almagro": {
        "departamento": 2000,
        "casa": 2300,
        "ph": 1800,
    },
    "san_telmo": {
        "departamento": 2400,
        "casa": 2800,
        "ph": 2200,
    },
    "puerto_madero": {
        "departamento": 5500,
        "casa": 6000,
        "ph": 5200,
    },
    "nunez": {
        "departamento": 2600,
        "casa": 3000,
        "ph": 2400,
    },
    "villa_urquiza": {
        "departamento": 2000,
        "casa": 2300,
        "ph": 1800,
    },
    "colegiales": {
        "departamento": 2300,
        "casa": 2700,
        "ph": 2100,
    },
    "chacarita": {
        "departamento": 2100,
        "casa": 2500,
        "ph": 1900,
    },
    "boedo": {
        "departamento": 1900,
        "casa": 2200,
        "ph": 1700,
    },
    "liniers": {
        "departamento": 1500,
        "casa": 1800,
        "ph": 1400,
    },
}

# Renovation cost estimates (USD/m²) by condition
RENOVATION_COST_PER_M2 = {
    "light": 200,      # cosmetic: paint, floors, fixtures
    "moderate": 450,   # kitchen, bathrooms, electrical
    "heavy": 800,      # structural, complete gut renovation
}


def _normalize_neighborhood(neighborhood: str) -> str:
    return neighborhood.lower().strip().replace(" ", "_").replace("-", "_")


def get_reference_price(neighborhood: str, prop_type: PropertyType = PropertyType.DEPARTAMENTO) -> Optional[float]:
    key = _normalize_neighborhood(neighborhood)
    ref = REFERENCE_PRICES.get(key, {})
    return ref.get(prop_type.value) or ref.get("departamento")


def compute_market_reference(
    properties: list[Property],
    neighborhood: str,
    prop_type: PropertyType = PropertyType.DEPARTAMENTO,
) -> MarketReference:
    """Compute price/m² statistics from scraped data, falling back to historical data."""
    prices_per_m2 = [
        p.price_per_m2
        for p in properties
        if p.price_per_m2 is not None and 500 < p.price_per_m2 < 15000
    ]

    fallback = get_reference_price(neighborhood, prop_type) or 2000.0

    if len(prices_per_m2) >= 5:
        avg = statistics.mean(prices_per_m2)
        median = statistics.median(prices_per_m2)
        min_p = min(prices_per_m2)
        max_p = max(prices_per_m2)
        sample_count = len(prices_per_m2)
    else:
        # Blend scraped data with historical reference
        if prices_per_m2:
            avg = statistics.mean(prices_per_m2) * 0.6 + fallback * 0.4
        else:
            avg = fallback
        median = avg
        min_p = avg * 0.75
        max_p = avg * 1.35
        sample_count = len(prices_per_m2)

    return MarketReference(
        neighborhood=neighborhood,
        avg_price_per_m2_usd=round(avg, 0),
        median_price_per_m2_usd=round(median, 0),
        min_price_per_m2_usd=round(min_p, 0),
        max_price_per_m2_usd=round(max_p, 0),
        sample_count=sample_count,
        property_type=prop_type,
    )


def estimate_renovation_cost(property: Property, condition: str = "moderate") -> float:
    """Estimate renovation cost in USD based on surface and assumed condition."""
    surface = property.surface_covered or property.surface_total or 50.0
    cost_per_m2 = RENOVATION_COST_PER_M2.get(condition, RENOVATION_COST_PER_M2["moderate"])
    return surface * cost_per_m2


def compute_discount(property: Property, market_ref: MarketReference) -> Optional[float]:
    """Return the % discount vs market median. Negative = below market."""
    if property.price_per_m2 is None or market_ref.median_price_per_m2_usd == 0:
        return None
    discount = (property.price_per_m2 / market_ref.median_price_per_m2_usd - 1) * 100
    return round(discount, 1)


def estimate_arv(
    property: Property,
    market_ref: MarketReference,
    premium_pct: float = 10.0,
) -> Optional[float]:
    """
    After Repair Value: surface × (market avg × (1 + premium/100)).
    The premium rewards a well-renovated unit being above average.
    """
    surface = property.surface_covered or property.surface_total
    if not surface:
        return None
    arv_per_m2 = market_ref.avg_price_per_m2_usd * (1 + premium_pct / 100)
    return round(surface * arv_per_m2, 0)


def identify_below_market(
    properties: list[Property],
    market_ref: MarketReference,
    threshold_pct: float = -10.0,
) -> list[Property]:
    """Return properties priced below market by at least threshold_pct."""
    result = []
    for p in properties:
        if p.price_per_m2 is None:
            continue
        discount = compute_discount(p, market_ref)
        if discount is not None and discount <= threshold_pct:
            result.append(p)
    return result
