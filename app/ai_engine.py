"""
AI content generation using Databricks AI functions.

Uses ai_query() via SQL for text generation and the Foundation Model API
for image analysis of engineering drawings.
"""

import json
import base64
import os
from io import BytesIO

import data_loader

# ---------------------------------------------------------------------------
# Project context (default for demo mode)
# ---------------------------------------------------------------------------

PROJECT_CONTEXT = {
    "name": "EV Battery Thermal Management System",
    "model": "TM-4200",
    "project_code": "EVTM-2026-Q2",
    "department": "Electrification Engineering Division",
    "platform": "400V EV Battery Pack",
    "cells": "96-cell module (8 rows x 12 columns)",
    "cooling": "Micro-channel liquid cooling plate",
    "operating_range": "-30 C to 55 C",
    "target_uniformity": "delta-T < 5.0 C",
    "cooling_capacity": "4.2 kW",
}


# ---------------------------------------------------------------------------
# AI-powered text generation via ai_query()
# ---------------------------------------------------------------------------

_CONTENT_PROMPT = """You are a senior automotive thermal-systems engineer at DENSO preparing
a technical presentation for the engineering review board.

PROJECT CONTEXT:
{context}

Generate content for a PowerPoint presentation. Return ONLY valid JSON with these keys:

{{
  "title": "main title (two lines OK, use newline)",
  "subtitle": "subtitle with model and project code",
  "executive_summary": "2-3 paragraph executive summary",
  "thermal_analysis_narrative": "2 paragraphs on thermal FEA results",
  "system_overview_narrative": "1 paragraph system architecture overview",
  "system_overview_bullets": ["bullet 1", "bullet 2", ...],
  "test_results_narrative": "1 paragraph summary of test results",
  "test_results_bullets": ["bullet 1", "bullet 2", ...],
  "manufacturing_narrative": "1 paragraph on manufacturing quality / Cpk",
  "findings": ["finding 1", "finding 2", ...],
  "recommendations": ["rec 1", "rec 2", ...],
  "next_steps": ["step with target date", ...]
}}

Use specific numbers, engineering terminology, 6-8 bullets per list.
Technical but accessible tone for the engineering review board."""


def generate_content(
    project_context: dict | None = None,
    model: str = "databricks-meta-llama-3-3-70b-instruct",
) -> dict:
    """Generate presentation content using ai_query().

    Falls back to high-quality static content if AI is unavailable.
    """
    ctx = project_context or PROJECT_CONTEXT

    try:
        prompt = _CONTENT_PROMPT.format(context=json.dumps(ctx, indent=2))
        # Escape single quotes for SQL
        safe_prompt = prompt.replace("'", "''")

        with data_loader.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT ai_query('{model}', '{safe_prompt}') AS content"
            )
            raw = cursor.fetchone()[0]

        # Parse JSON from response — strip markdown fences if present
        text = raw
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.split("```")[0]

        return json.loads(text)

    except Exception as exc:
        print(f"[ai_engine] ai_query failed ({exc}), using fallback content")
        return _FALLBACK_CONTENT


# ---------------------------------------------------------------------------
# Drawing analysis via ai_query with vision model
# ---------------------------------------------------------------------------

def analyze_drawing(image_bytes: bytes, model: str = "databricks-meta-llama-3-2-11b-vision-instruct") -> str:
    """Analyze an engineering drawing using a vision-capable model.

    Uses the Foundation Model API serving endpoint for multimodal input.
    Falls back to a generic caption if vision is unavailable.
    """
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        # Call the serving endpoint directly for vision
        response = w.serving_endpoints.query(
            name=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You are a DENSO automotive engineer. Describe this "
                                "engineering drawing or patent figure in 2-3 sentences "
                                "suitable for a presentation slide caption. Be specific "
                                "about components, flow paths, and key design features."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=256,
        )
        return response.choices[0].message.content

    except Exception as exc:
        print(f"[ai_engine] Vision analysis failed ({exc})")
        return "DENSO engineering drawing — thermal management system component"


# ---------------------------------------------------------------------------
# ai_parse_document for structured extraction
# ---------------------------------------------------------------------------

