import streamlit as st
import os
import sys
import io
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Flipping Inmobiliario BA",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Main background */
  .stApp { background-color: #f4f7fb; }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1F3864 0%, #2E5395 100%);
  }
  [data-testid="stSidebar"] * { color: #ffffff !important; }
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stMultiSelect label,
  [data-testid="stSidebar"] .stSlider label,
  [data-testid="stSidebar"] .stTextInput label,
  [data-testid="stSidebar"] .stCheckbox label { color: #cfe2ff !important; font-weight: 500; }

  /* Metric cards */
  [data-testid="metric-container"] {
    background: white;
    border: 1px solid #dde3f0;
    border-radius: 10px;
    padding: 12px 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }

  /* Property cards */
  .prop-card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    border: 1px solid #dde3f0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }
  .prop-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
  .badge-buy    { background:#C6EFCE; color:#276221; padding:4px 12px; border-radius:20px; font-weight:700; font-size:13px; }
  .badge-watch  { background:#FFEB9C; color:#9C6500; padding:4px 12px; border-radius:20px; font-weight:700; font-size:13px; }
  .badge-skip   { background:#FFC7CE; color:#9C0006; padding:4px 12px; border-radius:20px; font-weight:700; font-size:13px; }
  .score-high { color:#276221; font-weight:700; font-size:22px; }
  .score-med  { color:#9C6500; font-weight:700; font-size:22px; }
  .score-low  { color:#9C0006; font-weight:700; font-size:22px; }
  .stat-row { display:flex; gap:24px; flex-wrap:wrap; margin:10px 0; }
  .stat-item { font-size:13px; color:#555; }
  .stat-item b { color:#222; }
  .disc-pos { color:#276221; font-weight:700; }
  .disc-neg { color:#9C0006; font-weight:700; }

  /* Section headers */
  .section-title {
    font-size: 13px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.5px; color: #666; margin: 8px 0 4px;
  }
  .pro-item  { color:#276221; font-size:13px; margin:2px 0; }
  .con-item  { color:#9C0006; font-size:13px; margin:2px 0; }
  .reno-item { color:#2E5395; font-size:13px; margin:2px 0; }
  .summary-box {
    background:#f0f4ff; border-left:3px solid #2E5395;
    padding:8px 12px; border-radius:0 6px 6px 0;
    font-size:13px; color:#333; margin-top:10px;
  }

  /* Download button */
  .stDownloadButton button {
    background: #1F3864 !important;
    color: white !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 10px 24px !important;
    border: none !important;
    width: 100%;
  }
  .stDownloadButton button:hover { background: #2E5395 !important; }

  /* Run button */
  .stButton > button {
    background: #2E75B6 !important;
    color: white !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    border: none !important;
    width: 100%;
    padding: 10px !important;
  }
  .stButton > button:hover { background: #1F3864 !important; }

  div[data-testid="stExpander"] { background: white; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def badge_html(rec: str) -> str:
    cls = {"COMPRAR": "badge-buy", "ANALIZAR MÁS": "badge-watch", "DESCARTAR": "badge-skip"}.get(rec, "badge-watch")
    return f'<span class="{cls}">{rec}</span>'


def score_html(score: float) -> str:
    cls = "score-high" if score >= 7 else ("score-med" if score >= 5 else "score-low")
    return f'<span class="{cls}">{score:.1f}</span><span style="color:#999;font-size:14px">/10</span>'


def discount_html(pct: float) -> str:
    if pct <= -10:
        return f'<span class="disc-pos">▼ {abs(pct):.1f}% bajo mercado</span>'
    if pct >= 10:
        return f'<span class="disc-neg">▲ {pct:.1f}% sobre mercado</span>'
    return f'<span style="color:#555">{pct:+.1f}% vs mercado</span>'


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏠 Flipping BA")
    st.markdown("---")

    st.markdown("### 🔑 API Key")
    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-api03-...",
        help="Obtené tu key en console.anthropic.com",
    )

    st.markdown("---")
    st.markdown("### 🔍 Búsqueda")

    barrio = st.selectbox("Barrio", [
        "palermo", "belgrano", "recoleta", "villa_crespo", "caballito",
        "flores", "almagro", "san_telmo", "nunez", "colegiales",
        "chacarita", "boedo", "villa_urquiza",
    ], format_func=lambda x: x.replace("_", " ").title())

    fuentes = st.multiselect(
        "Fuentes",
        ["zonaprop", "mercadolibre"],
        default=["zonaprop", "mercadolibre"],
        format_func=lambda x: "ZonaProp" if x == "zonaprop" else "MercadoLibre",
    )
    if not fuentes:
        fuentes = ["zonaprop", "mercadolibre"]

    top_n = st.slider("Propiedades a rankear", 3, 20, 10)
    detalle_n = st.slider("Propiedades con detalle completo", 1, 10, 5)

    st.markdown("---")
    st.markdown("### ⚙️ Opciones")
    modo_demo = st.checkbox("Modo demo (sin internet)", value=True,
                            help="Usa datos de ejemplo para probar sin scraping real")

    st.markdown("---")
    run_btn = st.button("▶ Ejecutar análisis", use_container_width=True)


# ── Main area ─────────────────────────────────────────────────────────────────
st.markdown("# 🏠 Analizador de Flipping Inmobiliario")
st.markdown("**Buenos Aires** — Identificá oportunidades de compra, renovación y reventa")
st.markdown("---")

if not run_btn:
    # Landing state
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("**1.** Configurá los parámetros en el panel izquierdo")
    with col2:
        st.info("**2.** Hacé click en **Ejecutar análisis**")
    with col3:
        st.info("**3.** Descargá el reporte Excel con los resultados")

    st.markdown("""
    ### ¿Qué analiza el programa?
    | Métrica | Descripción |
    |---|---|
    | **Precio/m²** | Comparado con la mediana del barrio |
    | **Descuento vs. mercado** | % por debajo o encima del precio típico |
    | **ARV** | Valor estimado post-renovación |
    | **Costo de renovación** | Estimado según estado de la propiedad |
    | **Ganancia potencial y ROI** | Proyección financiera del flip |
    | **Pros y contras** | Análisis con Claude AI de cada aviso |
    """)
    st.stop()


# ── Execution ─────────────────────────────────────────────────────────────────
if api_key:
    os.environ["ANTHROPIC_API_KEY"] = api_key

# Reload modules to pick up fresh env
for mod in list(sys.modules.keys()):
    if any(mod.startswith(p) for p in ["models", "config", "demo_data", "scrapers", "analyzers", "reports"]):
        del sys.modules[mod]

try:
    from models import Property
    from analyzers.market import compute_market_reference
    from analyzers.ai_evaluator import AIEvaluator, batch_evaluate
except Exception as e:
    st.error(f"❌ Error al importar módulos: {e}")
    st.info("Asegurate de estar en la carpeta correcta del proyecto y que el repositorio esté actualizado (`git pull origin main`).")
    st.stop()

status = st.empty()
progress = st.progress(0)

# Step 1: collect properties
status.info("🔍 Recolectando propiedades...")
progress.progress(10)

all_properties = []
scraping_errors = []

if modo_demo:
    try:
        from demo_data import DEMO_PROPERTIES
        nb = barrio.lower()
        all_properties = [p for p in DEMO_PROPERTIES if nb in p.neighborhood.lower()]
        if not all_properties:
            all_properties = list(DEMO_PROPERTIES)
    except Exception as e:
        st.error(f"❌ Error cargando datos demo: {e}")
        st.stop()
else:
    if "zonaprop" in fuentes:
        try:
            from scrapers.zonaprop import ZonaPropScraper
            with ZonaPropScraper() as s:
                props = s.search(barrio, 50)
            all_properties.extend(props)
        except Exception as e:
            scraping_errors.append(f"**ZonaProp:** {e}")

    if "mercadolibre" in fuentes:
        try:
            from scrapers.mercadolibre import MercadoLibreScraper
            with MercadoLibreScraper() as s:
                props = s.search(barrio, 50)
            all_properties.extend(props)
        except Exception as e:
            scraping_errors.append(f"**MercadoLibre:** {e}")

    if scraping_errors:
        with st.expander("⚠️ Errores de scraping", expanded=True):
            for err in scraping_errors:
                st.warning(err)

if not all_properties:
    st.error("❌ No se encontraron propiedades.")
    if not modo_demo:
        st.info("💡 **Solución:** Activá el checkbox **'Modo demo (sin internet)'** en el panel izquierdo y volvé a ejecutar.")
    st.stop()

progress.progress(40)

# Step 2: market reference
status.info("📊 Calculando referencia de mercado...")
display_nb = barrio.replace("_", " ").title()
market_ref = compute_market_reference(all_properties, barrio)
progress.progress(55)

# Step 3: AI evaluation
evaluator = AIEvaluator()
ai_label = "Claude AI" if evaluator.available else "análisis heurístico"
status.info(f"🤖 Evaluando propiedades con {ai_label}...")
analyses = batch_evaluate(all_properties, market_ref, evaluator, top_n=top_n)
progress.progress(90)

# Step 4: Excel
status.info("📄 Generando Excel...")
from reports.excel import export_excel
ts = datetime.now().strftime("%Y%m%d_%H%M")
excel_path = f"/tmp/flipping_{barrio}_{ts}.xlsx"
export_excel(
    analyses=analyses,
    market_ref=market_ref,
    neighborhood=display_nb,
    total_props=len(all_properties),
    output_path=excel_path,
)
progress.progress(100)
status.empty()
progress.empty()

# ── Results header ────────────────────────────────────────────────────────────
buy_count   = sum(1 for a in analyses if a.flipping_recommendation == "COMPRAR")
watch_count = sum(1 for a in analyses if a.flipping_recommendation == "ANALIZAR MÁS")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Propiedades analizadas", len(all_properties))
col2.metric("Precio mediana", f"USD {market_ref.median_price_per_m2_usd:,.0f}/m²")
col3.metric("Rango precio/m²", f"USD {market_ref.min_price_per_m2_usd:,.0f} – {market_ref.max_price_per_m2_usd:,.0f}")
col4.metric("🟢 Recomendadas comprar", buy_count)
col5.metric("🟡 Para analizar", watch_count)

st.markdown("---")

# Download button
with open(excel_path, "rb") as f:
    excel_bytes = f.read()

col_dl, col_info = st.columns([1, 3])
with col_dl:
    st.download_button(
        label="📥 Descargar Excel",
        data=excel_bytes,
        file_name=f"flipping_{barrio}_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with col_info:
    ai_badge = "🤖 Análisis con Claude AI" if evaluator.available else "📐 Análisis heurístico"
    demo_badge = "🎭 Modo demo" if modo_demo else "🌐 Datos reales"
    st.markdown(f"**Barrio:** {display_nb} &nbsp;|&nbsp; **Fuentes:** {', '.join(fuentes)} &nbsp;|&nbsp; {demo_badge} &nbsp;|&nbsp; {ai_badge}")

st.markdown("---")

# ── Ranking table ─────────────────────────────────────────────────────────────
st.markdown("## 📊 Ranking de Oportunidades")

import pandas as pd

rows = []
for i, a in enumerate(analyses, 1):
    p = a.property
    surface = p.surface_covered or p.surface_total
    rows.append({
        "#": i,
        "Recomendación": a.flipping_recommendation or "—",
        "Score": round(a.flipping_score, 1),
        "Barrio": p.neighborhood,
        "Título": p.title[:55],
        "Precio": p.display_price,
        "m²": f"{surface:.0f}" if surface else "—",
        "USD/m²": f"{p.price_per_m2:,.0f}" if p.price_per_m2 else "—",
        "vs. mercado": f"{a.discount_vs_market_pct:+.1f}%" if a.discount_vs_market_pct is not None else "—",
        "Ganancia est.": f"USD {a.estimated_profit_usd:,.0f}" if a.estimated_profit_usd else "—",
        "ROI": f"{a.roi_pct:.0f}%" if a.roi_pct else "—",
        "Fuente": p.source.value,
    })

df = pd.DataFrame(rows)

def style_rec(val):
    if val == "COMPRAR":     return "background-color:#C6EFCE; color:#276221; font-weight:bold"
    if val == "ANALIZAR MÁS": return "background-color:#FFEB9C; color:#9C6500; font-weight:bold"
    if val == "DESCARTAR":   return "background-color:#FFC7CE; color:#9C0006; font-weight:bold"
    return ""

def style_disc(val):
    try:
        v = float(str(val).replace("%","").replace("+",""))
        if v <= -10: return "color:#276221; font-weight:bold"
        if v >=  10: return "color:#9C0006; font-weight:bold"
    except: pass
    return ""

styled_df = (
    df.style
    .map(style_rec,  subset=["Recomendación"])
    .map(style_disc, subset=["vs. mercado"])
    .set_properties(**{"font-size": "13px"})
    .hide(axis="index")
)
st.dataframe(styled_df, use_container_width=True, height=420)

# ── Property cards ────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"## 🔎 Detalle — Top {min(detalle_n, len(analyses))} propiedades")

for i, a in enumerate(analyses[:detalle_n], 1):
    p = a.property
    surface = p.surface_covered or p.surface_total

    pros_html  = "".join(f'<div class="pro-item">✅ {x}</div>'  for x in a.pros)  or "<div style='color:#999'>Sin datos</div>"
    cons_html  = "".join(f'<div class="con-item">❌ {x}</div>'  for x in a.cons)  or "<div style='color:#999'>Sin datos</div>"
    reno_html  = "".join(f'<div class="reno-item">🔧 {x}</div>' for x in a.renovation_suggestions) or "<div style='color:#999'>Sin datos</div>"

    disc_html  = discount_html(a.discount_vs_market_pct) if a.discount_vs_market_pct is not None else "—"
    profit_str = f"USD {a.estimated_profit_usd:,.0f}" if a.estimated_profit_usd else "—"
    roi_str    = f"{a.roi_pct:.0f}%" if a.roi_pct else "—"
    arv_str    = f"USD {a.estimated_arv_usd:,.0f}" if a.estimated_arv_usd else "—"
    reno_str   = f"USD {a.estimated_renovation_cost_usd:,.0f}" if a.estimated_renovation_cost_usd else "—"
    m2_str     = f"{surface:.0f} m²" if surface else "—"
    ppm2_str   = f"USD {p.price_per_m2:,.0f}/m²" if p.price_per_m2 else "—"
    amenities  = ", ".join(p.amenities) if p.amenities else "—"
    floor_str  = f"Piso {p.floor}/{p.total_floors}" if p.floor else "—"

    card = f"""
    <div class="prop-card">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px">
        <div>
          <span style="font-size:13px; color:#888">#{i}</span>
          <span style="font-size:17px; font-weight:700; margin-left:6px">{p.title[:65]}</span><br>
          <span style="color:#555; font-size:13px">📍 {p.address} &nbsp;·&nbsp; {p.neighborhood} &nbsp;·&nbsp;
            <a href="{p.url}" target="_blank" style="color:#2E5395">Ver aviso ↗</a>
          </span>
        </div>
        <div style="text-align:right">
          {badge_html(a.flipping_recommendation or "—")}
          &nbsp;&nbsp;{score_html(a.flipping_score)}
        </div>
      </div>

      <div class="stat-row" style="margin-top:14px">
        <div class="stat-item"><b>Precio:</b> {p.display_price}</div>
        <div class="stat-item"><b>Superficie:</b> {m2_str}</div>
        <div class="stat-item"><b>Precio/m²:</b> {ppm2_str}</div>
        <div class="stat-item"><b>Descuento:</b> {disc_html}</div>
        <div class="stat-item"><b>ARV:</b> {arv_str}</div>
        <div class="stat-item"><b>Reno. est.:</b> {reno_str}</div>
        <div class="stat-item"><b>Ganancia:</b> {profit_str}</div>
        <div class="stat-item"><b>ROI:</b> {roi_str}</div>
      </div>
      <div class="stat-row">
        <div class="stat-item"><b>Ambientes:</b> {p.rooms or "—"}</div>
        <div class="stat-item"><b>Piso:</b> {floor_str}</div>
        <div class="stat-item"><b>Antigüedad:</b> {f"{p.antiquity_years} años" if p.antiquity_years else "—"}</div>
        <div class="stat-item"><b>Amenities:</b> {amenities}</div>
        <div class="stat-item"><b>Expensas:</b> {f"ARS {p.expenses:,.0f}/mes" if p.expenses else "—"}</div>
        <div class="stat-item"><b>Fuente:</b> {p.source.value}</div>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; margin-top:14px">
        <div>
          <div class="section-title">Ventajas</div>
          {pros_html}
        </div>
        <div>
          <div class="section-title">Desventajas</div>
          {cons_html}
        </div>
        <div>
          <div class="section-title">Renovación sugerida</div>
          {reno_html}
        </div>
      </div>

      {"" if not a.ai_summary else f'<div class="summary-box">💬 <b>Resumen IA:</b> {a.ai_summary}</div>'}
    </div>
    """
    st.markdown(card, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
col_dl2, _ = st.columns([1, 3])
with col_dl2:
    st.download_button(
        label="📥 Descargar Excel completo",
        data=excel_bytes,
        file_name=f"flipping_{barrio}_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_bottom",
        use_container_width=True,
    )
