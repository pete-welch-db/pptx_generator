# Databricks notebook source
# MAGIC %md
# MAGIC # DENSO Demo — Load Gold Tables
# MAGIC Loads CSV data files into Delta gold tables for the PPTX generator.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog Name")
catalog = dbutils.widgets.get("catalog")
schema = "denso_demo"
fqn = lambda t: f"`{catalog}`.`{schema}`.`{t}`"

spark.sql(f"USE CATALOG `{catalog}`")
spark.sql(f"USE SCHEMA `{schema}`")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Locate CSV data files
# MAGIC DABs syncs files to the workspace. Determine the correct path.

# COMMAND ----------

import os

# In a DABs deployment, the notebook is at:
#   /Workspace/Users/<user>/.bundle/<bundle>/default/files/notebooks/02_load_gold_tables.py
# So data/ is at:
#   /Workspace/Users/<user>/.bundle/<bundle>/default/files/data/

# Get the notebook's workspace path and navigate to data/
notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
bundle_files_dir = "/Workspace" + notebook_path.rsplit("/notebooks/", 1)[0]
data_dir = bundle_files_dir + "/data"

print(f"Notebook path: {notebook_path}")
print(f"Data directory: {data_dir}")

# Verify the data files exist
csv_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]
print(f"Found {len(csv_files)} CSV files: {csv_files}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load each CSV into a gold Delta table

# COMMAND ----------

import pandas as pd

tables = {
    "thermal_sensor_readings": "thermal_sensor_readings.csv",
    "component_test_results": "component_test_results.csv",
    "manufacturing_quality": "manufacturing_quality.csv",
    "durability_cycling": "durability_cycling.csv",
    "component_specs": "component_specs.csv",
}

# COMMAND ----------

for table_name, csv_file in tables.items():
    csv_path = os.path.join(data_dir, csv_file)
    print(f"\nLoading {table_name} from {csv_path}...")

    try:
        # Read CSV with pandas then convert to Spark (works on serverless)
        pdf = pd.read_csv(csv_path)
        sdf = spark.createDataFrame(pdf)

        (
            sdf.write
            .format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(fqn(table_name))
        )

        count = spark.table(fqn(table_name)).count()
        print(f"  -> {fqn(table_name)}: {count:,} rows")

    except Exception as e:
        print(f"  ERROR loading {table_name}: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify all tables

# COMMAND ----------

print(f"\n{'='*60}")
print(f"Gold tables in {catalog}.{schema}:")
print(f"{'='*60}")
for table_name in tables:
    try:
        count = spark.table(fqn(table_name)).count()
        print(f"  {fqn(table_name)}: {count:,} rows")
    except Exception as e:
        print(f"  {fqn(table_name)}: NOT FOUND ({e})")