def parse_document_specs(volume_path: str) -> dict:
    """Use ai_parse_document to extract specs from a document in a volume.

    Useful for extracting structured data from uploaded spec sheets.
    """
    try:
        with data_loader.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT ai_parse_document(
                    read_files('{volume_path}'),
                    'Extract all engineering specifications, measurements, '
                    'tolerances, materials, and part numbers from this document. '
                    'Return as JSON with keys: components, specifications, materials, '
                    'test_conditions, results.'
                ) AS parsed
            """)
            raw = cursor.fetchone()[0]
            return json.loads(raw) if isinstance(raw, str) else raw
    except Exception as exc:
        print(f"[ai_engine] ai_parse_document failed ({exc})")
        return {}


# ---------------------------------------------------------------------------
# Fallback content (works without any AI/SQL connection)
# ---------------------------------------------------------------------------

_FALLBACK_CONTENT = {
    "title": "EV Battery Thermal Management System\nEngineering Design Review",
    "subtitle": "Model TM-4200  |  Project EVTM-2026-Q2  |  Electrification Engineering",
    "executive_summary": (
        "This document presents the engineering design review for the TM-4200 "
        "thermal management system, designed for next-generation 400V EV battery "
        "applications. The TM-4200 integrates a micro-channel liquid cooling plate "
        "with advanced ECU-controlled flow management to maintain cell temperature "
        "uniformity within \u00b12.5 \u00b0C across all operating conditions.\n\n"
        "Thermal simulation results confirm that the system meets all design targets "
        "under 3C fast-charge conditions at ambient temperatures up to 45 \u00b0C. "
        "Manufacturing process capability analysis shows Cpk values exceeding 1.33 "
        "for all critical dimensions, indicating robust production readiness. The "
        "system achieves a 15% weight reduction over the previous TM-3800 generation "
        "while improving cooling capacity by 22%."
    ),
    "thermal_analysis_narrative": (
        "Finite element thermal analysis was conducted using DENSO\u2019s proprietary "
        "simulation framework, modeling the full 96-cell battery module under "
        "worst-case thermal loading (3C fast charge at 45 \u00b0C ambient). The "
        "simulation accounts for cell-level heat generation, thermal interface "
        "material conductivity, coolant flow distribution, and environmental heat "
        "transfer.\n\n"
        "Results show a maximum cell temperature of 38.2 \u00b0C with module-level "
        "temperature uniformity of \u0394T = 4.8 \u00b0C, within the 5.0 \u00b0C "
        "design specification. The thermal gradient follows the expected coolant "
        "flow pattern. No thermal runaway risk zones were identified."
    ),
    "system_overview_narrative": (
        "The TM-4200 employs a closed-loop liquid cooling architecture with "
        "intelligent flow control, designed for seamless integration with existing "
        "battery pack assemblies."
    ),
    "system_overview_bullets": [
        "Micro-channel aluminum cooling plate with 0.8 mm channel pitch",
        "12x NTC thermistor array for real-time temperature mapping",
        "Brushless DC coolant pump \u2014 variable speed 2\u201312 L/min",
        "Electronic expansion valve for precise coolant regulation",
        "32-bit automotive-grade ECU with CAN / LIN interfaces",
        "Dual-fan radiator assembly (primary + redundant)",
    ],
    "test_results_narrative": (
        "Comprehensive validation testing was performed across the full operating "
        "envelope. All performance metrics met or exceeded design specifications at "
        "1C, 2C, and 3C charge rates under ambient conditions from \u221220 \u00b0C "
        "to 45 \u00b0C."
    ),
    "test_results_bullets": [
        "\u0394T uniformity: 3.2 \u00b0C (1C), 4.1 \u00b0C (2C), 4.8 \u00b0C (3C) \u2014 all within 5.0 \u00b0C spec",
        "Power consumption: 145\u2013195 W, 23% below 200 W target at 3C",
        "Coolant \u0394P: 45 kPa at max flow, 10% margin to 50 kPa limit",
        "Acoustic: 47 dBA peak (3C), below 50 dBA requirement",
        "MTBF estimate: >25,000 hours (accelerated life testing)",
    ],
    "manufacturing_narrative": (
        "Manufacturing process capability was assessed across a 500-unit pilot run. "
        "All critical-to-quality dimensions demonstrate Cpk > 1.33, confirming "
        "production readiness for volume ramp in Q3 2026."
    ),
    "findings": [
        "All thermal targets met under worst-case conditions (3C, 45 \u00b0C ambient)",
        "\u0394T of 4.8 \u00b0C gives 4% margin to the 5.0 \u00b0C limit",
        "15% weight reduction vs. TM-3800 through material optimization",
        "Cpk > 1.33 on all CTQ dimensions \u2014 production ready",
        "Power draw 23% below target; vehicle-level cooling may be downsized",
        "Opportunity to improve coolant flow uniformity in rows 6\u20138",
    ],
    "recommendations": [
        "Proceed to Design Verification (DV) testing with current baseline",
        "Investigate manifold redesign for downstream flow uniformity",
        "Initiate supplier qualification for volume cooling-plate stamping",
        "Conduct 10,000-cycle extended durability testing for DV",
        "Evaluate phase-change TIM for next-generation improvement",
        "Begin OEM customer sample builds \u2014 target Q3 2026",
    ],
    "next_steps": [
        "DV testing kickoff \u2014 May 2026",
        "OEM sample delivery \u2014 July 2026",
        "Production tooling procurement \u2014 August 2026",
        "Process Validation (PV) builds \u2014 October 2026",
        "Start of Production (SOP) \u2014 January 2027",
    ],
}
