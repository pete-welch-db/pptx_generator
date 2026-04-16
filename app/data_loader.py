"""
Data loader for Databricks gold tables and UC Volumes.
Reads engineering data from Delta tables and patent drawings from volumes.
"""

import os
from io import BytesIO

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks import sql as dbsql


def _get_catalog() -> str:
    return os.environ.get("CATALOG", "main")


def _get_schema() -> str:
    return os.environ.get("SCHEMA", "denso_demo")


def _fqn(table: str) -> str:
    """Fully-qualified table name."""
    return f"`{_get_catalog()}`.`{_get_schema()}`.`{table}`"


def _volume_path() -> str:
    return f"/Volumes/{_get_catalog()}/{_get_schema()}/engineering_drawings"


# ---------------------------------------------------------------------------
# SQL connection (for gold tables and ai_query)
# ---------------------------------------------------------------------------

def get_connection():
    """Create a Databricks SQL connection using SDK credentials."""
    w = WorkspaceClient()
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
    hostname = w.config.host.replace("https://", "").replace("http://", "")

    # Extract bearer token from SDK auth headers
    headers = w.config.authenticate()
    token = headers.get("Authorization", "").replace("Bearer ", "")

    return dbsql.connect(
        server_hostname=hostname,
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        access_token=token,
    )


# ---------------------------------------------------------------------------
# Gold table readers
# ---------------------------------------------------------------------------

def read_thermal_sensors() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(f"SELECT * FROM {_fqn('thermal_sensor_readings')}", conn)


def read_test_results() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(f"SELECT * FROM {_fqn('component_test_results')}", conn)


def read_manufacturing_quality() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(f"SELECT * FROM {_fqn('manufacturing_quality')}", conn)


def read_durability_cycling() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(f"SELECT * FROM {_fqn('durability_cycling')}", conn)


def read_component_specs() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(f"SELECT * FROM {_fqn('component_specs')}", conn)


def read_jira_issues(gate_review: str | None = None) -> pd.DataFrame:
    """Read Jira issues, optionally filtered by gate review type."""
    where = ""
    if gate_review:
        where = f" WHERE gate_review LIKE '%{gate_review}%'"
    with get_connection() as conn:
        return pd.read_sql(f"SELECT * FROM {_fqn('jira_issues')}{where}", conn)


def read_confluence_pages(gate_review: str | None = None) -> pd.DataFrame:
    """Read Confluence pages, optionally filtered by gate review type."""
    where = ""
    if gate_review:
        where = f" WHERE gate_review LIKE '%{gate_review}%'"
    with get_connection() as conn:
        return pd.read_sql(f"SELECT * FROM {_fqn('confluence_pages')}{where}", conn)


def get_data_summary() -> dict:
    """Quick summary stats for the sidebar."""
    with get_connection() as conn:
        cursor = conn.cursor()
        counts = {}
        for tbl in [
            "thermal_sensor_readings",
            "component_test_results",
            "manufacturing_quality",
            "durability_cycling",
        ]:
            cursor.execute(f"SELECT COUNT(*) FROM {_fqn(tbl)}")
            counts[tbl] = cursor.fetchone()[0]
        return counts


# ---------------------------------------------------------------------------
# UC Volume — engineering drawings
# ---------------------------------------------------------------------------

def list_drawings() -> list[dict]:
    """List PNG files in the engineering_drawings volume.

    Returns list of dicts: {'name': filename, 'path': full volume path}
    """
    w = WorkspaceClient()
    vol = _volume_path()
    try:
        entries = list(w.files.list_directory_contents(vol))
        return [
            {"name": e.name, "path": f"{vol}/{e.name}"}
            for e in entries
            if e.name.lower().endswith((".png", ".jpg", ".jpeg"))
        ]
    except Exception:
        return []


def read_drawing(path: str) -> bytes:
    """Read a drawing file from the UC Volume."""
    w = WorkspaceClient()
    resp = w.files.download(path)
    return resp.contents.read()


def upload_drawing(name: str, content: bytes):
    """Upload a drawing to the UC Volume."""
    w = WorkspaceClient()
    vol = _volume_path()
    w.files.upload(f"{vol}/{name}", BytesIO(content), overwrite=True)
