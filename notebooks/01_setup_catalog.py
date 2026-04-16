# Databricks notebook source
# MAGIC %md
# MAGIC # DENSO Demo — Setup Catalog, Schema & Volume
# MAGIC Creates the Unity Catalog schema and volume for the PPTX generator demo.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog Name")
catalog = dbutils.widgets.get("catalog")
schema = "denso_demo"

print(f"Setting up: {catalog}.{schema}")

# COMMAND ----------

spark.sql(f"USE CATALOG `{catalog}`")

spark.sql(f"""
    CREATE SCHEMA IF NOT EXISTS `{schema}`
    COMMENT 'DENSO EV Battery Thermal Management demo data'
""")

spark.sql(f"""
    CREATE VOLUME IF NOT EXISTS `{catalog}`.`{schema}`.`engineering_drawings`
    COMMENT 'Patent drawings and engineering diagrams for PPTX generation'
""")

print(f"Schema {catalog}.{schema} and volume engineering_drawings ready.")

# COMMAND ----------

# Verify
display(spark.sql(f"SHOW TABLES IN `{catalog}`.`{schema}`"))
display(spark.sql(f"SHOW VOLUMES IN `{catalog}`.`{schema}`"))
