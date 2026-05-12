"""
Claude AI property evaluator.

Uses Claude claude-sonnet-4-6 to analyze property listings and generate:
- Pros and cons for flipping
- Renovation suggestions
- Flipping score (0-10)
- Overall recommendation
"""

import json
import os
from typing import Optional
import anthropic

from models import Property, MarketReference, FlippingAnalysis
from analyzers.market import (
    compute_discount,
    estimate_arv,
    estimate_renovation_cost,
)


SYSTEM_PROMPT = """Eres un experto en inversión inmobiliaria con foco en flipping de propiedades en Buenos Aires, Argentina.
Tu tarea es analizar propiedades y evaluar su potencial para comprar, renovar y vender con ganancia.

Siempre respondés en español (Argentina). Sos directo, práctico y basás tus análisis en datos concretos.
Cuando analizás una propiedad, considerás:
- Precio por m² vs. el promedio del barrio
- Estado aparente de la propiedad según descripción
- Características que agregan valor (balcón, buena ubicación, planta baja/alta, luminosidad)
- Características que restan valor o elevan el costo de renovación (PH con techo propio, planta baja oscura, edificio antiguo sin expensas bajas)
- Potencial de revalorización post-renovación
- Tiempo estimado de venta en el barrio
"""

ANALYSIS_PROMPT_TEMPLATE = """Analizá esta propiedad para flipping inmobiliario:

## Datos de la propiedad
- **Título**: {title}
- **Tipo**: {property_type}
- **Barrio**: {neighborhood}
- **Dirección**: {address}
- **Precio pedido**: {display_price}
- **Precio por m²**: {price_per_m2}
- **Superficie cubierta**: {surface_covered} m²
- **Superficie total**: {surface_total} m²
- **Ambientes**: {rooms}
- **Dormitorios**: {bedrooms}
- **Baños**: {bathrooms}
- **Piso**: {floor}
- **Antigüedad**: {antiquity}
- **Amenities/características**: {amenities}
- **Parking**: {parking}
- **Expensas**: {expenses}
- **Fotos**: {photos_count}
- **Fuente**: {source}
- **URL**: {url}

## Descripción
{description}

## Contexto de mercado
- **Precio promedio del barrio**: USD {avg_price_per_m2}/m²
- **Precio mediana del barrio**: USD {median_price_per_m2}/m²
- **Descuento vs. mercado**: {discount_pct}%
- **ARV estimado** (valor post-renovación): USD {arv}
- **Costo estimado de renovación**: USD {reno_cost}
- **Ganancia potencial estimada**: USD {profit}

## Tu análisis
Respondé ÚNICAMENTE con un JSON válido con esta estructura exacta:
{{
  "pros": ["pro1", "pro2", ...],
  "cons": ["con1", "con2", ...],
  "renovation_suggestions": ["sugerencia1", "sugerencia2", ...],
  "flipping_score": <número del 0 al 10>,
  "ai_summary": "<resumen en 2-3 oraciones>",
  "flipping_recommendation": "<COMPRAR / ANALIZAR MÁS / DESCARTAR>",
  "estimated_renovation_condition": "<light|moderate|heavy>"
}}

Criterios para flipping_score:
- 9-10: Oportunidad excepcional, precio muy por debajo del mercado, buenas características
- 7-8: Buena oportunidad, vale la pena seguir
- 5-6: Oportunidad moderada, análisis adicional necesario
- 3-4: Poco margen, riesgo elevado
- 0-2: No recomendado para flipping
"""


