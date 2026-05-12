#!/usr/bin/env python3
"""
Property Flipping Analyzer — Buenos Aires

Busca oportunidades de flipping en ZonaProp y MercadoLibre,
analiza precio por m², ventajas/desventajas de cada propiedad
y genera un ranking con potencial de ganancia estimada.

Uso:
  python main.py --neighborhood palermo
  python main.py --neighborhood caballito --sources zonaprop mercadolibre
  python main.py --demo                          # modo demo sin internet
  python main.py --neighborhood palermo --demo   # demo filtrado por barrio
"""

import argparse
import sys
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

load_dotenv()

from config import (
    SUPPORTED_NEIGHBORHOODS,
    DEFAULT_MAX_RESULTS,
    DEFAULT_TOP_N,
    DEFAULT_DETAIL_COUNT,
    DEFAULT_DISCOUNT_THRESHOLD,
    AI_MODEL,
    ARV_PREMIUM_PCT,
)
from models import Property, PropertyType
from analyzers.market import compute_market_reference, estimate_arv, compute_discount, estimate_renovation_cost
from analyzers.ai_evaluator import AIEvaluator, batch_evaluate
from reports.terminal import print_full_report, console as report_console

console = Console()


def _load_demo(neighborhood: str | None) -> list[Property]:
    from demo_data import DEMO_PROPERTIES
    if neighborhood:
        nb = neighborhood.lower()
        return [
            p for p in DEMO_PROPERTIES
            if nb in p.neighborhood.lower()
        ]
    return list(DEMO_PROPERTIES)


def _scrape_zonaprop(neighborhood: str, max_results: int) -> list[Property]:
    from scrapers.zonaprop import ZonaPropScraper
    with ZonaPropScraper() as scraper:
        return scraper.search(neighborhood, max_results)


def _scrape_mercadolibre(neighborhood: str, max_results: int) -> list[Property]:
    from scrapers.mercadolibre import MercadoLibreScraper
    with MercadoLibreScraper() as scraper:
        return scraper.search(neighborhood, max_results)


