# Databricks notebook source
# MAGIC %md
# MAGIC # DENSO Demo — Load Patent Drawings to UC Volume
# MAGIC Uploads engineering patent drawings (PNG files) into a Unity Catalog Volume
# MAGIC so the Databricks App can serve them for PPTX generation.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog Name")
catalog = dbutils.widgets.get("catalog")
schema = "denso_demo"
volume = "engineering_drawings"
volume_path = f"/Volumes/{catalog}/{schema}/{volume}"

print(f"Target volume: {volume_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Upload drawings from repo
# MAGIC The drawings/ directory contains patent engineering drawings extracted from
# MAGIC DENSO thermal management patents (public domain).

# COMMAND ----------

import os
import glob

# Find the drawings directory relative to the notebook
drawings_dir = os.path.join(os.path.dirname(os.getcwd()), "drawings")
png_files = sorted(glob.glob(os.path.join(drawings_dir, "*.png")))

if not png_files:
    # Try workspace relative path
    print(f"No PNGs found at {drawings_dir}, trying workspace path...")
    drawings_dir = "/Workspace" + os.path.dirname(spark.conf.get("spark.databricks.notebook.path", "")).rsplit("/", 1)[0] + "/drawings"
    png_files = sorted(glob.glob(os.path.join(drawings_dir, "*.png")))

print(f"Found {len(png_files)} drawing files in {drawings_dir}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Copy to UC Volume

# COMMAND ----------

uploaded = 0
for png_path in png_files:
    filename = os.path.basename(png_path)
    dest = f"{volume_path}/{filename}"

    try:
        dbutils.fs.cp(f"file:{png_path}", dest)
        size_kb = os.path.getsize(png_path) / 1024
        print(f"  Uploaded: {filename} ({size_kb:.0f} KB)")
        uploaded += 1
    except Exception as e:
        # Fallback: use workspace client
        try:
            from databricks.sdk import WorkspaceClient
            from io import BytesIO

            w = WorkspaceClient()
            with open(png_path, "rb") as f:
                w.files.upload(dest, f, overwrite=True)
            print(f"  Uploaded (SDK): {filename}")
            uploaded += 1
        except Exception as e2:
            print(f"  FAILED: {filename} - {e2}")

print(f"\n{uploaded}/{len(png_files)} drawings uploaded to {volume_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Add descriptive metadata
# MAGIC Create a metadata table mapping filenames to patent info for the app UI.

# COMMAND ----------

from pyspark.sql import Row

metadata = [
    Row(filename="heat_exchanger-04.png", patent="US20210039470A1", title="Heat Exchanger - Cross Section View", category="Heat Exchanger", description="Cross-sectional view of micro-channel heat exchanger core for battery cooling"),
    Row(filename="heat_exchanger-05.png", patent="US20210039470A1", title="Heat Exchanger - Plan View", category="Heat Exchanger", description="Plan view from stacking direction showing plate configuration"),
    Row(filename="heat_exchanger-06.png", patent="US20210039470A1", title="Heat Exchanger - Detailed Assembly", category="Heat Exchanger", description="Detailed cross-section showing refrigerant and coolant flow channels"),
    Row(filename="heat_exchanger-07.png", patent="US20210039470A1", title="Heat Exchanger - Second Embodiment", category="Heat Exchanger", description="Alternative design configuration for improved thermal performance"),
    Row(filename="heat_exchanger-08.png", patent="US20210039470A1", title="Heat Exchanger - Flow Configuration", category="Heat Exchanger", description="Stacked plate flow path design for counter-flow heat exchange"),
    Row(filename="thermal_mgmt-03.png", patent="US20210355362A1", title="Thermal Management - System Architecture", category="System Architecture", description="Full vehicle thermal management system showing battery, motor, and inverter cooling loops"),
    Row(filename="thermal_mgmt-04.png", patent="US20210355362A1", title="Thermal Management - Coolant Composition", category="System Architecture", description="Schematic of heat transfer medium composition for EV cooling"),
    Row(filename="thermal_mgmt-05.png", patent="US20210355362A1", title="Thermal Management - Performance Data", category="System Architecture", description="Electrical conductivity and thermal performance characteristics"),
    Row(filename="thermal_mgmt-06.png", patent="US20210355362A1", title="Thermal Management - Flow Surface", category="System Architecture", description="Cross-section of coolant flow passage surface treatment"),
    Row(filename="thermal_mgmt-07.png", patent="US20210355362A1", title="Thermal Management - Surface Detail", category="System Architecture", description="Detailed surface morphology for enhanced heat transfer"),
    Row(filename="vehicle_thermal-04.png", patent="US20140041826A1", title="Vehicle Thermal System - Winter Warming", category="Vehicle Thermal", description="Complete vehicle thermal system during winter warming-up operation"),
    Row(filename="vehicle_thermal-05.png", patent="US20140041826A1", title="Vehicle Thermal System - Winter Running", category="Vehicle Thermal", description="Thermal circuit configuration during winter driving conditions"),
    Row(filename="vehicle_thermal-06.png", patent="US20140041826A1", title="Vehicle Thermal System - Summer Charging", category="Vehicle Thermal", description="Battery cooling configuration during summer fast-charge conditions"),
    Row(filename="vehicle_thermal-07.png", patent="US20140041826A1", title="Vehicle Thermal System - Summer Running", category="Vehicle Thermal", description="Thermal management during summer driving with cabin A/C active"),
    Row(filename="vehicle_thermal-08.png", patent="US20140041826A1", title="Vehicle Thermal System - Alt Config 1", category="Vehicle Thermal", description="Second embodiment thermal system configuration"),
    Row(filename="vehicle_thermal-09.png", patent="US20140041826A1", title="Vehicle Thermal System - Alt Config 2", category="Vehicle Thermal", description="Third embodiment with simplified valve arrangement"),
    Row(filename="vehicle_thermal-10.png", patent="US20140041826A1", title="Vehicle Thermal System - Alt Config 3", category="Vehicle Thermal", description="Fourth embodiment optimized for dual-zone operation"),
    Row(filename="temp_regulation-04.png", patent="US9649908B2", title="Temperature Regulation - Cooling Mode", category="Temperature Regulation", description="Heat pump cooling mode system schematic for battery temperature control"),
    Row(filename="temp_regulation-05.png", patent="US9649908B2", title="Temperature Regulation - High Performance", category="Temperature Regulation", description="High-performance cooling refrigerant flow diagram"),
    Row(filename="temp_regulation-06.png", patent="US9649908B2", title="Temperature Regulation - Control Block", category="Temperature Regulation", description="Control system block diagram showing sensor inputs and actuator outputs"),
    Row(filename="temp_regulation-07.png", patent="US9649908B2", title="Temperature Regulation - Passive Cooling", category="Temperature Regulation", description="Low-performance passive cooling heat pipe mode"),
    Row(filename="temp_regulation-08.png", patent="US9649908B2", title="Temperature Regulation - Heating Mode", category="Temperature Regulation", description="Battery heating mode using heat pump for cold-weather operation"),
]

meta_df = spark.createDataFrame(metadata)
fqn = f"`{catalog}`.`{schema}`.`drawing_metadata`"
meta_df.write.format("delta").mode("overwrite").saveAsTable(fqn)

print(f"Drawing metadata saved to {fqn}: {meta_df.count()} entries")
display(meta_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify volume contents

# COMMAND ----------

files = dbutils.fs.ls(volume_path)
print(f"\nVolume contents ({len(files)} files):")
for f in files:
    print(f"  {f.name} ({f.size / 1024:.0f} KB)")