def _build_prompt(property: Property, market_ref: Optional[MarketReference]) -> str:
    discount = compute_discount(property, market_ref) if market_ref else None
    arv = estimate_arv(property, market_ref) if market_ref else None
    reno_cost = estimate_renovation_cost(property, "moderate")
    profit = (arv - (property.price_usd or 0) - reno_cost) if arv and property.price_usd else None

    return ANALYSIS_PROMPT_TEMPLATE.format(
        title=property.title,
        property_type=property.property_type.value,
        neighborhood=property.neighborhood,
        address=property.address,
        display_price=property.display_price,
        price_per_m2=f"USD {property.price_per_m2:,.0f}" if property.price_per_m2 else "N/D",
        surface_covered=property.surface_covered or "N/D",
        surface_total=property.surface_total or "N/D",
        rooms=property.rooms or "N/D",
        bedrooms=property.bedrooms or "N/D",
        bathrooms=property.bathrooms or "N/D",
        floor=f"Piso {property.floor} de {property.total_floors}" if property.floor else "N/D",
        antiquity=f"{property.antiquity_years} años" if property.antiquity_years else "N/D",
        amenities=", ".join(property.amenities) if property.amenities else "sin datos",
        parking="Sí" if property.parking else "No",
        expenses=f"ARS {property.expenses:,.0f}/mes" if property.expenses else "N/D",
        photos_count=property.photos_count,
        source=property.source.value,
        url=property.url,
        description=property.description[:2000] if property.description else "Sin descripción",
        avg_price_per_m2=f"{market_ref.avg_price_per_m2_usd:,.0f}" if market_ref else "N/D",
        median_price_per_m2=f"{market_ref.median_price_per_m2_usd:,.0f}" if market_ref else "N/D",
        discount_pct=f"{discount:+.1f}" if discount is not None else "N/D",
        arv=f"{arv:,.0f}" if arv else "N/D",
        reno_cost=f"{reno_cost:,.0f}",
        profit=f"{profit:,.0f}" if profit else "N/D",
    )


