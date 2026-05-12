from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class PropertySource(str, Enum):
    ZONAPROP = "zonaprop"
    MERCADOLIBRE = "mercadolibre"
    DEMO = "demo"


class PropertyType(str, Enum):
    DEPARTAMENTO = "departamento"
    CASA = "casa"
    PH = "ph"
    LOCAL = "local"


class OperationType(str, Enum):
    VENTA = "venta"
    ALQUILER = "alquiler"


@dataclass
class Property:
    id: str
    source: PropertySource
    url: str
    title: str
    price_usd: Optional[float]
    price_ars: Optional[float]
    surface_total: Optional[float]   # m²
    surface_covered: Optional[float]  # m² cubiertos
    rooms: Optional[int]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    address: str
    neighborhood: str
    city: str = "Buenos Aires"
    property_type: PropertyType = PropertyType.DEPARTAMENTO
    operation_type: OperationType = OperationType.VENTA
    description: str = ""
    expenses: Optional[float] = None  # ARS/month
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    parking: bool = False
    amenities: list[str] = field(default_factory=list)
    photos_count: int = 0
    antiquity_years: Optional[int] = None
    raw_data: dict = field(default_factory=dict)

    @property
    def price_per_m2(self) -> Optional[float]:
        surface = self.surface_covered or self.surface_total
        if self.price_usd and surface and surface > 0:
            return self.price_usd / surface
        return None

    @property
    def display_price(self) -> str:
        if self.price_usd:
            return f"USD {self.price_usd:,.0f}"
        if self.price_ars:
            return f"ARS {self.price_ars:,.0f}"
        return "Sin precio"


@dataclass
class MarketReference:
    neighborhood: str
    avg_price_per_m2_usd: float
    median_price_per_m2_usd: float
    min_price_per_m2_usd: float
    max_price_per_m2_usd: float
    sample_count: int
    property_type: PropertyType = PropertyType.DEPARTAMENTO


@dataclass
class PropertyFeature:
    name: str
    is_positive: bool
    impact_description: str
    value_impact_pct: float  # estimated % impact on value


@dataclass
class FlippingAnalysis:
    property: Property
    market_ref: Optional[MarketReference]

    # Price analysis
    discount_vs_market_pct: Optional[float] = None  # negative = below market
    estimated_renovation_cost_usd: Optional[float] = None
    estimated_arv_usd: Optional[float] = None  # After Repair Value
    estimated_profit_usd: Optional[float] = None
    roi_pct: Optional[float] = None

    # AI analysis
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    renovation_suggestions: list[str] = field(default_factory=list)
    ai_summary: str = ""
    flipping_score: float = 0.0  # 0-10
    flipping_recommendation: str = ""

    # Computed features
    features: list[PropertyFeature] = field(default_factory=list)

    @property
    def is_below_market(self) -> bool:
        return self.discount_vs_market_pct is not None and self.discount_vs_market_pct < -5

    @property
    def score_label(self) -> str:
        if self.flipping_score >= 8:
            return "EXCELENTE"
        if self.flipping_score >= 6:
            return "BUENA"
        if self.flipping_score >= 4:
            return "MODERADA"
        return "BAJA"
