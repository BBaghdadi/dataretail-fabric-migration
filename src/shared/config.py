"""
config.py
---------
Configuration centralisée du projet.
Toutes les constantes et paramètres en un seul endroit.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Chemins ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
SEEDS_DIR    = DATA_DIR / "seeds" / "output"
LOGS_DIR     = PROJECT_ROOT / "logs"

# ── GCP ───────────────────────────────────────────────────────────────────────
GCP_PROJECT_ID  = os.getenv("GCP_PROJECT_ID", "dataretail-migration")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "dataretail-migration-source")

# ── GCS Paths ─────────────────────────────────────────────────────────────────
GCS_PATHS = {
    "customers"   : "raw/customers/customers.csv",
    "orders"      : "raw/orders/orders.csv",
    "order_items" : "raw/orders/order_items.csv",
    "products"    : "raw/products/products.json",
    "bq_summary"  : "exports/bigquery/bq_sales_summary.parquet",
}

# ── Bronze ────────────────────────────────────────────────────────────────────
BRONZE_TABLES = {
    "customers"   : "bronze_customers",
    "orders"      : "bronze_orders",
    "order_items" : "bronze_order_items",
    "products"    : "bronze_products",
    "bq_summary"  : "bronze_bq_summary",
}

QUARANTINE_DIR = DATA_DIR / "quarantine"

# ── Validation basique Bronze ─────────────────────────────────────────────────
BRONZE_VALIDATION = {
    "customers": {
        "required_columns": [
            "customer_id", "email", "first_name",
            "last_name", "created_at"
        ],
        "min_rows": 1000,
    },
    "orders": {
        "required_columns": [
            "order_id", "customer_id",
            "order_date", "total_amount_eur", "status"
        ],
        "min_rows": 10000,
    },
    "order_items": {
        "required_columns": [
            "item_id", "order_id",
            "product_id", "quantity", "unit_price_eur"
        ],
        "min_rows": 10000,
    },
}

# ── Microsoft Fabric / OneLake ────────────────────────────────────────────────
FABRIC_WORKSPACE_NAME        = os.getenv("FABRIC_WORKSPACE_NAME", "DataRetail-DEV")
FABRIC_BRONZE_LAKEHOUSE_NAME = os.getenv("FABRIC_BRONZE_LAKEHOUSE_NAME", "LH_Bronze")
FABRIC_SILVER_LAKEHOUSE_NAME = os.getenv("FABRIC_SILVER_LAKEHOUSE_NAME", "LH_Silver")
FABRIC_GOLD_LAKEHOUSE_NAME   = os.getenv("FABRIC_GOLD_LAKEHOUSE_NAME",   "LH_Gold")
ONELAKE_ENDPOINT             = os.getenv("ONELAKE_ENDPOINT", "https://onelake.dfs.fabric.microsoft.com")