#!/usr/bin/env python3
"""
Reset demo state — clears uploaded drawings from UC Volume and
removes their entries from the drawing_analysis table (and vector search).

Run from the repo root:
    python3 scripts/reset_demo.py --profile pptx-demo

The script preserves the original 22 patent drawings and only removes
files that were uploaded through the app (identified by not being in
the original set).
"""

import argparse
import subprocess
import json
import sys

# Original drawings that ship with the repo — never delete these
ORIGINAL_DRAWINGS = {
    "heat_exchanger-04.png", "heat_exchanger-05.png", "heat_exchanger-06.png",
    "heat_exchanger-07.png", "heat_exchanger-08.png",
    "thermal_mgmt-03.png", "thermal_mgmt-04.png", "thermal_mgmt-05.png",
    "thermal_mgmt-06.png", "thermal_mgmt-07.png",
    "vehicle_thermal-04.png", "vehicle_thermal-05.png", "vehicle_thermal-06.png",
    "vehicle_thermal-07.png", "vehicle_thermal-08.png", "vehicle_thermal-09.png",
    "vehicle_thermal-10.png",
    "temp_regulation-04.png", "temp_regulation-05.png", "temp_regulation-06.png",
    "temp_regulation-07.png", "temp_regulation-08.png",
    "denso_logo.png",
}

CATALOG = "serverless_sandbox_hsze05_catalog"
SCHEMA = "denso_demo"
VOLUME = "engineering_drawings"
WAREHOUSE_ID = "2e69b709a9fe757a"


def run_sql(statement: str, profile: str) -> dict:
    """Execute SQL via the Databricks API."""
    payload = json.dumps({
        "warehouse_id": WAREHOUSE_ID,
        "statement": statement,
        "wait_timeout": "30s",
    })
    result = subprocess.run(
        ["databricks", "api", "post", "/api/2.0/sql/statements",
         "--profile", profile, "--json", payload],
        capture_output=True, text=True,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"SQL error: {result.stderr or result.stdout}")
        return {"status": {"state": "FAILED"}}


def list_volume_files(profile: str) -> list[str]:
    """List all files in the UC Volume."""
    resp = run_sql(
        f"LIST '/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}'",
        profile,
    )
    files = []
    if resp.get("status", {}).get("state") == "SUCCEEDED":
        for row in resp.get("result", {}).get("data_array", []):
            # LIST returns [path, name, size, modificationTime]
            name = row[1] if len(row) > 1 else row[0].rsplit("/", 1)[-1]
            files.append(name)
    return files


def main():
    parser = argparse.ArgumentParser(description="Reset DENSO PPTX demo state")
    parser.add_argument("--profile", default="pptx-demo", help="Databricks CLI profile")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    parser.add_argument("--full-reset", action="store_true", help="Also rebuild drawing_analysis from original 22 only")
    args = parser.parse_args()

    print(f"{'DRY RUN — ' if args.dry_run else ''}Resetting demo state...")
    print(f"Profile: {args.profile}")
    print(f"Volume: /Volumes/{CATALOG}/{SCHEMA}/{VOLUME}")
    print()

    # 1. Find uploaded (non-original) files in the volume
    print("Listing volume files...")
    all_files = list_volume_files(args.profile)
    uploaded_files = [f for f in all_files if f not in ORIGINAL_DRAWINGS]
    original_count = len([f for f in all_files if f in ORIGINAL_DRAWINGS])

    print(f"  Total files in volume: {len(all_files)}")
    print(f"  Original drawings: {original_count}")
    print(f"  Uploaded (to remove): {len(uploaded_files)}")

    if not uploaded_files:
        print("\nNo uploaded drawings to clean up. Demo state is already clean.")
        if not args.full_reset:
            return

    # 2. Delete uploaded files from the volume
    for filename in uploaded_files:
        path = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{filename}"
        print(f"  {'Would delete' if args.dry_run else 'Deleting'}: {filename}")
        if not args.dry_run:
            run_sql(f"SELECT 1", args.profile)  # keepalive
            # Use the Databricks CLI to delete
            subprocess.run(
                ["databricks", "fs", "rm",
                 f"dbfs:/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{filename}",
                 "--profile", args.profile],
                capture_output=True,
            )

    # 3. Remove uploaded entries from drawing_analysis table
    if uploaded_files:
        filenames_sql = ", ".join(f"'{f}'" for f in uploaded_files)
        print(f"\n{'Would remove' if args.dry_run else 'Removing'} {len(uploaded_files)} entries from drawing_analysis...")
        if not args.dry_run:
            resp = run_sql(
                f"DELETE FROM `{CATALOG}`.`{SCHEMA}`.`drawing_analysis` "
                f"WHERE filename IN ({filenames_sql})",
                args.profile,
            )
            state = resp.get("status", {}).get("state", "?")
            print(f"  drawing_analysis cleanup: {state}")

    # 4. Remove uploaded entries from drawing_metadata table
    if uploaded_files:
        print(f"{'Would remove' if args.dry_run else 'Removing'} from drawing_metadata...")
        if not args.dry_run:
            resp = run_sql(
                f"DELETE FROM `{CATALOG}`.`{SCHEMA}`.`drawing_metadata` "
                f"WHERE filename IN ({filenames_sql})",
                args.profile,
            )
            state = resp.get("status", {}).get("state", "?")
            print(f"  drawing_metadata cleanup: {state}")

    # 5. Full reset: rebuild drawing_analysis with only originals
    if args.full_reset:
        originals_sql = ", ".join(f"'{f}'" for f in ORIGINAL_DRAWINGS if f != "denso_logo.png")
        print(f"\n{'Would rebuild' if args.dry_run else 'Rebuilding'} drawing_analysis (originals only)...")
        if not args.dry_run:
            resp = run_sql(
                f"DELETE FROM `{CATALOG}`.`{SCHEMA}`.`drawing_analysis` "
                f"WHERE filename NOT IN ({originals_sql})",
                args.profile,
            )
            state = resp.get("status", {}).get("state", "?")
            print(f"  drawing_analysis full reset: {state}")

    print(f"\n{'DRY RUN complete.' if args.dry_run else 'Demo reset complete.'}")
    print("Vector Search index will auto-sync the deletions from the Delta table.")
    print(f"Volume should now have {original_count} original drawings.")


if __name__ == "__main__":
    main()