class AIEvaluator:
    def __init__(self, model: str = "claude-sonnet-4-6"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self.model = model

    @property
    def available(self) -> bool:
        return self.client is not None

    def evaluate(
        self,
        property: Property,
        market_ref: Optional[MarketReference] = None,
    ) -> FlippingAnalysis:
        discount = compute_discount(property, market_ref) if market_ref else None
        arv = estimate_arv(property, market_ref) if market_ref else None
        reno_cost = estimate_renovation_cost(property, "moderate")
        profit = (arv - (property.price_usd or 0) - reno_cost) if arv and property.price_usd else None
        roi = (profit / ((property.price_usd or 1) + reno_cost) * 100) if profit else None

        analysis = FlippingAnalysis(
            property=property,
            market_ref=market_ref,
            discount_vs_market_pct=discount,
            estimated_renovation_cost_usd=reno_cost,
            estimated_arv_usd=arv,
            estimated_profit_usd=profit,
            roi_pct=round(roi, 1) if roi else None,
        )

        if self.client:
            self._ai_enrich(analysis, property, market_ref)
        else:
            self._heuristic_enrich(analysis, property, market_ref)

        return analysis

    def _ai_enrich(
        self,
        analysis: FlippingAnalysis,
        property: Property,
        market_ref: Optional[MarketReference],
    ) -> None:
        prompt = _build_prompt(property, market_ref)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            # Extract JSON even if surrounded by markdown fences
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            analysis.pros = data.get("pros", [])
            analysis.cons = data.get("cons", [])
            analysis.renovation_suggestions = data.get("renovation_suggestions", [])
            analysis.flipping_score = float(data.get("flipping_score", 0))
            analysis.ai_summary = data.get("ai_summary", "")
            analysis.flipping_recommendation = data.get("flipping_recommendation", "")

            # Refine renovation cost based on AI condition estimate
            condition = data.get("estimated_renovation_condition", "moderate")
            analysis.estimated_renovation_cost_usd = estimate_renovation_cost(property, condition)
            # Recompute profit with refined cost
            if analysis.estimated_arv_usd and property.price_usd:
                profit = analysis.estimated_arv_usd - property.price_usd - analysis.estimated_renovation_cost_usd
                analysis.estimated_profit_usd = round(profit, 0)
                inv = property.price_usd + analysis.estimated_renovation_cost_usd
                analysis.roi_pct = round(profit / inv * 100, 1) if inv > 0 else None
        except Exception as e:
            analysis.ai_summary = f"Error en análisis IA: {e}"
            self._heuristic_enrich(analysis, property, market_ref)

    def _heuristic_enrich(
        self,
        analysis: FlippingAnalysis,
        property: Property,
        market_ref: Optional[MarketReference],
    ) -> None:
        """Fallback rule-based analysis when AI is not available."""
        pros, cons = [], []
        score = 5.0

        # Price analysis
        if analysis.discount_vs_market_pct is not None:
            if analysis.discount_vs_market_pct <= -20:
                pros.append(f"Precio {abs(analysis.discount_vs_market_pct):.0f}% por debajo del mercado")
                score += 2.5
            elif analysis.discount_vs_market_pct <= -10:
                pros.append(f"Precio {abs(analysis.discount_vs_market_pct):.0f}% por debajo del mercado")
                score += 1.5
            elif analysis.discount_vs_market_pct <= -5:
                pros.append(f"Precio levemente por debajo del mercado ({analysis.discount_vs_market_pct:.0f}%)")
                score += 0.5
            elif analysis.discount_vs_market_pct >= 15:
                cons.append(f"Precio {analysis.discount_vs_market_pct:.0f}% sobre el mercado")
                score -= 2.0
            elif analysis.discount_vs_market_pct >= 5:
                cons.append(f"Precio levemente sobre el mercado ({analysis.discount_vs_market_pct:.0f}%)")
                score -= 0.5

        # Amenities
        amenities = property.amenities
        if "balcón" in amenities:
            pros.append("Tiene balcón (muy valorado en CABA)")
            score += 0.5
        if "terraza" in amenities:
            pros.append("Terraza propia agrega valor significativo")
            score += 0.8
        if "cochera" in amenities or property.parking:
            pros.append("Cochera incluida")
            score += 0.5
        if "pileta" in amenities:
            pros.append("Pileta en el edificio")
            score += 0.3

        # Floor
        if property.floor:
            if property.floor == 1:
                cons.append("Planta baja puede ser menos luminosa y menos segura")
                score -= 0.5
            elif property.floor >= 5:
                pros.append(f"Piso {property.floor} - buena altura, más luminosidad")
                score += 0.3

        # Antiquity
        if property.antiquity_years:
            if property.antiquity_years > 50:
                cons.append(f"Edificio antiguo ({property.antiquity_years} años) puede requerir más inversión")
                score -= 0.5
            elif property.antiquity_years < 15:
                pros.append("Edificio relativamente nuevo")
                score += 0.3

        # Surface
        surface = property.surface_covered or property.surface_total
        if surface:
            if surface < 35:
                cons.append("Superficie muy reducida limita el mercado de compradores")
                score -= 0.3
            elif surface > 80:
                pros.append("Superficie amplia, apta para familias")
                score += 0.2

        # ROI
        if analysis.roi_pct is not None:
            if analysis.roi_pct >= 20:
                pros.append(f"ROI estimado atractivo: {analysis.roi_pct:.0f}%")
                score += 1.0
            elif analysis.roi_pct >= 10:
                pros.append(f"ROI estimado razonable: {analysis.roi_pct:.0f}%")
                score += 0.5
            elif analysis.roi_pct < 5:
                cons.append(f"ROI estimado bajo: {analysis.roi_pct:.0f}%")
                score -= 1.0

        analysis.pros = pros
        analysis.cons = cons
        analysis.renovation_suggestions = [
            "Pintura completa y pisos laminados",
            "Renovación de cocina y baños",
            "Mejora de instalación eléctrica y luminarias",
            "Carpintería y aberturas",
        ]

        score = max(0.0, min(10.0, score))
        analysis.flipping_score = round(score, 1)

        if score >= 7:
            analysis.flipping_recommendation = "COMPRAR"
            analysis.ai_summary = (
                f"Propiedad con buen potencial de flipping en {property.neighborhood}. "
                f"Score: {score:.1f}/10. Se recomienda avanzar con due diligence."
            )
        elif score >= 5:
            analysis.flipping_recommendation = "ANALIZAR MÁS"
            analysis.ai_summary = (
                f"Oportunidad moderada en {property.neighborhood}. "
                f"Score: {score:.1f}/10. Requiere análisis adicional antes de decidir."
            )
        else:
            analysis.flipping_recommendation = "DESCARTAR"
            analysis.ai_summary = (
                f"Oportunidad poco atractiva para flipping en {property.neighborhood}. "
                f"Score: {score:.1f}/10. Bajo margen o múltiples desventajas."
            )


def batch_evaluate(
    properties: list[Property],
    market_ref: Optional[MarketReference],
    evaluator: AIEvaluator,
    top_n: int = 10,
) -> list[FlippingAnalysis]:
    """Evaluate all properties and return top N by flipping score."""
    from analyzers.market import compute_discount

    # Quick pre-filter: only properties with price data
    candidates = [p for p in properties if p.price_usd is not None]

    # Sort by price/m² discount before AI (to save API calls)
    def sort_key(p: Property) -> float:
        if p.price_per_m2 is None or market_ref is None:
            return 0.0
        disc = compute_discount(p, market_ref)
        return disc if disc is not None else 0.0

    candidates.sort(key=sort_key)

    # Evaluate top candidates (more AI calls for best opportunities)
    results = []
    for prop in candidates[:top_n * 2]:
        analysis = evaluator.evaluate(prop, market_ref)
        results.append(analysis)

    results.sort(key=lambda a: a.flipping_score, reverse=True)
    return results[:top_n]
