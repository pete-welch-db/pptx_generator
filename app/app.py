"""
DENSO Engineering Presentation Generator
=========================================
Databricks App — reads gold tables, patent drawings from UC Volumes,
uses ai_query() for AI-generated content.

Run locally:  streamlit run app.py
Deploy:       databricks apps deploy denso-pptx-generator --source-code-path ./app
"""

import os
import tempfile
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
    # Local dev — graceful fallback
    try:
        import data_loader
        import ai_engine
    except Exception:
        data_loader = None
        ai_engine = None

from pptx_builder import DensoPPTXBuilder

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
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### DENSO")
    st.markdown("Engineering Presentation Generator")
    st.divider()

    if IN_DATABRICKS:
        st.success("Connected to Databricks")
        catalog = os.environ.get("CATALOG", "main")
        schema = os.environ.get("SCHEMA", "denso_demo")
        st.caption(f"Catalog: `{catalog}` / Schema: `{schema}`")
    else:
        st.info("Running locally (demo mode)")

    st.divider()
    st.markdown(
        "**Built in an afternoon.**\n\n"
        "AI + Databricks eliminates weeks of manual "
        "presentation assembly for engineering review decks."
    )

# ---------------------------------------------------------------------------
# Chart generators (from gold table data or mock)
# ---------------------------------------------------------------------------

def _make_thermal_heatmap(df: pd.DataFrame | None = None) -> BytesIO:
    """Generate thermal heatmap from sensor data or mock."""
    fig, ax = plt.subplots(figsize=(12, 7))
    plt.rcParams.update({"font.family": "sans-serif", "axes.titleweight": "bold"})

    if df is not None and len(df) > 0:
        # Pivot real sensor data to grid (use last timestamp)
        latest = df.groupby("sensor_id").last().reset_index()
        rows = sorted(latest["cell_position_row"].unique())
        cols = sorted(latest["cell_position_col"].unique())
        grid = latest.pivot(index="cell_position_row", columns="cell_position_col", values="temperature_c")
        im = ax.imshow(grid.values, cmap="RdYlBu_r", aspect="auto", interpolation="bicubic")
    else:
        x = np.linspace(0, 11, 120)
        y = np.linspace(0, 7, 80)
        X, Y = np.meshgrid(x, y)
        temps = 32 + 0.9*X/11 + 3.8*np.exp(-((X-5.5)**2+(Y-3.5)**2)/8) + 2.2*np.exp(-((X-8.5)**2+(Y-5)**2)/5)
        im = ax.contourf(X, Y, temps, levels=60, cmap="RdYlBu_r")

    fig.colorbar(im, ax=ax, label="Temperature (\u00b0C)", pad=0.02)
    ax.set_title("Thermal Distribution \u2014 Battery Module TM-4200\n3C Fast Charge @ 25 \u00b0C Ambient", fontsize=14, fontweight="bold")
    ax.set_xlabel("Cell Column Position")
    ax.set_ylabel("Cell Row Position")
    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _make_test_chart(df: pd.DataFrame | None = None) -> BytesIO:
    """Performance vs spec grouped bar chart."""
    fig, ax = plt.subplots(figsize=(12, 7))

    categories = ["\u0394T Uniformity\n(\u00b0C)", "Cool-down Rate\n(\u00b0C/min)", "Power Draw\n(W)", "Coolant \u0394P\n(kPa)", "Noise Level\n(dBA)"]
    specs = [5.0, 5.0, 200, 50, 50]
    conditions = {"1C Charge": [3.2, 2.1, 145, 32, 38], "2C Charge": [4.1, 3.5, 168, 38, 42], "3C Fast Charge": [4.8, 4.8, 195, 45, 47]}

    x = np.arange(len(categories))
    w = 0.23
    colors = ["#2196F3", "#FF9800", "#C8102E"]
    for i, (cond, vals) in enumerate(conditions.items()):
        pct = [v / s * 100 for v, s in zip(vals, specs)]
        ax.bar(x + (i - 1) * w, pct, w, label=cond, color=colors[i], alpha=0.88)

    ax.axhline(100, color="red", lw=2, ls="--", label="Spec Limit (100 %)")
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylabel("% of Specification Limit")
    ax.set_ylim(0, 120)
    ax.set_title("Performance Test Results vs. Specification Limits", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.25)
    ax.text(4.35, 107, "ALL PASS", fontsize=13, fontweight="bold", color="#2E7D32", bbox=dict(boxstyle="round", facecolor="#C8E6C9", alpha=0.9))
    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _make_tolerance_chart(df: pd.DataFrame | None = None) -> BytesIO:
    """Manufacturing Cpk distribution chart."""
    fig, ax = plt.subplots(figsize=(12, 7))
    np.random.seed(42)

    if df is not None and "cooling_plate_flatness_mm" in df.columns:
        measurements = df["cooling_plate_flatness_mm"].dropna().values
    else:
        measurements = np.random.normal(loc=0.048, scale=0.011, size=500)
        measurements = measurements[(measurements > 0.005) & (measurements < 0.10)]

    lsl, usl, target = 0.020, 0.080, 0.050
    ax.hist(measurements, bins=42, density=True, alpha=0.75, color="#C8102E", edgecolor="white", lw=0.5)

    mu, sigma = np.mean(measurements), np.std(measurements)
    xs = np.linspace(0, 0.1, 300)
    pdf = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((xs - mu) / sigma) ** 2)
    ax.plot(xs, pdf, "k-", lw=2, label="Normal fit")

    ax.axvline(lsl, color="#E65100", lw=2, ls="--", label=f"LSL = {lsl:.3f} mm")
    ax.axvline(usl, color="#E65100", lw=2, ls="--", label=f"USL = {usl:.3f} mm")
    ax.axvline(target, color="#2E7D32", lw=1.5, ls=":", label=f"Target = {target:.3f} mm")

    cpk = min((usl - mu) / (3 * sigma), (mu - lsl) / (3 * sigma))
    ax.text(0.087, ax.get_ylim()[1] * 0.82, f"n = {len(measurements)}\n\u03bc = {mu:.4f} mm\n\u03c3 = {sigma:.4f} mm\nCpk = {cpk:.2f}", fontsize=11, bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85))

    ax.set_xlabel("Cooling Plate Flatness (mm)")
    ax.set_ylabel("Density")
    ax.set_title("Manufacturing Tolerance Distribution \u2014 Cooling Plate Assembly", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10, loc="upper left")
    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
