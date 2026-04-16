# Databricks notebook source
# MAGIC %md
# MAGIC # DENSO Demo — Analyze Drawings & Build Vector Search Index
# MAGIC
# MAGIC Processes all engineering drawings in the UC Volume:
# MAGIC 1. **Vision extraction** — Claude analyzes each drawing, extracts components, specs, system area
# MAGIC 2. **Embeddings** — Generates vector embeddings of the extracted descriptions
# MAGIC 3. **Vector Search index** — Creates a searchable index for semantic drawing-to-data matching
# MAGIC
# MAGIC This enables intelligent linking at PPTX generation time: data metrics are embedded
# MAGIC and matched to the most relevant drawings via vector similarity.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog Name")
catalog = dbutils.widgets.get("catalog")
schema = "denso_demo"
volume = "engineering_drawings"
fqn = lambda t: f"`{catalog}`.`{schema}`.`{t}`"
volume_path = f"/Volumes/{catalog}/{schema}/{volume}"

print(f"Catalog: {catalog}")
print(f"Volume: {volume_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Create the drawing_analysis table

# COMMAND ----------

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {fqn('drawing_analysis')} (
        filename STRING COMMENT 'Drawing filename in UC Volume',
        patent STRING COMMENT 'Patent number',
        title STRING COMMENT 'Drawing title',
        category STRING COMMENT 'High-level category',
        extracted_components ARRAY<STRING> COMMENT 'Components identified by vision model',
        extracted_specs MAP<STRING, STRING> COMMENT 'Specifications extracted from drawing',
        system_area STRING COMMENT 'thermal, electrical, mechanical, control',
        description_text STRING COMMENT 'Full AI-generated description of drawing content',
        data_keywords ARRAY<STRING> COMMENT 'Keywords for matching to gold table data',
        embedding ARRAY<DOUBLE> COMMENT 'Vector embedding of description_text'
    )
    USING DELTA
    COMMENT 'AI-extracted metadata and embeddings for engineering drawings'
""")
print(f"Table {fqn('drawing_analysis')} ready")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Vision extraction — analyze each drawing with Claude

# COMMAND ----------

import os
import json
import base64
import time

png_files = sorted([f for f in os.listdir(volume_path) if f.endswith('.png')])
print(f"Found {len(png_files)} drawings to analyze")

# Get existing metadata for patent/title info
existing_meta = spark.sql(f"SELECT * FROM {fqn('drawing_metadata')}").toPandas()
meta_lookup = {row['filename']: row for _, row in existing_meta.iterrows()}

# COMMAND ----------

# Vision extraction prompt
VISION_PROMPT = """You are a DENSO automotive thermal-systems engineer analyzing a patent drawing.

Analyze this engineering drawing and return ONLY valid JSON with these fields:

{
    "extracted_components": ["list", "of", "specific", "components", "shown"],
    "extracted_specs": {"spec_name": "value", ...},
    "system_area": "one of: thermal, electrical, mechanical, control, system_architecture",
    "description_text": "Detailed 3-4 sentence technical description of what this drawing shows, including flow paths, component relationships, and design features",
    "data_keywords": ["keywords", "that", "would", "match", "test", "data", "about", "this", "drawing"]
}

For data_keywords, include terms like: temperature, cooling, thermal, pressure, flow_rate,
heat_exchanger, coolant, refrigerant, valve, pump, sensor, ECU, battery, uniformity, etc.
Include both the component names and the metrics you'd measure for those components."""

# COMMAND ----------

results = []
for i, filename in enumerate(png_files):
    print(f"\n[{i+1}/{len(png_files)}] Analyzing {filename}...")

    # Read image and encode
    filepath = os.path.join(volume_path, filename)
    with open(filepath, 'rb') as f:
        img_bytes = f.read()
    b64_img = base64.standard_b64encode(img_bytes).decode('utf-8')

    # Get existing metadata
    meta = meta_lookup.get(filename, {})
    patent = meta.get('patent', 'Unknown') if isinstance(meta, dict) else getattr(meta, 'patent', 'Unknown')
    title = meta.get('title', filename) if isinstance(meta, dict) else getattr(meta, 'title', filename)
    category = meta.get('category', 'Unknown') if isinstance(meta, dict) else getattr(meta, 'category', 'Unknown')

    try:
        # Call ai_query with vision via SQL
        # We pass the image as a base64 data URI in the prompt
        vision_query = f"""
        SELECT ai_query(
            'databricks-claude-sonnet-4-6',
            CONCAT(
                'Image (base64 PNG): data:image/png;base64,{b64_img[:100]}...\\n\\n',
                '{VISION_PROMPT.replace(chr(39), chr(39)+chr(39))}'
            )
        ) AS result
        """

        # For vision, use the serving endpoint directly instead of ai_query SQL
        # ai_query SQL doesn't support image inputs yet, so we use the SDK
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()

        response = w.serving_endpoints.query(
            name="databricks-claude-sonnet-4-6",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_img}"}
                        },
                        {
                            "type": "text",
                            "text": VISION_PROMPT
                        }
                    ]
                }
            ],
            max_tokens=1024
        )

        raw = response.choices[0].message.content

        # Parse JSON from response
        text = raw
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.split("```")[0]

        parsed = json.loads(text)

        results.append({
            "filename": filename,
            "patent": patent,
            "title": title,
            "category": category,
            "extracted_components": parsed.get("extracted_components", []),
            "extracted_specs": parsed.get("extracted_specs", {}),
            "system_area": parsed.get("system_area", "unknown"),
            "description_text": parsed.get("description_text", ""),
            "data_keywords": parsed.get("data_keywords", []),
        })

        print(f"  Components: {parsed.get('extracted_components', [])[:5]}")
        print(f"  System area: {parsed.get('system_area', '?')}")
        print(f"  Keywords: {parsed.get('data_keywords', [])[:5]}")

    except Exception as e:
        print(f"  ERROR: {e}")
        # Fallback: use existing metadata
        results.append({
            "filename": filename,
            "patent": patent,
            "title": title,
            "category": category,
            "extracted_components": [],
            "extracted_specs": {},
            "system_area": category.lower().replace(" ", "_"),
            "description_text": meta.get('description', '') if isinstance(meta, dict) else getattr(meta, 'description', ''),
            "data_keywords": ["thermal", "cooling", "battery", "temperature"],
        })

    # Rate limiting
    time.sleep(0.5)

