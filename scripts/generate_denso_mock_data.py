"""
Generate mock Jira and Confluence CSV data for the DENSO TM-4200
EV Battery Thermal Management System gate review project.
"""

import csv
import random
import os
from datetime import date, timedelta

random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# ── Assignees ──────────────────────────────────────────────────────────
ASSIGNEES = [
    "Takeshi Yamamoto",
    "Yuki Tanaka",
    "Hiroshi Nakamura",
    "Akiko Suzuki",
    "Kenji Watanabe",
    "Mika Ito",
    "Satoshi Kobayashi",
    "Kyle Henderson",
    "Sarah Mitchell",
    "James Park",
    "David Chen",
    "Emily Reeves",
]

COMPONENTS = [
    "Cooling Plate",
    "Coolant Pump",
    "ECU",
    "Expansion Valve",
    "Radiator",
    "TIM",
    "Sensors",
    "System Integration",
]

LABEL_POOL = [
    "thermal", "electrical", "mechanical", "software",
    "safety", "manufacturing", "quality", "design",
]

GATES = ["PKD", "RKD", "DR", "SQA"]
SPRINTS = ["Sprint 12", "Sprint 13", "Sprint 14", "Sprint 15", "Sprint 16"]
PRIORITIES = ["Critical", "High", "Medium", "Low"]

# ── Realistic summaries grouped by component ──────────────────────────
SUMMARIES = {
    "Cooling Plate": [
        "Cooling plate flatness exceeds spec on units 347-352",
        "Brazing joint leak detected at 2.5 bar pressure test on CP-4200-A1",
        "Cooling plate inlet manifold O-ring groove dimension out of tolerance",
        "FEA thermal gradient exceeds 4°C across cooling plate surface at 3C charge",
        "Surface roughness Ra > 1.6 µm on cooling plate mating face (Lot 22)",
        "Cooling plate weight 8% over target — evaluate thinner wall design",
    ],
    "Coolant Pump": [
        "Coolant flow rate drops below 6 L/min at high ambient temps",
        "Pump cavitation noise observed above 55°C coolant temperature",
        "Coolant pump PWM duty-cycle mapping needs recalibration for low-flow mode",
        "Pump motor bearing life test shows 12% degradation at 8000 hrs",
        "Coolant pump connector seal fails IP67 splash test",
    ],
    "ECU": [
        "ECU firmware v2.3 watchdog timer reset during 3C charge",
        "CAN bus message EVTM_TempReq drops frames under high bus load",
        "ECU flash memory write endurance margin below 10% at EOL",
        "OBD-II DTC P0599 false trigger under cold-start conditions",
        "ECU bootloader update fails intermittently via UDS 0x34 service",
        "Power supply ripple on ECU 5V rail exceeds 100mV pp at 12V drop",
    ],
    "Expansion Valve": [
        "Electronic expansion valve response lag >800ms at step input",
        "EXV stepper motor stall at −30°C ambient soak",
        "Expansion valve superheat control oscillates ±3°C at partial load",
        "EXV coil resistance drift after 2000 thermal cycles",
    ],
    "Radiator": [
        "Radiator core pressure drop 15% above target at 10 L/min",
        "Fin density optimization needed to meet NVH targets at 4000 RPM fan speed",
        "Radiator mounting bracket stress exceeds allowable at 20G shock load",
    ],
    "TIM": [
        "TIM pad delamination observed after 1500 thermal cycles",
        "Thermal interface material bulk resistance increases 18% post-aging",
        "TIM compression set exceeds 25% after 90-day high-temp storage",
        "TIM outgassing VOC levels above DENSO DS-4501 limit",
        "Alternative TIM supplier qualification — Henkel vs Shin-Etsu comparison",
    ],
    "Sensors": [
        "NTC thermistor B-constant tolerance causes ±1.2°C error at 60°C",
        "Coolant pressure sensor zero-point drift after vibration endurance",
        "Battery cell surface thermocouple adhesive fails above 70°C",
        "Inlet/outlet ΔT sensor pair mismatch exceeds 0.5°C specification",
    ],
    "System Integration": [
        "System-level COP drops below 2.8 at 45°C ambient condition",
        "Refrigerant charge optimization for dual-mode heat pump / cooling",
        "Harness routing interference with HV battery disconnect bracket",
        "Full-vehicle thermal soak test shows 3-min delay to reach target temp",
        "Integration test — HVAC priority arbitration conflicts with BTMS request",
        "EMC pre-compliance CISPR 25 Class 5 failure on ECU power lines",
    ],
}

