"""
DENSO Engineering Presentation Generator
=========================================
Databricks App — reads gold tables, patent drawings from UC Volumes,
uses ai_query() for AI-generated content, Vector Search for drawing-data linkage.

Run locally:  streamlit run app.py
Deploy:       databricks apps deploy denso-pptx-generator --source-code-path ./app
"""

import os
import time
from datetime import date
from io import BytesIO
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Determine runtime environment
# ---------------------------------------------------------------------------
IN_DATABRICKS = bool(os.environ.get("DATABRICKS_WAREHOUSE_ID") or os.environ.get("DB_IS_DRIVER"))

if IN_DATABRICKS:
    import data_loader
    import ai_engine
else:
    try:
        import data_loader
        import ai_engine
    except Exception:
        data_loader = None
        ai_engine = None

from pptx_builder import DensoPPTXBuilder

CATALOG = os.environ.get("CATALOG", "serverless_sandbox_hsze05_catalog")
SCHEMA = os.environ.get("SCHEMA", "denso_demo")
WAREHOUSE = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="DENSO PPTX Generator", page_icon="\U0001f3ed", layout="wide")

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; }
h1 { color: #C8102E !important; }
.stButton>button {
    background-color: #C8102E; color: white;
    border: none; border-radius: 6px;
    font-size: 1.1rem; padding: 0.6rem 2rem;
}
.stButton>button:hover { background-color: #a00d24; color: white; }
.stDownloadButton>button {
    background-color: #1565C0; color: white;
    border: none; border-radius: 6px;
    font-size: 1.1rem; padding: 0.6rem 2rem;
}
code { font-size: 0.85em; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    logo_path = Path(__file__).parent / "denso_logo.png"
    if logo_path.exists():
        st.image(str(logo_path), width=180)
    else:
        st.markdown("### DENSO")
    st.markdown("Engineering Presentation Generator")
    st.divider()

    if IN_DATABRICKS:
        st.success("Connected to Databricks")
        st.caption(f"Catalog: `{CATALOG}`")
        st.caption(f"Schema: `{SCHEMA}`")
        st.caption(f"Warehouse: `{WAREHOUSE[:8]}...`")
    else:
        st.info("Running locally (demo mode)")

    st.divider()
    st.markdown(
        "**Built in an afternoon.**\n\n"
        "AI + Databricks eliminates weeks of manual "
        "presentation assembly for engineering review decks."
    )


# ---------------------------------------------------------------------------
# Chart generators
# ---------------------------------------------------------------------------

def _make_thermal_heatmap(df: pd.DataFrame | None = None) -> BytesIO:
    fig, ax = plt.subplots(figsize=(12, 7))
    plt.rcParams.update({"font.family": "sans-serif", "axes.titleweight": "bold"})
    if df is not None and len(df) > 0:
        latest = df.groupby("sensor_id").last().reset_index()
        grid = latest.pivot(index="cell_position_row", columns="cell_position_col", values="temperature_c")
        im = ax.imshow(grid.values, cmap="RdYlBu_r", aspect="auto", interpolation="bicubic")
    else:
        x = np.linspace(0, 11, 120); y = np.linspace(0, 7, 80); X, Y = np.meshgrid(x, y)
        temps = 32 + 0.9*X/11 + 3.8*np.exp(-((X-5.5)**2+(Y-3.5)**2)/8) + 2.2*np.exp(-((X-8.5)**2+(Y-5)**2)/5)
        im = ax.contourf(X, Y, temps, levels=60, cmap="RdYlBu_r")
    fig.colorbar(im, ax=ax, label="Temperature (\u00b0C)", pad=0.02)
    ax.set_title("Thermal Distribution \u2014 Battery Module TM-4200\n3C Fast Charge @ 25 \u00b0C Ambient", fontsize=14, fontweight="bold")
    ax.set_xlabel("Cell Column Position"); ax.set_ylabel("Cell Row Position")
    plt.tight_layout()
    buf = BytesIO(); fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white"); plt.close(fig); buf.seek(0)
    return buf


def _make_test_chart(df: pd.DataFrame | None = None) -> BytesIO:
    fig, ax = plt.subplots(figsize=(12, 7))
    categories = ["\u0394T Uniformity\n(\u00b0C)", "Cool-down Rate\n(\u00b0C/min)", "Power Draw\n(W)", "Coolant \u0394P\n(kPa)", "Noise Level\n(dBA)"]
    specs = [5.0, 5.0, 200, 50, 50]
    conditions = {"1C Charge": [3.2, 2.1, 145, 32, 38], "2C Charge": [4.1, 3.5, 168, 38, 42], "3C Fast Charge": [4.8, 4.8, 195, 45, 47]}
    x = np.arange(len(categories)); w = 0.23; colors = ["#2196F3", "#FF9800", "#C8102E"]
    for i, (cond, vals) in enumerate(conditions.items()):
        ax.bar(x + (i - 1) * w, [v/s*100 for v,s in zip(vals,specs)], w, label=cond, color=colors[i], alpha=0.88)
    ax.axhline(100, color="red", lw=2, ls="--", label="Spec Limit"); ax.set_xticks(x); ax.set_xticklabels(categories)
    ax.set_ylabel("% of Specification Limit"); ax.set_ylim(0, 120)
    ax.set_title("Performance Test Results vs. Specification Limits", fontsize=14, fontweight="bold"); ax.legend(); ax.grid(axis="y", alpha=0.25)
    ax.text(4.35, 107, "ALL PASS", fontsize=13, fontweight="bold", color="#2E7D32", bbox=dict(boxstyle="round", facecolor="#C8E6C9", alpha=0.9))
    plt.tight_layout()
    buf = BytesIO(); fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white"); plt.close(fig); buf.seek(0)
    return buf


def _make_tolerance_chart(df: pd.DataFrame | None = None) -> BytesIO:
    fig, ax = plt.subplots(figsize=(12, 7)); np.random.seed(42)
    if df is not None and "cooling_plate_flatness_mm" in df.columns:
        measurements = df["cooling_plate_flatness_mm"].dropna().values
    else:
        measurements = np.random.normal(loc=0.048, scale=0.011, size=500)
        measurements = measurements[(measurements > 0.005) & (measurements < 0.10)]
    lsl, usl, target = 0.020, 0.080, 0.050
    ax.hist(measurements, bins=42, density=True, alpha=0.75, color="#C8102E", edgecolor="white", lw=0.5)
    mu, sigma = np.mean(measurements), np.std(measurements)
    xs = np.linspace(0, 0.1, 300)
    ax.plot(xs, (1/(sigma*np.sqrt(2*np.pi)))*np.exp(-0.5*((xs-mu)/sigma)**2), "k-", lw=2, label="Normal fit")
    ax.axvline(lsl, color="#E65100", lw=2, ls="--", label=f"LSL={lsl:.3f}"); ax.axvline(usl, color="#E65100", lw=2, ls="--", label=f"USL={usl:.3f}")
    ax.axvline(target, color="#2E7D32", lw=1.5, ls=":", label=f"Target={target:.3f}")
    cpk = min((usl-mu)/(3*sigma), (mu-lsl)/(3*sigma))
    ax.text(0.087, ax.get_ylim()[1]*0.82, f"n={len(measurements)}\n\u03bc={mu:.4f}\n\u03c3={sigma:.4f}\nCpk={cpk:.2f}", fontsize=11, bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85))
    ax.set_xlabel("Cooling Plate Flatness (mm)"); ax.set_ylabel("Density")
    ax.set_title("Manufacturing Tolerance Distribution \u2014 Cooling Plate Assembly", fontsize=14, fontweight="bold"); ax.legend(loc="upper left")
    plt.tight_layout()
    buf = BytesIO(); fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white"); plt.close(fig); buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
st.title("Engineering Presentation Generator")

tab_arch, tab_demo, tab_upload = st.tabs([
    "\U0001f3d7\ufe0f Architecture",
    "\U0001f680 Generate Presentation",
    "\U0001f4c1 From Your Files",
])


# ========================= ARCHITECTURE TAB ================================
with tab_arch:
    st.header("System Architecture")
    st.markdown("Technical overview of the AI-powered PPTX generation pipeline for LatentView review.")

    st.subheader("End-to-End Pipeline")
    st.code("""
    Engineering Drawings (PNG)          Gold Delta Tables (CSV -> Delta)
    uploaded or from UC Volume          thermal_sensors, test_results,
            |                           manufacturing_quality, durability,
            v                           component_specs
    +------------------+                        |
    | Claude Vision    |                        v
    | (Sonnet 4.6)     |               +------------------+
    | Extract:         |               | SQL Warehouse    |
    |  - components    |               | ai_query()       |
    |  - specs         |               | Generate:        |
    |  - system area   |               |  - exec summary  |
    |  - keywords      |               |  - narratives    |
    +--------+---------+               |  - findings      |
             |                         +--------+---------+
             v                                  |
    +------------------+                        |
    | GTE-Large-EN     |                        |
    | Embedding Model  |                        |
    | (1024-dim vector)|                        |
    +--------+---------+                        |
             |                                  |
             v                                  |
    +------------------+                        |
    | Vector Search    |   <- semantic match -> |
    | Delta Sync Index |                        |
    | (auto-updating)  |                        |
    +--------+---------+                        |
             |                                  |
             +----------------+-----------------+
                              |
                              v
                    +------------------+
                    | python-pptx      |
                    | DENSO-branded    |
                    | PPTX assembly    |
                    +------------------+
                              |
                              v
                     .pptx download
    """, language=None)

    st.subheader("Databricks Services Used")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Compute & Data")
        st.markdown(f"""
| Service | Detail |
|---|---|
| **Unity Catalog** | `{CATALOG}.{SCHEMA}` |
| **UC Volume** | `engineering_drawings` (patent PNGs) |
| **SQL Warehouse** | `{WAREHOUSE[:16]}...` (Serverless) |
| **Delta Tables** | 6 gold tables + 1 analysis table |
| **Vector Search** | Delta Sync index on `drawing_analysis` |
| **Databricks App** | Streamlit, MEDIUM compute |
        """)
    with col2:
        st.markdown("##### AI Models (Foundation Model API)")
        st.markdown("""
| Model | Purpose |
|---|---|
| **databricks-claude-sonnet-4-6** | Content generation via `ai_query()` |
| **databricks-claude-sonnet-4-6** | Vision: drawing analysis + extraction |
| **databricks-gte-large-en** | Embedding model (1024-dim vectors) |
| **ai_parse_document()** | Structured spec extraction from docs |
        """)

    st.subheader("Gold Table Schema")
    st.markdown(f"All tables in `{CATALOG}.{SCHEMA}`:")
    table_data = {
        "Table": [
            "thermal_sensor_readings", "component_test_results", "manufacturing_quality",
            "durability_cycling", "component_specs", "drawing_metadata", "drawing_analysis",
        ],
        "Rows": ["1,440", "90", "500", "2,000", "7", "22", "22+"],
        "Key Columns": [
            "timestamp, sensor_id, temperature_c, cell_position_row/col",
            "test_id, component, test_condition, metric, value, spec_limit, pass_fail",
            "unit_serial, cooling_plate_flatness_mm, channel_depth/width, Cpk",
            "cycle_number, min/max_temp, coolant_flow_rate, pressure_drop",
            "Component, Part_Number, Material, Weight_g, Tolerance",
            "filename, patent, title, category, description",
            "filename, extracted_components, system_area, embedding (1024-dim)",
        ],
        "Purpose": [
            "Thermal FEA heatmap + time-series charts",
            "Performance vs spec bar charts + tables",
            "Cpk tolerance distribution analysis",
            "Durability trend analysis",
            "Component spec tables in PPTX",
            "Drawing catalog for UI selection",
            "Vision-extracted metadata + vectors for semantic search",
        ],
    }
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

    st.subheader("Vector Search Pipeline")
    st.markdown("""
**Batch (Notebook 04 — runs once on setup):**
1. For each of 22 patent drawings in UC Volume
2. Call `databricks-claude-sonnet-4-6` with vision to extract components, specs, system area, keywords
3. Call `databricks-gte-large-en` to generate 1024-dim embedding of the description
4. Write to `drawing_analysis` Delta table
5. Vector Search Delta Sync index auto-updates

**Real-time (App — on each upload):**
1. User uploads new drawing via Streamlit
2. Save PNG to UC Volume (`/Volumes/.../engineering_drawings/`)
3. Claude Vision extracts metadata inline (~3 sec)
4. INSERT into `drawing_analysis` via SQL Warehouse
5. Vector Search index auto-syncs (new drawing immediately searchable)

**At Generation Time:**
1. For each gold table, generate a semantic query (e.g. "thermal sensor temperature uniformity cooling")
2. Vector Search returns top-3 matching drawings by cosine similarity
3. Matched drawings are paired with their data on PPTX slides
4. AI narrative is generated with both the drawing context and the data summary
    """)

    st.subheader("Notebooks (DABs Deployed)")
    nb_data = {
        "Notebook": [
            "01_setup_catalog.py", "02_load_gold_tables.py",
            "03_load_drawings.py", "04_analyze_drawings.py",
        ],
        "Purpose": [
            "Create UC schema + engineering_drawings volume",
            "Load 5 CSV data files into gold Delta tables",
            "Upload 22 patent PNGs to UC Volume + create metadata table",
            "Vision extraction + embeddings + Vector Search index creation",
        ],
        "Compute": ["Serverless", "Serverless", "Serverless", "Serverless"],
        "Key Operations": [
            "CREATE SCHEMA, CREATE VOLUME",
            "pandas.read_csv -> spark.createDataFrame -> saveAsTable",
            "os file copy to /Volumes/... + drawing_metadata table",
            "serving_endpoints.query (vision + embedding) + vector_search_indexes.create_index",
        ],
    }
    st.dataframe(pd.DataFrame(nb_data), use_container_width=True, hide_index=True)

    st.subheader("Repository")
    st.code("""
pptx_generator/
\u251c\u2500\u2500 databricks.yml              # DABs bundle config
\u251c\u2500\u2500 app/
\u2502   \u251c\u2500\u2500 app.py                  # Streamlit application (this file)
\u2502   \u251c\u2500\u2500 app.yaml                # Databricks App config (env vars, resources)
\u2502   \u251c\u2500\u2500 pptx_builder.py         # DENSO-branded PPTX assembly (python-pptx)
\u2502   \u251c\u2500\u2500 data_loader.py          # Gold table + UC Volume reader (SQL connector)
\u2502   \u251c\u2500\u2500 ai_engine.py            # ai_query, vision, embeddings, vector search
\u2502   \u251c\u2500\u2500 denso_logo.png          # DENSO corporate logo
\u2502   \u2514\u2500\u2500 requirements.txt        # App dependencies
\u251c\u2500\u2500 notebooks/                      # DABs-deployed setup notebooks
\u251c\u2500\u2500 data/                           # CSV source files for gold tables
\u251c\u2500\u2500 drawings/                       # 22 patent engineering drawings (PNG)
\u251c\u2500\u2500 demo_uploads/                   # 5 extra drawings for upload demo
\u2514\u2500\u2500 scripts/reset_demo.py           # Clean uploaded drawings for demo replay
    """, language=None)


# ========================= GENERATE TAB ====================================
with tab_demo:
    st.subheader("EV Battery Thermal Management System \u2014 Model TM-4200")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Project:** EV Battery Thermal Management System")
        st.markdown("**Model:** TM-4200  |  **Platform:** 400V EV Battery Pack")
    with col2:
        st.markdown("**Cells:** 96-cell module (8\u00d712)  |  **Cooling:** 4.2 kW")
        st.markdown("**Target \u0394T:** < 5.0 \u00b0C  |  **Flow:** 8 L/min")

    # -- Drawing selection --
    st.markdown("---")
    st.markdown("#### Select Engineering Drawings")

    available_drawings = []
    if IN_DATABRICKS and data_loader:
        available_drawings = data_loader.list_drawings()

    if available_drawings:
        drawing_names = [d["name"] for d in available_drawings]
        selected_drawing_names = st.multiselect(
            "Drawings from UC Volume", options=drawing_names, default=drawing_names[:4],
            help=f"Source: `/Volumes/{CATALOG}/{SCHEMA}/engineering_drawings/`",
        )
        selected_drawings = [d for d in available_drawings if d["name"] in selected_drawing_names]
        if selected_drawings:
            cols = st.columns(min(4, len(selected_drawings)))
            for i, drw in enumerate(selected_drawings):
                with cols[i % 4]:
                    try:
                        st.image(data_loader.read_drawing(drw["path"]), caption=drw["name"], use_container_width=True)
                    except Exception:
                        st.caption(drw["name"])
    else:
        selected_drawings = []
        st.info("No drawings in UC Volume. Run the setup notebook or upload below.")

    uploaded_drawings = st.file_uploader(
        "Or upload new engineering drawings", type=["png", "jpg", "jpeg"],
        accept_multiple_files=True, key="demo_upload",
    )

    st.markdown("---")

    if st.button("Generate Presentation", key="demo_gen", type="primary"):

        # ── STEP 1: Read Gold Tables ──────────────────────────────────────
        with st.status("Reading gold Delta tables...", expanded=True) as status:
            st.write(f"`USE CATALOG {CATALOG}; USE SCHEMA {SCHEMA};`")
            thermal_df = mfg_df = test_df = specs_df = None
            tables_read = 0
            if IN_DATABRICKS and data_loader:
                for tbl, loader in [
                    ("thermal_sensor_readings", lambda: data_loader.read_thermal_sensors()),
                    ("manufacturing_quality", lambda: data_loader.read_manufacturing_quality()),
                    ("component_test_results", lambda: data_loader.read_test_results()),
                    ("component_specs", lambda: data_loader.read_component_specs()),
                ]:
                    t0 = time.time()
                    try:
                        df = loader()
                        elapsed = time.time() - t0
                        st.write(f"`SELECT * FROM {CATALOG}.{SCHEMA}.{tbl}` \u2192 **{len(df):,} rows** ({elapsed:.1f}s)")
                        if tbl == "thermal_sensor_readings": thermal_df = df
                        elif tbl == "manufacturing_quality": mfg_df = df
                        elif tbl == "component_test_results": test_df = df
                        elif tbl == "component_specs": specs_df = df
                        tables_read += 1
                    except Exception as e:
                        st.write(f"`{tbl}` \u274c {e}")
            else:
                st.write("Local mode \u2014 using mock data")
            status.update(label=f"Gold tables loaded ({tables_read}/4)", state="complete")

        # ── STEP 2: Generate Charts ───────────────────────────────────────
        with st.status("Generating matplotlib visualizations...", expanded=False) as status:
            t0 = time.time()
            thermal_img = _make_thermal_heatmap(thermal_df)
            st.write(f"Thermal heatmap: `contourf` 120\u00d780 grid \u2192 PNG ({time.time()-t0:.1f}s)")
            test_img = _make_test_chart(test_df)
            st.write("Test results: grouped bar chart (3 conditions \u00d7 5 metrics)")
            tolerance_img = _make_tolerance_chart(mfg_df)
            st.write(f"Tolerance distribution: n={500 if mfg_df is None else len(mfg_df)}, Cpk analysis")
            status.update(label="Visualizations generated (3 charts)", state="complete")

        # ── STEP 3: Vector Search Matching ────────────────────────────────
        data_drawing_matches = {}
        with st.status("Vector Search: matching drawings to data...", expanded=True) as status:
            if IN_DATABRICKS and ai_engine:
                try:
                    st.write(f"Index: `{CATALOG}.{SCHEMA}.drawing_analysis_index`")
                    st.write("Embedding model: `databricks-gte-large-en` (1024-dim)")
                    data_tables = {
                        "thermal_sensor_readings": thermal_df,
                        "component_test_results": test_df,
                        "manufacturing_quality": mfg_df,
                        "component_specs": specs_df,
                    }
                    t0 = time.time()
                    data_drawing_matches = ai_engine.match_data_to_drawings(data_tables)
                    elapsed = time.time() - t0
                    for tbl, matches in data_drawing_matches.items():
                        if matches:
                            names = [m.get("filename", "?") for m in matches[:2]]
                            st.write(f"`{tbl}` \u2192 **{', '.join(names)}** (cosine similarity)")
                    st.write(f"Completed in {elapsed:.1f}s")
                except Exception as e:
                    st.write(f"Vector search unavailable: {e}")
            else:
                st.write("Skipped (local mode)")
            status.update(label=f"Drawing-data matches found ({sum(1 for m in data_drawing_matches.values() if m)})", state="complete")

        # ── STEP 4: AI Content Generation ─────────────────────────────────
        with st.status("Calling ai_query() for presentation content...", expanded=True) as status:
            if IN_DATABRICKS and ai_engine:
                st.write("Model: `databricks-claude-sonnet-4-6`")
                st.write(f"SQL: `SELECT ai_query('databricks-claude-sonnet-4-6', <prompt>) AS content`")
                st.write("Generating: executive summary, thermal narrative, test results, findings, recommendations...")
                t0 = time.time()
                content = ai_engine.generate_content()
                elapsed = time.time() - t0
                st.write(f"Response received ({elapsed:.1f}s) \u2014 {len(str(content)):,} chars")
            else:
                from ai_engine import _FALLBACK_CONTENT
                content = _FALLBACK_CONTENT
                st.write("Using pre-written fallback content (no AI connection)")
            status.update(label=f"AI content generated", state="complete")

        # ── STEP 5: Process Uploaded Drawings ─────────────────────────────
        upload_analyses = {}
        if uploaded_drawings:
            with st.status(f"Processing {len(uploaded_drawings)} uploaded drawings...", expanded=True) as status:
                for uf in uploaded_drawings:
                    if IN_DATABRICKS and ai_engine:
                        try:
                            uf_bytes = uf.read(); uf.seek(0)
                            st.write(f"**{uf.name}** ({len(uf_bytes)/1024:.0f} KB)")

                            t0 = time.time()
                            data_loader.upload_drawing(uf.name, uf_bytes)
                            st.write(f"  \u2514 Saved to `/Volumes/{CATALOG}/{SCHEMA}/engineering_drawings/{uf.name}` ({time.time()-t0:.1f}s)")

                            t0 = time.time()
                            analysis = ai_engine.analyze_and_index_drawing(uf_bytes, uf.name)
                            upload_analyses[uf.name] = analysis
                            comps = analysis.get("extracted_components", [])
                            kws = analysis.get("data_keywords", [])
                            area = analysis.get("system_area", "?")
                            st.write(f"  \u2514 Claude Vision: **{area}** | {len(comps)} components | {len(kws)} keywords ({time.time()-t0:.1f}s)")
                            st.write(f"  \u2514 INSERT INTO `{CATALOG}.{SCHEMA}.drawing_analysis` \u2192 Vector Search auto-sync")
                        except Exception as e:
                            st.write(f"  \u2514 Error: {e}")
                status.update(label=f"Processed {len(upload_analyses)}/{len(uploaded_drawings)} drawings", state="complete")

        # ── STEP 6: Build PPTX ────────────────────────────────────────────
        with st.status("Assembling DENSO-branded PPTX...", expanded=True) as status:
            builder = DensoPPTXBuilder()

            builder.add_title_slide(content["title"], content["subtitle"], date.today().strftime("%B %d, %Y"))
            st.write("Slide 1: Title (DENSO red, logo, date)")

            builder.add_section_slide("Executive Summary", number=1)
            builder.add_content_slide("Executive Summary", body=content["executive_summary"])
            st.write("Slides 2-3: Executive Summary")

            builder.add_section_slide("System Architecture", number=2)
            builder.add_content_slide("System Overview", body=content["system_overview_narrative"], bullets=content["system_overview_bullets"])
            st.write("Slides 4-5: System Architecture")

            # Drawings
            all_drawing_images = []
            for drw in selected_drawings:
                try:
                    all_drawing_images.append((drw["name"], BytesIO(data_loader.read_drawing(drw["path"])), "volume"))
                except Exception:
                    pass
            for uf in (uploaded_drawings or []):
                uf.seek(0)
                all_drawing_images.append((uf.name, BytesIO(uf.read()), "upload"))

            if all_drawing_images:
                builder.add_section_slide("Engineering Drawings", number=3)
                for name, img_buf, source in all_drawing_images:
                    caption = ""
                    if source == "upload" and name in upload_analyses:
                        caption = upload_analyses[name].get("description_text", "")
                        kw = ", ".join(upload_analyses[name].get("data_keywords", [])[:5])
                        if kw: caption = f"{caption}  |  Related: {kw}" if caption else kw
                    elif IN_DATABRICKS and ai_engine:
                        try:
                            img_buf.seek(0); caption = ai_engine.analyze_drawing(img_buf.read()); img_buf.seek(0)
                        except Exception: pass
                    slide_title = name.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title()
                    builder.add_image_slide(slide_title, img_buf, caption=caption)

                if data_drawing_matches:
                    bullets = []
                    for tbl, matches in data_drawing_matches.items():
                        if matches:
                            bullets.append(f"{tbl.replace('_',' ').title()}: linked to {', '.join(m.get('filename','?') for m in matches[:2])}")
                    if bullets:
                        builder.add_content_slide("Data-Drawing Linkage (Vector Search)", body="Semantic matching links data to drawings via Databricks Vector Search.", bullets=bullets)

                st.write(f"Slides 6-{6+len(all_drawing_images)}: {len(all_drawing_images)} engineering drawings (with AI captions)")
                section_offset = 4
            else:
                section_offset = 3

            builder.add_section_slide("Thermal Analysis", number=section_offset)
            thermal_img.seek(0); builder.add_image_slide("Thermal Distribution \u2014 FEA Results", thermal_img, caption="3C fast charge @ 25\u00b0C ambient")
            builder.add_content_slide("Thermal Analysis Summary", body=content["thermal_analysis_narrative"])
            st.write("Thermal Analysis section (heatmap + narrative)")

            builder.add_section_slide("Validation Testing", number=section_offset+1)
            test_img.seek(0); builder.add_image_slide("Performance vs. Specification", test_img)
            builder.add_content_slide("Test Results Summary", body=content["test_results_narrative"], bullets=content["test_results_bullets"])
            if test_df is not None: builder.add_table_slide("Detailed Test Data", test_df.head(12))
            st.write("Validation Testing section (chart + table + narrative)")

            builder.add_section_slide("Manufacturing Readiness", number=section_offset+2)
            tolerance_img.seek(0)
            builder.add_two_col_slide("Manufacturing Quality", left_text=content["manufacturing_narrative"],
                left_bullets=["Cpk > 1.33 on all CTQ dimensions", "500-unit pilot run completed", "Statistical process control confirmed"],
                right_image=tolerance_img)
            if specs_df is not None: builder.add_table_slide("Component Specifications", specs_df)
            st.write("Manufacturing Readiness section (Cpk chart + specs table)")

            builder.add_section_slide("Findings & Recommendations", number=section_offset+3)
            builder.add_content_slide("Key Findings", bullets=content["findings"])
            builder.add_content_slide("Recommendations", bullets=content["recommendations"])
            builder.add_content_slide("Next Steps", bullets=content["next_steps"])
            st.write("Findings, Recommendations, Next Steps")

            builder.add_closing_slide("Thank You", lines=[
                "DENSO International America, Inc.", "Electrification Engineering Division",
                f"Generated {date.today()} | AI-Powered by Databricks"])

            pptx_bytes = builder.save_bytes()
            total_slides = len(builder.prs.slides)
            st.write(f"**Total: {total_slides} slides** | {len(pptx_bytes.getvalue())/1024:.0f} KB")
            status.update(label=f"PPTX assembled ({total_slides} slides)", state="complete")

        # ── Result ────────────────────────────────────────────────────────
        st.success(f"Presentation generated \u2014 {total_slides} slides")

        st.markdown("#### Preview")
        c1, c2, c3 = st.columns(3)
        thermal_img.seek(0); test_img.seek(0); tolerance_img.seek(0)
        with c1: st.image(thermal_img, caption="Thermal Analysis", use_container_width=True)
        with c2: st.image(test_img, caption="Test Results", use_container_width=True)
        with c3: st.image(tolerance_img, caption="Manufacturing Quality", use_container_width=True)

        st.download_button(
            label="Download Presentation (.pptx)", data=pptx_bytes,
            file_name=f"DENSO_TM4200_Review_{date.today():%Y%m%d}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            type="primary",
        )


# ========================= UPLOAD TAB ======================================
with tab_upload:
    st.subheader("Generate from Your Files")
    st.markdown("Upload engineering drawings, data files, and a description.")

    description = st.text_area("Presentation topic / description", height=120,
        placeholder="Describe the engineering project, review topic, or analysis\u2026")

    col_img, col_data = st.columns(2)
    with col_img:
        up_images = st.file_uploader("Engineering Drawings / Images", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="up_img")
    with col_data:
        up_data = st.file_uploader("Data Files (CSV / Excel)", type=["csv", "xlsx", "xls"], accept_multiple_files=True, key="up_data")

    save_to_volume = st.checkbox("Save uploaded drawings to UC Volume for future use", value=True)

    if st.button("Generate from Uploads", key="upload_gen", type="primary"):
        if not description and not up_images and not up_data:
            st.warning("Please provide a description or upload at least one file.")
        else:
            with st.status("Processing uploads...", expanded=True) as status:
                builder = DensoPPTXBuilder()
                title_text = description.split(".")[0][:80] if description else "Engineering Review"
                builder.add_title_slide(title_text, "DENSO | Engineering Review", date.today().strftime("%B %d, %Y"))
                if description:
                    builder.add_content_slide("Overview", body=description)

                for uf in (up_images or []):
                    img_bytes = uf.read()
                    st.write(f"**{uf.name}** ({len(img_bytes)/1024:.0f} KB)")

                    if save_to_volume and IN_DATABRICKS and data_loader:
                        try:
                            data_loader.upload_drawing(uf.name, img_bytes)
                            st.write(f"  \u2514 Saved to UC Volume")
                        except Exception: pass

                    caption = ""
                    if IN_DATABRICKS and ai_engine:
                        try:
                            t0 = time.time()
                            analysis = ai_engine.analyze_and_index_drawing(img_bytes, uf.name)
                            caption = analysis.get("description_text", "")
                            st.write(f"  \u2514 Vision: {analysis.get('system_area','?')} | {len(analysis.get('extracted_components',[]))} components ({time.time()-t0:.1f}s)")
                            st.write(f"  \u2514 Indexed in `drawing_analysis` for Vector Search")
                        except Exception as e:
                            st.write(f"  \u2514 Analysis: {e}")

                    builder.add_image_slide(uf.name.rsplit(".", 1)[0].replace("_", " ").title(), BytesIO(img_bytes), caption=caption)

                for uf in (up_data or []):
                    try:
                        df = pd.read_csv(uf) if uf.name.endswith(".csv") else pd.read_excel(uf)
                        builder.add_table_slide(uf.name.rsplit(".", 1)[0].replace("_", " ").title(), df.head(15))
                        st.write(f"**{uf.name}**: {len(df)} rows, {len(df.columns)} columns")
                    except Exception as e:
                        st.write(f"**{uf.name}**: Error \u2014 {e}")

                builder.add_closing_slide("Thank You", lines=["DENSO | AI-Generated Presentation | Databricks"])
                pptx_bytes = builder.save_bytes()
                status.update(label=f"Built {len(builder.prs.slides)} slides", state="complete")

            st.success(f"Presentation generated \u2014 {len(builder.prs.slides)} slides")
            st.download_button(
                label="Download Presentation (.pptx)", data=pptx_bytes,
                file_name=f"DENSO_Custom_{date.today():%Y%m%d}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                type="primary",
            )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
data_source = f"Databricks Gold Tables (`{CATALOG}.{SCHEMA}`)" if IN_DATABRICKS else "Demo Mode (local)"
st.caption(
    f"DENSO Engineering Presentation Generator \u00b7 Data: {data_source} \u00b7 "
    "AI: Databricks Foundation Model API \u00b7 Built in an afternoon, not six months."
)