st.title("Engineering Presentation Generator")
st.markdown(
    "Select engineering drawings from the **UC Volume**, upload your own, "
    "and generate a DENSO-branded PowerPoint in seconds."
)

tab_demo, tab_upload = st.tabs(["\U0001f680 Quick Demo", "\U0001f4c1 From Your Files"])

# ========================= QUICK DEMO TAB =================================
with tab_demo:
    st.subheader("Demo: EV Battery Thermal Management System")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Project:** EV Battery Thermal Management System")
        st.markdown("**Model:** TM-4200  |  **Platform:** 400V EV Battery Pack")
    with col2:
        st.markdown("**Cells:** 96-cell module (8x12)  |  **Cooling:** 4.2 kW")
        st.markdown("**Target \u0394T:** < 5.0 \u00b0C  |  **Flow:** 8 L/min")

    # -- Drawing selection from volume --
    st.markdown("---")
    st.markdown("#### Select Engineering Drawings")

    available_drawings = []
    if IN_DATABRICKS and data_loader:
        available_drawings = data_loader.list_drawings()

    if available_drawings:
        drawing_names = [d["name"] for d in available_drawings]
        selected_drawing_names = st.multiselect(
            "Select drawings from UC Volume to include in the presentation",
            options=drawing_names,
            default=drawing_names[:4],
            help="These patent drawings are stored in a Unity Catalog Volume",
        )
        selected_drawings = [d for d in available_drawings if d["name"] in selected_drawing_names]

        # Preview thumbnails
        if selected_drawings:
            cols = st.columns(min(4, len(selected_drawings)))
            for i, drw in enumerate(selected_drawings):
                with cols[i % 4]:
                    try:
                        img_bytes = data_loader.read_drawing(drw["path"])
                        st.image(img_bytes, caption=drw["name"], use_container_width=True)
                    except Exception:
                        st.caption(drw["name"])
    else:
        selected_drawings = []
        st.info(
            "No drawings found in UC Volume. "
            "Run the setup notebook to load patent drawings, or upload below."
        )

    # Upload additional drawings
    uploaded_drawings = st.file_uploader(
        "Or upload your own engineering drawings",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="demo_upload",
    )

    st.markdown("---")

    if st.button("Generate Presentation", key="demo_gen", type="primary"):
        with st.spinner("Building your presentation\u2026"):
            progress = st.progress(0, text="Reading gold tables\u2026")

            # 1 — Read data
            thermal_df = mfg_df = test_df = specs_df = None
            if IN_DATABRICKS and data_loader:
                try:
                    thermal_df = data_loader.read_thermal_sensors()
                    mfg_df = data_loader.read_manufacturing_quality()
                    test_df = data_loader.read_test_results()
                    specs_df = data_loader.read_component_specs()
                except Exception as e:
                    st.warning(f"Could not read gold tables: {e}")

            progress.progress(20, text="Generating visualizations\u2026")

            # 2 — Generate charts
            thermal_img = _make_thermal_heatmap(thermal_df)
            test_img = _make_test_chart(test_df)
            tolerance_img = _make_tolerance_chart(mfg_df)

            progress.progress(40, text="Generating AI content\u2026")

            # 3 — AI content
            if IN_DATABRICKS and ai_engine:
                content = ai_engine.generate_content()
            else:
                from ai_engine import _FALLBACK_CONTENT
                content = _FALLBACK_CONTENT

            progress.progress(65, text="Building PPTX\u2026")

            # 4 — Build deck
            builder = DensoPPTXBuilder()

            builder.add_title_slide(
                content["title"],
                content["subtitle"],
                date.today().strftime("%B %d, %Y"),
            )

            builder.add_section_slide("Executive Summary", number=1)
            builder.add_content_slide("Executive Summary", body=content["executive_summary"])

            builder.add_section_slide("System Architecture", number=2)
            builder.add_content_slide(
                "System Overview",
                body=content["system_overview_narrative"],
                bullets=content["system_overview_bullets"],
            )

            # Engineering drawings from volume + uploads
            all_drawing_images = []
            for drw in selected_drawings:
                try:
                    img_bytes = data_loader.read_drawing(drw["path"])
                    all_drawing_images.append((drw["name"], BytesIO(img_bytes)))
                except Exception:
                    pass

            for uf in (uploaded_drawings or []):
                all_drawing_images.append((uf.name, BytesIO(uf.read())))

            if all_drawing_images:
                builder.add_section_slide("Engineering Drawings", number=3)
                for name, img_buf in all_drawing_images:
                    caption = ""
                    if IN_DATABRICKS and ai_engine:
                        try:
                            img_buf.seek(0)
                            caption = ai_engine.analyze_drawing(img_buf.read())
                            img_buf.seek(0)
                        except Exception:
                            pass
                    title = name.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title()
                    builder.add_image_slide(title, img_buf, caption=caption)
                section_offset = 4
            else:
                section_offset = 3

            builder.add_section_slide("Thermal Analysis", number=section_offset)
            thermal_img.seek(0)
            builder.add_image_slide(
                "Thermal Distribution \u2014 FEA Results",
                thermal_img,
                caption="Simulated thermal distribution under 3C fast charge at 25 \u00b0C ambient",
            )
            builder.add_content_slide("Thermal Analysis Summary", body=content["thermal_analysis_narrative"])

            builder.add_section_slide("Validation Testing", number=section_offset + 1)
            test_img.seek(0)
            builder.add_image_slide("Performance vs. Specification", test_img)
            builder.add_content_slide(
                "Test Results Summary",
                body=content["test_results_narrative"],
                bullets=content["test_results_bullets"],
            )

            if test_df is not None:
                builder.add_table_slide("Detailed Test Data", test_df.head(12))
            elif specs_df is not None:
                builder.add_table_slide("Component Specifications", specs_df)

            builder.add_section_slide("Manufacturing Readiness", number=section_offset + 2)
            tolerance_img.seek(0)
            builder.add_two_col_slide(
                "Manufacturing Quality",
                left_text=content["manufacturing_narrative"],
                left_bullets=["Cpk > 1.33 on all CTQ dimensions", "500-unit pilot run completed", "Statistical process control confirmed"],
                right_image=tolerance_img,
            )

            if specs_df is not None:
                builder.add_table_slide("Component Specifications", specs_df)

            builder.add_section_slide("Findings & Recommendations", number=section_offset + 3)
            builder.add_content_slide("Key Findings", bullets=content["findings"])
            builder.add_content_slide("Recommendations", bullets=content["recommendations"])
            builder.add_content_slide("Next Steps", bullets=content["next_steps"])

            builder.add_closing_slide(
                "Thank You",
                lines=[
                    "DENSO International America, Inc.",
                    "Electrification Engineering Division",
                    f"Generated {date.today()} | AI-Powered by Databricks",
                ],
            )

            pptx_bytes = builder.save_bytes()
            progress.progress(100, text="Done!")

        st.success(f"Presentation generated \u2014 {len(builder.prs.slides)} slides")

        # Preview charts
        st.markdown("#### Preview")
        c1, c2, c3 = st.columns(3)
        thermal_img.seek(0)
        test_img.seek(0)
        tolerance_img.seek(0)
        with c1:
            st.image(thermal_img, caption="Thermal Analysis", use_container_width=True)
        with c2:
            st.image(test_img, caption="Test Results", use_container_width=True)
        with c3:
            st.image(tolerance_img, caption="Manufacturing Quality", use_container_width=True)

        st.download_button(
            label="Download Presentation (.pptx)",
            data=pptx_bytes,
            file_name=f"DENSO_TM4200_Review_{date.today():%Y%m%d}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            type="primary",
        )