# Flatten to get a pool of (component, summary) tuples
SUMMARY_POOL = []
for comp, summaries in SUMMARIES.items():
    for s in summaries:
        SUMMARY_POOL.append((comp, s))

random.shuffle(SUMMARY_POOL)

# Component → most-relevant labels mapping (for realistic correlation)
COMPONENT_LABELS = {
    "Cooling Plate": ["thermal", "mechanical", "manufacturing", "design"],
    "Coolant Pump": ["mechanical", "manufacturing", "quality"],
    "ECU": ["software", "electrical", "safety"],
    "Expansion Valve": ["thermal", "mechanical"],
    "Radiator": ["thermal", "mechanical", "design"],
    "TIM": ["thermal", "manufacturing", "quality"],
    "Sensors": ["electrical", "quality"],
    "System Integration": ["thermal", "electrical", "safety", "design"],
}

# Gate relevance by component (weighted toward most likely)
COMPONENT_GATES = {
    "Cooling Plate": ["PKD", "RKD", "DR"],
    "Coolant Pump": ["RKD", "DR"],
    "ECU": ["RKD", "DR", "SQA"],
    "Expansion Valve": ["RKD", "DR"],
    "Radiator": ["PKD", "RKD"],
    "TIM": ["PKD", "DR", "SQA"],
    "Sensors": ["RKD", "DR", "SQA"],
    "System Integration": ["DR", "SQA"],
}


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def generate_jira_issues(path: str):
    """Generate ~40 Jira issue rows."""
    # Status distribution: 10 open-ish, 20 resolved, 10 closed
    status_bucket = (
        ["Open"] * 5
        + ["In Progress"] * 3
        + ["Blocked"] * 2
        + ["Resolved"] * 20
        + ["Closed"] * 10
    )
    random.shuffle(status_bucket)

    rows = []
    used = set()

    for i in range(40):
        key = f"EVTM-{1001 + i}"

        # Pick a unique summary
        comp, summary = SUMMARY_POOL[i % len(SUMMARY_POOL)]

        status = status_bucket[i]
        priority = random.choices(
            PRIORITIES, weights=[10, 30, 40, 20], k=1
        )[0]
        assignee = random.choice(ASSIGNEES)
        sprint = random.choice(SPRINTS)
        story_points = random.choice([1, 2, 3, 5, 8, 13])

        # Labels — pick 2-3 from component-relevant pool
        comp_labels = COMPONENT_LABELS.get(comp, LABEL_POOL[:3])
        n_labels = random.randint(2, 3)
        labels = random.sample(comp_labels, min(n_labels, len(comp_labels)))
        # occasionally add one more from the general pool
        if random.random() < 0.3:
            extra = random.choice([l for l in LABEL_POOL if l not in labels])
            labels.append(extra)

        # Gate review — 1 or 2 gates from component-relevant set
        comp_gates = COMPONENT_GATES.get(comp, GATES)
        n_gates = 1 if random.random() < 0.6 else 2
        gate_review = random.sample(comp_gates, min(n_gates, len(comp_gates)))

        # Dates
        created = random_date(date(2026, 1, 5), date(2026, 4, 10))
        resolved_date = ""
        resolution = ""
        if status in ("Resolved", "Closed"):
            resolved_date = random_date(
                created + timedelta(days=2),
                min(created + timedelta(days=45), date(2026, 4, 15)),
            )
            resolution = random.choice(["Fixed", "Fixed", "Fixed", "Won't Fix", "Duplicate"])
        elif status == "Blocked":
            resolution = ""

        rows.append({
            "issue_key": key,
            "summary": summary,
            "status": status,
            "priority": priority,
            "assignee": assignee,
            "component": comp,
            "created_date": created.isoformat(),
            "resolved_date": str(resolved_date) if resolved_date else "",
            "resolution": resolution,
            "sprint": sprint,
            "story_points": story_points,
            "labels": ";".join(sorted(labels)),
            "gate_review": ";".join(sorted(gate_review)),
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {path}")


# ── Confluence pages ──────────────────────────────────────────────────

CONFLUENCE_PAGES = [
    {
        "page_id": "EVTM-DOC-001",
        "title": "TM-4200 System Architecture Design Document v3.1",
        "status": "Published",
        "content_summary": "Top-level system architecture for the TM-4200 battery thermal management system including refrigerant loop, coolant loop, control strategy, and interface definitions.",
        "labels": "specification;design-review",
        "gate_review": "PKD",
        "linked_issues": ["EVTM-1001", "EVTM-1008", "EVTM-1035"],
    },
    {
        "page_id": "EVTM-DOC-002",
        "title": "Thermal FEA Analysis Report - 3C Fast Charge Scenarios",
        "status": "Published",
        "content_summary": "Finite element thermal analysis of cooling plate and TIM stack under 3C fast-charge conditions (25°C, 35°C, 45°C ambient). Includes hot-spot mapping and design margin assessment.",
        "labels": "test-report;design-review",
        "gate_review": "RKD;DR",
        "linked_issues": ["EVTM-1004", "EVTM-1030"],
    },
    {
        "page_id": "EVTM-DOC-003",
        "title": "DR-3 Design Review Meeting Notes - 2026-03-15",
        "status": "Published",
        "content_summary": "Minutes from third design review gate. Covers open action items, risk register updates, and component-level design freeze status.",
        "labels": "meeting-notes;design-review",
        "gate_review": "DR",
        "linked_issues": ["EVTM-1002", "EVTM-1010", "EVTM-1015", "EVTM-1022"],
    },
    {
        "page_id": "EVTM-DOC-004",
        "title": "Supplier Quality Audit Report - Cooling Plate (CP-4200-A1)",
        "status": "Published",
        "content_summary": "On-site SQA audit of cooling plate supplier (Tier-2, Kariya plant). Covers process capability, dimensional control, brazing quality, and corrective actions from prior audit.",
        "labels": "supplier-quality;risk-assessment",
        "gate_review": "SQA",
        "linked_issues": ["EVTM-1001", "EVTM-1002", "EVTM-1005"],
    },
    {
        "page_id": "EVTM-DOC-005",
        "title": "PKD Gate Review Checklist - Phase 2 Exit Criteria",
        "status": "Published",
        "content_summary": "Product Key Decision gate checklist with 34 exit criteria covering system requirements, feasibility, supplier selection, and initial cost targets.",
        "labels": "design-review;specification",
        "gate_review": "PKD",
        "linked_issues": ["EVTM-1001", "EVTM-1006", "EVTM-1012"],
    },
    {
        "page_id": "EVTM-DOC-006",
        "title": "Coolant Pump Endurance Test Report - 8000 hr Results",
        "status": "Published",
        "content_summary": "Long-duration endurance test results for coolant pump assembly. Documents flow rate degradation, bearing wear, and seal integrity over 8000-hour accelerated life test.",
        "labels": "test-report;supplier-quality",
        "gate_review": "RKD;SQA",
        "linked_issues": ["EVTM-1007", "EVTM-1008", "EVTM-1009"],
    },
    {
        "page_id": "EVTM-DOC-007",
        "title": "ECU Firmware Release Notes - v2.3.1 Patch",
        "status": "Under Review",
        "content_summary": "Release notes for ECU firmware patch addressing watchdog timer reset, CAN frame drop, and OBD-II DTC false trigger issues identified in Sprint 14.",
        "labels": "specification;risk-assessment",
        "gate_review": "DR",
        "linked_issues": ["EVTM-1011", "EVTM-1012", "EVTM-1014"],
    },
    {
        "page_id": "EVTM-DOC-008",
        "title": "TIM Material Qualification - Henkel vs Shin-Etsu Comparison",
        "status": "Published",
        "content_summary": "Head-to-head comparison of two TIM candidates across thermal conductivity, long-term aging, compression set, outgassing, and cost. Includes recommendation matrix.",
        "labels": "test-report;supplier-quality;design-review",
        "gate_review": "PKD;SQA",
        "linked_issues": ["EVTM-1026", "EVTM-1027", "EVTM-1028", "EVTM-1029"],
    },
    {
        "page_id": "EVTM-DOC-009",
        "title": "System-Level COP Optimization Study",
        "status": "Under Review",
        "content_summary": "Analysis of system coefficient of performance across operating envelope. Evaluates refrigerant charge, compressor speed mapping, and EXV control tuning for COP improvement.",
        "labels": "test-report;design-review",
        "gate_review": "RKD;DR",
        "linked_issues": ["EVTM-1035", "EVTM-1036"],
    },
    {
        "page_id": "EVTM-DOC-010",
        "title": "EMC Pre-Compliance Test Report - CISPR 25 Class 5",
        "status": "Draft",
        "content_summary": "Pre-compliance electromagnetic compatibility test results for ECU and pump driver electronics. Documents conducted and radiated emissions against CISPR 25 Class 5 limits.",
        "labels": "test-report;risk-assessment",
        "gate_review": "DR;SQA",
        "linked_issues": ["EVTM-1040"],
    },
    {
        "page_id": "EVTM-DOC-011",
        "title": "DFMEA - Cooling Plate Assembly Rev C",
        "status": "Published",
        "content_summary": "Design Failure Mode and Effects Analysis for the cooling plate assembly, covering brazing defects, manifold sealing, flatness deviations, and corrosion risk.",
        "labels": "risk-assessment;design-review",
        "gate_review": "PKD;RKD",
        "linked_issues": ["EVTM-1001", "EVTM-1003"],
    },
    {
        "page_id": "EVTM-DOC-012",
        "title": "Sensor Calibration Procedure - NTC Thermistors & Pressure Transducers",
        "status": "Published",
        "content_summary": "Calibration procedure and acceptance criteria for all temperature and pressure sensors in the BTMS. Includes traceability requirements and measurement uncertainty budget.",
        "labels": "specification;supplier-quality",
        "gate_review": "RKD;SQA",
        "linked_issues": ["EVTM-1031", "EVTM-1032", "EVTM-1033"],
    },
    {
        "page_id": "EVTM-DOC-013",
        "title": "Thermal Soak Test Protocol & Results - Full Vehicle",
        "status": "Draft",
        "content_summary": "Test protocol and preliminary results for full-vehicle thermal soak test at 45°C ambient. Measures time-to-target for battery pack cooling from soak temperature.",
        "labels": "test-report;meeting-notes",
        "gate_review": "DR",
        "linked_issues": ["EVTM-1038"],
    },
    {
        "page_id": "EVTM-DOC-014",
        "title": "RKD Gate Review Checklist - Requirements Freeze Criteria",
        "status": "Under Review",
        "content_summary": "Requirements Key Decision gate checklist covering requirements traceability, DVP&R plan, supplier PPAP status, and test readiness for component validation.",
        "labels": "design-review;specification",
        "gate_review": "RKD",
        "linked_issues": ["EVTM-1006", "EVTM-1016", "EVTM-1020"],
    },
    {
        "page_id": "EVTM-DOC-015",
        "title": "Expansion Valve Cold-Start Performance Analysis",
        "status": "Published",
        "content_summary": "Analysis of electronic expansion valve behavior during cold-start conditions (−30°C to −10°C ambient soak). Documents stepper motor stall events and superheat control response.",
        "labels": "test-report;risk-assessment",
        "gate_review": "RKD;DR",
        "linked_issues": ["EVTM-1017", "EVTM-1018", "EVTM-1019"],
    },
]

AUTHORS = [
    "Takeshi Yamamoto",
    "Akiko Suzuki",
    "Kyle Henderson",
    "Sarah Mitchell",
    "Hiroshi Nakamura",
    "David Chen",
    "Kenji Watanabe",
    "Mika Ito",
]


def generate_confluence_pages(path: str):
    rows = []
    for page in CONFLUENCE_PAGES:
        created = random_date(date(2026, 1, 10), date(2026, 3, 20))
        last_updated = random_date(
            created + timedelta(days=1),
            min(created + timedelta(days=30), date(2026, 4, 14)),
        )
        rows.append({
            "page_id": page["page_id"],
            "title": page["title"],
            "space": "EVTM Engineering",
            "author": random.choice(AUTHORS),
            "created_date": created.isoformat(),
            "last_updated": last_updated.isoformat(),
            "status": page["status"],
            "content_summary": page["content_summary"],
            "labels": page["labels"],
            "linked_jira_issues": ";".join(page["linked_issues"]),
            "gate_review": page["gate_review"],
        })

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    jira_path = os.path.join(DATA_DIR, "jira_issues.csv")
    confluence_path = os.path.join(DATA_DIR, "confluence_pages.csv")

    generate_jira_issues(jira_path)
    generate_confluence_pages(confluence_path)
    print("Done.")
