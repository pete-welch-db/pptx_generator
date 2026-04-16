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
# MAGIC ## Locate drawings in the workspace

# COMMAND ----------

import os

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
bundle_files_dir = "/Workspace" + notebook_path.rsplit("/notebooks/", 1)[0]
drawings_dir = bundle_files_dir + "/drawings"

png_files = sorted([f for f in os.listdir(drawings_dir) if f.endswith(".png")])
print(f"Found {len(png_files)} drawing files in {drawings_dir}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Copy drawings to UC Volume

# COMMAND ----------

uploaded = 0
for filename in png_files:
    src = os.path.join(drawings_dir, filename)
    dest = f"{volume_path}/{filename}"

    try:
        # Read file and write to volume
        with open(src, "rb") as f:
            data = f.read()

        # Write to volume path
        with open(f"/Volumes/{catalog}/{schema}/{volume}/{filename}", "wb") as f:
            f.write(data)

        size_kb = len(data) / 1024
        print(f"  Uploaded: {filename} ({size_kb:.0f} KB)")
        uploaded += 1
    except Exception as e:
        print(f"  FAILED: {filename} - {e}")

print(f"\n{uploaded}/{len(png_files)} drawings uploaded to {volume_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create drawing metadata table

# COMMAND ----------

from pyspark.sql import Row

metadata = [
    Row(filename="heat_exchanger-04.png", patent="US20210039470A1", title="Heat Exchanger - Cross Section View", category="Heat Exchanger", description="Cross-sectional view of micro-channel heat exchanger core for battery cooling"),
    Row(filename="heat_exchanger-05.png", patent="US20210039470A1", title="Heat Exchanger - Plan View", category="Heat Exchanger", description="Plan view from stacking direction showing plate configuration"),
    Row(filename="heat_exchanger-06.png", patent="US20210039470A1", title="Heat Exchanger - Detailed Assembly", category="Heat Exchanger", description="Detailed cross-section showing refrigerant and coolant flow channels"),
    Row(filename="heat_exchanger-07.png", patent="US20210039470A1", title="Heat Exchanger - Second Embodiment", category="Heat Exchanger", description="Alternative design configuration for improved thermal performance"),
    Row(filename="heat_exchanger-08.png", patent="US20210039470A1", title="Heat Exchanger - Flow Configuration", category="Heat Exchanger", description="Stacked plate flow path design for counter-flow heat exchange"),
    Row(filename="thermal_mgmt-03.png", patent="US20210355362A1", title="Thermal Management - System Architecture", category="System Architecture", description="Full vehicle thermal management system with battery, motor, and inverter loops"),
    Row(filename="thermal_mgmt-04.png", patent="US20210355362A1", title="Thermal Management - Coolant Composition", category="System Architecture", description="Schematic of heat transfer medium composition for EV cooling"),
    Row(filename="thermal_mgmt-05.png", patent="US20210355362A1", title="Thermal Management - Performance Data", category="System Architecture", description="Electrical conductivity and thermal performance characteristics"),
    Row(filename="thermal_mgmt-06.png", patent="US20210355362A1", title="Thermal Management - Flow Surface", category="System Architecture", description="Cross-section of coolant flow passage surface treatment"),
    Row(filename="thermal_mgmt-07.png", patent="US20210355362A1", title="Thermal Management - Surface Detail", category="System Architecture", description="Detailed surface morphology for enhanced heat transfer"),
    Row(filename="vehicle_thermal-04.png", patent="US20140041826A1", title="Vehicle Thermal - Winter Warming", category="Vehicle Thermal", description="Vehicle thermal system during winter warming-up operation"),
    Row(filename="vehicle_thermal-05.png", patent="US20140041826A1", title="Vehicle Thermal - Winter Running", category="Vehicle Thermal", description="Thermal circuit during winter driving conditions"),
    Row(filename="vehicle_thermal-06.png", patent="US20140041826A1", title="Vehicle Thermal - Summer Charging", category="Vehicle Thermal", description="Battery cooling during summer fast-charge conditions"),
    Row(filename="vehicle_thermal-07.png", patent="US20140041826A1", title="Vehicle Thermal - Summer Running", category="Vehicle Thermal", description="Thermal management during summer driving with cabin A/C"),
    Row(filename="vehicle_thermal-08.png", patent="US20140041826A1", title="Vehicle Thermal - Alt Config 1", category="Vehicle Thermal", description="Second embodiment thermal system configuration"),
    Row(filename="vehicle_thermal-09.png", patent="US20140041826A1", title="Vehicle Thermal - Alt Config 2", category="Vehicle Thermal", description="Third embodiment with simplified valve arrangement"),
    Row(filename="vehicle_thermal-10.png", patent="US20140041826A1", title="Vehicle Thermal - Alt Config 3", category="Vehicle Thermal", description="Fourth embodiment optimized for dual-zone operation"),
    Row(filename="temp_regulation-04.png", patent="US9649908B2", title="Temperature Regulation - Cooling Mode", category="Temperature Regulation", description="Heat pump cooling mode for battery temperature control"),
    Row(filename="temp_regulation-05.png", patent="US9649908B2", title="Temperature Regulation - High Performance", category="Temperature Regulation", description="High-performance cooling refrigerant flow diagram"),
    Row(filename="temp_regulation-06.png", patent="US9649908B2", title="Temperature Regulation - Control Block", category="Temperature Regulation", description="Control system block diagram with sensor inputs and actuator outputs"),
    Row(filename="temp_regulation-07.png", patent="US9649908B2", title="Temperature Regulation - Passive Cooling", category="Temperature Regulation", description="Low-performance passive cooling heat pipe mode"),
    Row(filename="temp_regulation-08.png", patent="US9649908B2", title="Temperature Regulation - Heating Mode", category="Temperature Regulation", description="Battery heating mode using heat pump for cold-weather operation"),
]

fqn_meta = f"`{catalog}`.`{schema}`.`drawing_metadata`"
meta_df = spark.createDataFrame(metadata)
meta_df.write.format("delta").mode("overwrite").saveAsTable(fqn_meta)

print(f"Drawing metadata saved to {fqn_meta}: {meta_df.count()} entries")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify volume contents

# COMMAND ----------

vol_files = os.listdir(f"/Volumes/{catalog}/{schema}/{volume}")
print(f"\nVolume contents ({len(vol_files)} files):")
for f in sorted(vol_files):
    size = os.path.getsize(f"/Volumes/{catalog}/{schema}/{volume}/{f}")
    print(f"  {f} ({size / 1024:.0f} KB)")