# ========================= UPLOAD TAB =====================================
with tab_upload:
    st.subheader("Generate from Your Files")
    st.markdown(
        "Upload engineering drawings, data files, and a description. "
        "The AI will analyze your content and produce a branded presentation."
    )

    description = st.text_area(
        "Presentation topic / description",
        height=120,
        placeholder="Describe the engineering project, review topic, or analysis\u2026",
    )

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
            with st.spinner("Processing uploads\u2026"):
                builder = DensoPPTXBuilder()

                title_text = description.split(".")[0][:80] if description else "Engineering Review"
                builder.add_title_slide(title_text, "DENSO | Engineering Review", date.today().strftime("%B %d, %Y"))

                if description:
                    builder.add_content_slide("Overview", body=description)

                for uf in (up_images or []):
                    img_bytes = uf.read()

                    # Save to volume if requested
                    if save_to_volume and IN_DATABRICKS and data_loader:
                        try:
                            data_loader.upload_drawing(uf.name, img_bytes)
                            st.toast(f"Saved {uf.name} to UC Volume")
                        except Exception:
                            pass

                    caption = ""
                    if IN_DATABRICKS and ai_engine:
                        try:
                            caption = ai_engine.analyze_drawing(img_bytes)
                        except Exception:
                            pass

                    title = uf.name.rsplit(".", 1)[0].replace("_", " ").title()
                    builder.add_image_slide(title, BytesIO(img_bytes), caption=caption)

                for uf in (up_data or []):
                    try:
                        df = pd.read_csv(uf) if uf.name.endswith(".csv") else pd.read_excel(uf)
                        builder.add_table_slide(uf.name.rsplit(".", 1)[0].replace("_", " ").title(), df.head(15))
                    except Exception as e:
                        st.warning(f"Could not process {uf.name}: {e}")

                builder.add_closing_slide("Thank You", lines=["DENSO | AI-Generated Presentation | Databricks"])

                pptx_bytes = builder.save_bytes()

            st.success(f"Presentation generated \u2014 {len(builder.prs.slides)} slides")
            st.download_button(
                label="Download Presentation (.pptx)",
                data=pptx_bytes,
                file_name=f"DENSO_Custom_{date.today():%Y%m%d}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                type="primary",
            )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
data_source = "Databricks Gold Tables + UC Volumes" if IN_DATABRICKS else "Demo Mode (local)"
st.caption(
    f"DENSO Engineering Presentation Generator \u00b7 Data: {data_source} \u00b7 "
    "AI: Databricks Foundation Model API \u00b7 Built in an afternoon, not six months."
)