print(f"\nAnalyzed {len(results)} drawings")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Generate embeddings for each drawing description

# COMMAND ----------

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

for i, result in enumerate(results):
    desc = result["description_text"]
    keywords = " ".join(result.get("data_keywords", []))
    components = " ".join(result.get("extracted_components", []))

    # Combine all text for a rich embedding
    embed_text = f"{desc} Components: {components} Keywords: {keywords}"

    if not embed_text.strip():
        embed_text = f"{result['title']} {result['category']} engineering drawing"

    try:
        resp = w.serving_endpoints.query(
            name="databricks-gte-large-en",
            input=[embed_text]
        )
        result["embedding"] = resp.data[0].embedding
        print(f"[{i+1}/{len(results)}] {result['filename']}: embedding dim={len(result['embedding'])}")
    except Exception as e:
        print(f"[{i+1}/{len(results)}] {result['filename']}: embedding FAILED ({e})")
        result["embedding"] = None

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Write results to Delta table

# COMMAND ----------

from pyspark.sql import Row
from pyspark.sql.types import *

schema_def = StructType([
    StructField("filename", StringType()),
    StructField("patent", StringType()),
    StructField("title", StringType()),
    StructField("category", StringType()),
    StructField("extracted_components", ArrayType(StringType())),
    StructField("extracted_specs", MapType(StringType(), StringType())),
    StructField("system_area", StringType()),
    StructField("description_text", StringType()),
    StructField("data_keywords", ArrayType(StringType())),
    StructField("embedding", ArrayType(DoubleType())),
])