def run(
    neighborhood: str,
    sources: list[str],
    max_results: int,
    top_n: int,
    detail_count: int,
    demo_mode: bool,
    discount_threshold: float,
) -> None:
    console.rule("[bold magenta]FLIPPING ANALYZER — Buenos Aires[/bold magenta]")

    evaluator = AIEvaluator(model=AI_MODEL)
    if evaluator.available:
        console.print("[green]✓[/green] Claude AI disponible para análisis enriquecido")
    else:
        console.print(
            "[yellow]⚠[/yellow]  Claude AI no disponible "
            "(configurá ANTHROPIC_API_KEY). Usando análisis heurístico."
        )

    # ── 1. RECOLECCIÓN DE PROPIEDADES ──────────────────────────────────
    all_properties: list[Property] = []

    if demo_mode:
        console.print(f"\n[cyan]Modo demo:[/cyan] cargando propiedades de muestra...")
        all_properties = _load_demo(neighborhood if neighborhood != "all" else None)
        console.print(f"  → {len(all_properties)} propiedades cargadas")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            if "zonaprop" in sources:
                task = progress.add_task(f"[cyan]Scrapeando ZonaProp ({neighborhood})…", total=None)
                try:
                    zp_props = _scrape_zonaprop(neighborhood, max_results // len(sources))
                    all_properties.extend(zp_props)
                    progress.update(task, description=f"[green]ZonaProp: {len(zp_props)} propiedades[/green]")
                except Exception as e:
                    progress.update(task, description=f"[red]ZonaProp error: {e}[/red]")
                finally:
                    progress.stop_task(task)

            if "mercadolibre" in sources:
                task = progress.add_task(f"[cyan]Scrapeando MercadoLibre ({neighborhood})…", total=None)
                try:
                    ml_props = _scrape_mercadolibre(neighborhood, max_results // len(sources))
                    all_properties.extend(ml_props)
                    progress.update(task, description=f"[green]MercadoLibre: {len(ml_props)} propiedades[/green]")
                except Exception as e:
                    progress.update(task, description=f"[red]MercadoLibre error: {e}[/red]")
                finally:
                    progress.stop_task(task)

    if not all_properties:
        console.print(
            "[bold red]No se encontraron propiedades.[/bold red] "
            "Verificá la conexión o usá --demo para modo de demostración."
        )
        sys.exit(1)

    # ── 2. ANÁLISIS DE MERCADO ──────────────────────────────────────────
    display_neighborhood = neighborhood if neighborhood != "all" else "Buenos Aires"
    console.print(f"\n[cyan]Calculando referencia de mercado para {display_neighborhood}…[/cyan]")
    market_ref = compute_market_reference(all_properties, display_neighborhood)
    console.print(
        f"  → Precio mediana: USD {market_ref.median_price_per_m2_usd:,.0f}/m²  "
        f"| Propiedades con precio/m²: {market_ref.sample_count}/{len(all_properties)}"
    )

    # ── 3. EVALUACIÓN CON IA ────────────────────────────────────────────
    console.print(f"\n[cyan]Evaluando propiedades (top {top_n})…[/cyan]")
    analyses = batch_evaluate(all_properties, market_ref, evaluator, top_n=top_n)

    # ── 4. REPORTE ──────────────────────────────────────────────────────
    print_full_report(
        analyses=analyses,
        market_ref=market_ref,
        neighborhood=display_neighborhood,
        total_props=len(all_properties),
        show_details=detail_count,
    )

    # ── 5. RESUMEN DE MEJORES OPORTUNIDADES ─────────────────────────────
    buy_recs = [a for a in analyses if a.flipping_recommendation == "COMPRAR"]
    if buy_recs:
        console.print(
            f"\n[bold green]🏠 {len(buy_recs)} oportunidad(es) recomendada(s) para comprar:[/bold green]"
        )
        for a in buy_recs:
            p = a.property
            surface = p.surface_covered or p.surface_total or 0
            console.print(
                f"  • [bold]{p.title[:55]}[/bold]\n"
                f"    {p.display_price} | {surface:.0f}m² | "
                f"USD {p.price_per_m2:,.0f}/m² | Score: {a.flipping_score:.1f}/10\n"
                f"    [link={p.url}]{p.url}[/link]"
            )
    else:
        console.print("\n[yellow]No se encontraron oportunidades de compra directa en este lote.[/yellow]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analizador de oportunidades de flipping inmobiliario en Buenos Aires",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Barrios soportados: {', '.join(SUPPORTED_NEIGHBORHOODS)}

Ejemplos:
  python main.py --demo
  python main.py --neighborhood palermo --demo
  python main.py --neighborhood caballito --sources zonaprop
  python main.py --neighborhood belgrano --sources zonaprop mercadolibre --top 15
""",
    )
    parser.add_argument(
        "--neighborhood", "-n",
        default="all",
        help="Barrio a analizar (default: todos en demo mode)",
    )
    parser.add_argument(
        "--sources", "-s",
        nargs="+",
        default=["zonaprop", "mercadolibre"],
        choices=["zonaprop", "mercadolibre"],
        help="Fuentes a scrapear (default: ambas)",
    )
    parser.add_argument(
        "--max-results", "-m",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=f"Máximo de propiedades por fuente (default: {DEFAULT_MAX_RESULTS})",
    )
    parser.add_argument(
        "--top", "-t",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Top N oportunidades a rankear (default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--details", "-d",
        type=int,
        default=DEFAULT_DETAIL_COUNT,
        help=f"Cuántas propiedades mostrar en detalle (default: {DEFAULT_DETAIL_COUNT})",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Modo demo con datos de ejemplo (no requiere internet)",
    )
    parser.add_argument(
        "--discount",
        type=float,
        default=DEFAULT_DISCOUNT_THRESHOLD,
        help=f"Umbral de descuento vs. mercado %% (default: {DEFAULT_DISCOUNT_THRESHOLD})",
    )

    args = parser.parse_args()

    if args.neighborhood != "all" and args.neighborhood not in SUPPORTED_NEIGHBORHOODS:
        # Try with underscore/hyphen variants
        clean = args.neighborhood.lower().replace("-", "_").replace(" ", "_")
        if clean not in SUPPORTED_NEIGHBORHOODS:
            console.print(
                f"[yellow]Aviso:[/yellow] '{args.neighborhood}' no está en la lista de barrios conocidos. "
                f"Se intentará scrapear igualmente."
            )
        else:
            args.neighborhood = clean

    run(
        neighborhood=args.neighborhood,
        sources=args.sources,
        max_results=args.max_results,
        top_n=args.top,
        detail_count=args.details,
        demo_mode=args.demo,
        discount_threshold=args.discount,
    )


if __name__ == "__main__":
    main()
