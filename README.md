# DENSO Engineering PPTX Generator

AI-powered PowerPoint generation for engineering review decks, running on Databricks.

## What It Does

Takes engineering data (thermal analysis, test results, manufacturing QC) and patent drawings,
feeds them through Databricks AI functions (`ai_query`, `ai_parse_document`), and produces a
polished, DENSO-branded PPTX in seconds.

**Demo scenario:** EV Battery Thermal Management System (Model TM-4200, 96-cell module, 400V platform)

## Architecture

```
Gold Delta Tables (UC)          UC Volume
  thermal_sensor_readings         /engineering_drawings/
  component_test_results            heat_exchanger-*.png
  manufacturing_quality             thermal_mgmt-*.png
  durability_cycling                vehicle_thermal-*.png
  component_specs                   temp_regulation-*.png
  drawing_metadata
        |                                |
        v                                v
  +-----------------------------------------+
  |        Databricks App (Streamlit)       |
  |  - Reads gold tables via SQL connector  |
  |  - Reads drawings from UC Volume        |
  |  - ai_query() for content generation    |
  |  - ai_parse_document() for spec sheets  |
  |  - Vision model for drawing analysis    |
  |  - python-pptx for PPTX generation      |
  +-----------------------------------------+
                    |
                    v
          DENSO-branded .pptx
```

## Deploy with DABs

```bash
# 1. Configure your workspace
databricks auth login <workspace-url>

# 2. Set variables
export BUNDLE_VAR_catalog="your_catalog"
export BUNDLE_VAR_warehouse_id="your_warehouse_id"
export BUNDLE_VAR_workspace_url="https://your-workspace.cloud.databricks.com"

# 3. Deploy and run setup
databricks bundle deploy
databricks bundle run setup_gold_tables

# 4. Deploy the app
databricks bundle run denso-pptx-generator
```

## Data

- `data/` — CSV files loaded into gold Delta tables via notebook
- `drawings/` — Patent engineering drawings (DENSO thermal management patents, public domain)

### Gold Tables

| Table | Rows | Description |
|-------|------|-------------|
| `thermal_sensor_readings` | 1,440 | 12 NTC sensors x 120 timestamps during 3C fast charge |
| `component_test_results` | 90 | Validation across 9 conditions x 5 metrics |
| `manufacturing_quality` | 500 | Pilot run QC measurements (flatness, Cpk) |
| `durability_cycling` | 2,000 | Thermal cycling -40/+85C with degradation trend |
| `component_specs` | 7 | Part numbers, materials, tolerances |
| `drawing_metadata` | 22 | Patent drawing descriptions and categories |

### Patent Drawings (UC Volume)

22 engineering drawings from 4 DENSO patents:
- **US20210039470A1** — Heat exchanger cross-sections and flow paths
- **US20210355362A1** — Vehicle thermal management system architecture
- **US20140041826A1** — Winter/summer thermal operation modes
- **US9649908B2** — Temperature regulation and heat pump cooling

## AI Functions Used

| Function | Purpose |
|----------|---------|
| `ai_query()` | Generate executive summaries, narratives, findings, recommendations |
| `ai_parse_document()` | Extract specs from uploaded engineering documents |
| Foundation Model API (vision) | Analyze engineering drawings and auto-generate captions |

## Local Development

```bash
cd app
pip install -r requirements.txt
streamlit run app.py
```

The app auto-detects whether it's running in Databricks or locally and adjusts accordingly.
