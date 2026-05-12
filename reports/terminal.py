"""
Rich terminal report generator for flipping analysis results.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box

from models import FlippingAnalysis, MarketReference

console = Console()


def _score_color(score: float) -> str:
    if score >= 8:
        return "bold green"
    if score >= 6:
        return "green"
    if score >= 4:
        return "yellow"
    return "red"


def _discount_color(pct: float) -> str:
    if pct <= -15:
        return "bold green"
    if pct <= -5:
        return "green"
    if pct >= 10:
        return "red"
    return "white"


def print_market_summary(market_ref: MarketReference, neighborhood: str, total_props: int) -> None:
    console.print()
    console.rule(f"[bold cyan]Mercado: {neighborhood.title()}[/bold cyan]")
    console.print(
        f"  [bold]Precio promedio:[/bold] USD {market_ref.avg_price_per_m2_usd:,.0f}/m²  |  "
        f"[bold]Mediana:[/bold] USD {market_ref.median_price_per_m2_usd:,.0f}/m²  |  "
        f"[bold]Rango:[/bold] USD {market_ref.min_price_per_m2_usd:,.0f} – {market_ref.max_price_per_m2_usd:,.0f}/m²"
    )
    console.print(
        f"  [dim]Propiedades analizadas: {total_props}  |  "
        f"Muestra para referencia: {market_ref.sample_count}[/dim]"
    )


def print_results_table(analyses: list[FlippingAnalysis]) -> None:
    console.print()
    console.rule("[bold cyan]Ranking de Oportunidades de Flipping[/bold cyan]")

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", expand=False)
    table.add_column("#", justify="right", width=3, no_wrap=True)
    table.add_column("Score", justify="center", width=7, no_wrap=True)
    table.add_column("Rec.", width=12, no_wrap=True)
    table.add_column("Barrio", width=13, no_wrap=True)
    table.add_column("Propiedad", min_width=24, max_width=35)
    table.add_column("Precio", justify="right", width=12, no_wrap=True)
    table.add_column("m²", justify="right", width=5, no_wrap=True)
    table.add_column("USD/m²", justify="right", width=7, no_wrap=True)
    table.add_column("vs. mdo.", justify="right", width=8, no_wrap=True)
    table.add_column("ARV", justify="right", width=11, no_wrap=True)
    table.add_column("Ganancia", justify="right", width=11, no_wrap=True)
    table.add_column("ROI", justify="right", width=6, no_wrap=True)
    table.add_column("Fuente", width=12, no_wrap=True)

    for i, a in enumerate(analyses, 1):
        p = a.property
        score_str = f"[{_score_color(a.flipping_score)}]{a.flipping_score:.1f}/10[/{_score_color(a.flipping_score)}]"

        rec_color = {
            "COMPRAR": "bold green",
            "ANALIZAR MÁS": "yellow",
            "DESCARTAR": "red",
        }.get(a.flipping_recommendation, "white")
        rec_str = f"[{rec_color}]{a.flipping_recommendation or '—'}[/{rec_color}]"

        title_short = (p.title[:33] + "…") if len(p.title) > 33 else p.title

        surface = p.surface_covered or p.surface_total
        m2_str = f"{surface:.0f}" if surface else "—"

        ppm2_str = f"USD {p.price_per_m2:,.0f}" if p.price_per_m2 else "—"

        if a.discount_vs_market_pct is not None:
            disc_str = f"[{_discount_color(a.discount_vs_market_pct)}]{a.discount_vs_market_pct:+.1f}%[/{_discount_color(a.discount_vs_market_pct)}]"
        else:
            disc_str = "—"

        arv_str = f"USD {a.estimated_arv_usd:,.0f}" if a.estimated_arv_usd else "—"
        profit_str = f"USD {a.estimated_profit_usd:,.0f}" if a.estimated_profit_usd else "—"
        roi_str = f"{a.roi_pct:.0f}%" if a.roi_pct else "—"

        table.add_row(
            str(i),
            score_str,
            rec_str,
            p.neighborhood,
            title_short,
            p.display_price,
            m2_str,
            ppm2_str,
            disc_str,
            arv_str,
            profit_str,
            roi_str,
            p.source.value,
        )

    console.print(table)


def print_property_detail(analysis: FlippingAnalysis, rank: int) -> None:
    p = analysis.property
    score_color = _score_color(analysis.flipping_score)
    surface = p.surface_covered or p.surface_total

    title = (
        f"[bold]#{rank} {p.title}[/bold] — "
        f"[{score_color}]Score: {analysis.flipping_score:.1f}/10 ({analysis.score_label})[/{score_color}]"
    )

    # Build detail panels
    info_lines = [
        f"[bold]Barrio:[/bold] {p.neighborhood}",
        f"[bold]Dirección:[/bold] {p.address}",
        f"[bold]Tipo:[/bold] {p.property_type.value.title()}",
        f"[bold]Precio:[/bold] {p.display_price}",
        f"[bold]Superficie:[/bold] {surface:.0f} m²" if surface else "[bold]Superficie:[/bold] —",
        f"[bold]Precio/m²:[/bold] USD {p.price_per_m2:,.0f}" if p.price_per_m2 else "[bold]Precio/m²:[/bold] —",
    ]
    if p.rooms:
        info_lines.append(f"[bold]Ambientes:[/bold] {p.rooms}")
    if p.floor:
        info_lines.append(f"[bold]Piso:[/bold] {p.floor}" + (f"/{p.total_floors}" if p.total_floors else ""))
    if p.antiquity_years:
        info_lines.append(f"[bold]Antigüedad:[/bold] {p.antiquity_years} años")
    if p.amenities:
        info_lines.append(f"[bold]Amenities:[/bold] {', '.join(p.amenities)}")
    if p.expenses:
        info_lines.append(f"[bold]Expensas:[/bold] ARS {p.expenses:,.0f}/mes")

    fin_lines = []
    if analysis.discount_vs_market_pct is not None:
        color = _discount_color(analysis.discount_vs_market_pct)
        fin_lines.append(
            f"[bold]Descuento vs. mercado:[/bold] [{color}]{analysis.discount_vs_market_pct:+.1f}%[/{color}]"
        )
    if analysis.estimated_arv_usd:
        fin_lines.append(f"[bold]ARV estimado:[/bold] USD {analysis.estimated_arv_usd:,.0f}")
    if analysis.estimated_renovation_cost_usd:
        fin_lines.append(f"[bold]Costo renovación:[/bold] USD {analysis.estimated_renovation_cost_usd:,.0f}")
    if analysis.estimated_profit_usd:
        color = "green" if analysis.estimated_profit_usd > 0 else "red"
        fin_lines.append(f"[bold]Ganancia potencial:[/bold] [{color}]USD {analysis.estimated_profit_usd:,.0f}[/{color}]")
    if analysis.roi_pct:
        color = "green" if analysis.roi_pct > 10 else "yellow" if analysis.roi_pct > 0 else "red"
        fin_lines.append(f"[bold]ROI:[/bold] [{color}]{analysis.roi_pct:.0f}%[/{color}]")

    pros_text = "\n".join(f"[green]✓[/green] {pro}" for pro in analysis.pros) or "[dim]Sin datos[/dim]"
    cons_text = "\n".join(f"[red]✗[/red] {con}" for con in analysis.cons) or "[dim]Sin datos[/dim]"
    reno_text = "\n".join(f"[cyan]→[/cyan] {s}" for s in analysis.renovation_suggestions) or "[dim]Sin datos[/dim]"

    console.print()
    console.print(Panel(
        "\n".join([
            Columns([
                Panel("\n".join(info_lines), title="Ficha", expand=True),
                Panel("\n".join(fin_lines) if fin_lines else "[dim]Sin datos financieros[/dim]",
                      title="Financiero", expand=True),
            ]).__str__() if False else  # Columns doesn't render well in panels; use side-by-side text
            "\n".join(info_lines) + "\n\n" + "\n".join(fin_lines),
            "",
            f"[bold cyan]Pros:[/bold cyan]\n{pros_text}",
            "",
            f"[bold red]Contras:[/bold red]\n{cons_text}",
            "",
            f"[bold yellow]Sugerencias de renovación:[/bold yellow]\n{reno_text}",
            "",
            f"[bold]Resumen IA:[/bold] {analysis.ai_summary}",
            f"[bold]URL:[/bold] [link={p.url}]{p.url}[/link]",
        ]),
        title=title,
        border_style=score_color,
    ))


def print_full_report(
    analyses: list[FlippingAnalysis],
    market_ref: MarketReference,
    neighborhood: str,
    total_props: int,
    show_details: int = 3,
) -> None:
    console.print()
    console.rule("[bold magenta]ANÁLISIS DE FLIPPING INMOBILIARIO[/bold magenta]")
    print_market_summary(market_ref, neighborhood, total_props)
    print_results_table(analyses)

    if show_details > 0:
        console.print()
        console.rule(f"[bold cyan]Detalles Top {min(show_details, len(analyses))} Oportunidades[/bold cyan]")
        for i, analysis in enumerate(analyses[:show_details], 1):
            print_property_detail(analysis, i)

    console.print()
    console.rule("[bold magenta]FIN DEL REPORTE[/bold magenta]")