rows = []
for r in results:
    rows.append(Row(
        filename=r["filename"],
        patent=r["patent"],
        title=r["title"],
        category=r["category"],
        extracted_components=r["extracted_components"],
        extracted_specs=r["extracted_specs"],
        system_area=r["system_area"],
        description_text=r["description_text"],
        data_keywords=r["data_keywords"],
        embedding=r.get("embedding"),
    ))

df = spark.createDataFrame(rows, schema=schema_def)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn("drawing_analysis"))

count = spark.table(fqn("drawing_analysis")).count()
print(f"\nSaved {count} drawing analyses to {fqn('drawing_analysis')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Create Vector Search Index
# MAGIC
# MAGIC The Vector Search index auto-syncs from the Delta table.
# MAGIC When new drawings are analyzed (via upload), they're inserted into the table
# MAGIC and the index updates automatically.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

VS_ENDPOINT = "denso_drawings_vs"
VS_INDEX = f"{catalog}.{schema}.drawing_analysis_index"

# Create Vector Search endpoint (if not exists)
try:
    w.vector_search_endpoints.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")
    print(f"Created Vector Search endpoint: {VS_ENDPOINT}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Vector Search endpoint {VS_ENDPOINT} already exists")
    else:
        print(f"Endpoint creation: {e}")

# COMMAND ----------

import time

# Wait for endpoint to be ready
for _ in range(30):
    try:
        ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
        status = ep.endpoint_status.state.value if ep.endpoint_status else "UNKNOWN"
        print(f"Endpoint status: {status}")
        if status == "ONLINE":
            break
    except Exception as e:
        print(f"Waiting for endpoint... ({e})")
    time.sleep(10)

# COMMAND ----------

# Create Delta Sync index — auto-updates when drawing_analysis table changes
source_table = f"{catalog}.{schema}.drawing_analysis"
try:
    w.vector_search_indexes.create_index(
        name=VS_INDEX,
        endpoint_name=VS_ENDPOINT,
        primary_key="filename",
        index_type="DELTA_SYNC",
        delta_sync_index_spec={
            "source_table": source_table,
            "pipeline_type": "TRIGGERED",
            "embedding_source_columns": [
                {
                    "name": "description_text",
                    "embedding_model_endpoint_name": "databricks-gte-large-en"
                }
            ],
        },
    )
    print(f"Created Vector Search index: {VS_INDEX}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Vector Search index {VS_INDEX} already exists")
    else:
        print(f"Index creation: {e}")
        # Fallback: try with pre-computed embeddings
        try:
            w.vector_search_indexes.create_index(
                name=VS_INDEX,
                endpoint_name=VS_ENDPOINT,
                primary_key="filename",
                index_type="DELTA_SYNC",
                delta_sync_index_spec={
                    "source_table": source_table,
                    "pipeline_type": "TRIGGERED",
                    "embedding_vector_columns": [
                        {
                            "name": "embedding",
                            "embedding_dimension": len(results[0].get("embedding", [])) if results and results[0].get("embedding") else 1024,
                        }
                    ],
                },
            )
            print(f"Created Vector Search index (pre-computed embeddings): {VS_INDEX}")
        except Exception as e2:
            print(f"Fallback index creation: {e2}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Verify

# COMMAND ----------

print("=== Drawing Analysis Table ===")
display(spark.sql(f"""
    SELECT filename, system_area,
           size(extracted_components) as num_components,
           size(data_keywords) as num_keywords,
           CASE WHEN embedding IS NOT NULL THEN size(embedding) ELSE 0 END as embedding_dim
    FROM {fqn('drawing_analysis')}
"""))

# COMMAND ----------

# Test a vector search query
try:
    search_results = w.vector_search_indexes.query_index(
        index_name=VS_INDEX,
        columns=["filename", "title", "system_area", "description_text"],
        query_text="battery thermal cooling temperature uniformity",
        num_results=3,
    )
    print("=== Vector Search Test: 'battery thermal cooling temperature' ===")
    for r in search_results.result.data_array:
        print(f"  {r[0]:40s} | {r[2]:25s} | score={r[-1]:.3f}" if len(r) > 3 else f"  {r}")
except Exception as e:
    print(f"Vector search test: {e}")
    print("(Index may still be syncing — this is expected for first run)")
