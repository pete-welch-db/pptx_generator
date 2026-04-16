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
# MAGIC ## Upload CSVs to a temp volume, then read with Spark

# COMMAND ----------

import os

# The data files are in the repo's data/ directory
# When running via DABs job, they're at the workspace path
# When running interactively, adjust the path as needed
data_dir = os.path.join(os.path.dirname(os.getcwd()), "data")

# Check for files in the notebook's directory structure
import glob
csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
if not csv_files:
    # Try the bundle-relative path
    data_dir = "/Workspace/Users/" + spark.conf.get("spark.databricks.notebook.path", "").rsplit("/", 2)[0] + "/data"
    print(f"Trying: {data_dir}")

print(f"Data directory: {data_dir}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load each CSV into a gold Delta table

# COMMAND ----------

from pyspark.sql.types import *

# Table definitions with schemas for clean ingestion
tables = {
    "thermal_sensor_readings": {
        "file": "thermal_sensor_readings.csv",
        "schema": StructType([
            StructField("timestamp", TimestampType()),
            StructField("sensor_id", StringType()),
            StructField("temperature_c", DoubleType()),
            StructField("cell_position_row", IntegerType()),
            StructField("cell_position_col", IntegerType()),
        ]),
    },
    "component_test_results": {
        "file": "component_test_results.csv",
        "schema": StructType([
            StructField("test_id", StringType()),
            StructField("test_date", DateType()),
            StructField("component", StringType()),
            StructField("test_condition", StringType()),
            StructField("metric", StringType()),
            StructField("value", DoubleType()),
            StructField("unit", StringType()),
            StructField("spec_limit", DoubleType()),
            StructField("pass_fail", StringType()),
        ]),
    },
    "manufacturing_quality": {
        "file": "manufacturing_quality.csv",
        "schema": StructType([
            StructField("unit_serial", StringType()),
            StructField("measurement_date", DateType()),
            StructField("cooling_plate_flatness_mm", DoubleType()),
            StructField("channel_depth_mm", DoubleType()),
            StructField("channel_width_mm", DoubleType()),
            StructField("surface_roughness_um", DoubleType()),
            StructField("leak_test_pressure_kpa", DoubleType()),
            StructField("leak_test_result", StringType()),
            StructField("weight_g", DoubleType()),
            StructField("inspector_id", StringType()),
        ]),
    },
    "durability_cycling": {
        "file": "durability_cycling.csv",
        "schema": StructType([
            StructField("cycle_number", IntegerType()),
            StructField("min_temp_c", DoubleType()),
            StructField("max_temp_c", DoubleType()),
            StructField("delta_t_c", DoubleType()),
            StructField("coolant_flow_rate_lpm", DoubleType()),
            StructField("pressure_drop_kpa", DoubleType()),
            StructField("visual_inspection", StringType()),
            StructField("notes", StringType()),
        ]),
    },
    "component_specs": {
        "file": "component_specs.csv",
        "schema": StructType([
            StructField("Component", StringType()),
            StructField("Part_Number", StringType()),
            StructField("Material", StringType()),
            StructField("Weight_g", IntegerType()),
            StructField("Tolerance", StringType()),
            StructField("Status", StringType()),
        ]),
    },
}

# COMMAND ----------

for table_name, config in tables.items():
    csv_path = os.path.join(data_dir, config["file"])
    print(f"\nLoading {table_name} from {csv_path}...")

    try:
        df = (
            spark.read.format("csv")
            .option("header", "true")
            .option("inferSchema", "true")
            .load(csv_path)
        )

        (
            df.write
            .format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(fqn(table_name))
        )

        count = spark.table(fqn(table_name)).count()
        print(f"  -> {fqn(table_name)}: {count:,} rows")

    except Exception as e:
        print(f"  ERROR loading {table_name}: {e}")
        # Fallback: create from pandas if CSV is available locally
        try:
            import pandas as pd
            pdf = pd.read_csv(csv_path)
            sdf = spark.createDataFrame(pdf)
            sdf.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn(table_name))
            print(f"  -> Loaded via pandas fallback: {spark.table(fqn(table_name)).count():,} rows")
        except Exception as e2:
            print(f"  FALLBACK ALSO FAILED: {e2}")

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
    except Exception:
        print(f"  {fqn(table_name)}: NOT FOUND")

# COMMAND ----------

# Quick preview of each table
for table_name in tables:
    print(f"\n--- {table_name} ---")
    display(spark.table(fqn(table_name)).limit(5))
