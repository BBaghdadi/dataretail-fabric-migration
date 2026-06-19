"""
generate_sources.py
-------------------
Génère les données sources simulant un environnement e-commerce existant.

Sources simulées :
    - Salesforce CRM  → customers.csv
    - Oracle ERP      → orders.csv
    - SAP SD          → order_items.csv
    - Catalogue       → products.json
    - Export BigQuery → bq_sales_summary.parquet

Auteur  : DataRetail Migration Project
Version : 1.0.0
Sprint  : 1 — Fondations
"""

import os
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
from faker import Faker
from dotenv import load_dotenv

# ── Chargement des variables d'environnement ──────────────────────────────────
load_dotenv()

# ── Configuration du logger ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
SEED         = 42
N_CUSTOMERS  = 5_000
N_ORDERS     = 50_000
N_PRODUCTS   = 200

random.seed(SEED)
np.random.seed(SEED)
fake = Faker("fr_FR")
Faker.seed(SEED)

OUTPUT_DIR = Path("data/seeds/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATE_START = datetime(2022, 1, 1)
DATE_END   = datetime(2024, 12, 31)

CATEGORIES = [
    "Électronique", "Vêtements", "Alimentation",
    "Maison & Jardin", "Sport & Loisirs", "Beauté & Santé",
    "Livres & Médias", "Jouets & Jeux",
]
STATUSES        = ["pending", "confirmed", "shipped", "delivered", "cancelled", "refunded"]
STATUS_WEIGHTS  = [0.05, 0.10, 0.20, 0.50, 0.10, 0.05]
PAYMENT_METHODS = ["credit_card", "paypal", "bank_transfer", "voucher"]
CHANNELS        = ["web", "mobile_app", "marketplace", "telephone"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def introduce_nulls(df: pd.DataFrame, col: str, rate: float = 0.02) -> pd.DataFrame:
    """Introduit des nulls intentionnels pour simuler des données réelles imparfaites."""
    mask = np.random.rand(len(df)) < rate
    df.loc[mask, col] = np.nan
    return df


# ── Générateurs ───────────────────────────────────────────────────────────────

def generate_customers() -> pd.DataFrame:
    logger.info("Génération des clients (simulation Salesforce CRM)...")
    records = []

    for i in range(N_CUSTOMERS):
        created_at = random_date(DATE_START, DATE_END)
        country = random.choices(
            ["FR", "BE", "CH", "LU", "DE", "ES", "IT"],
            weights=[60, 10, 8, 4, 8, 5, 5],
        )[0]

        records.append({
            "customer_id"        : f"CUS-{i+1:06d}",
            "salesforce_id"      : fake.uuid4(),
            "first_name"         : fake.first_name(),
            "last_name"          : fake.last_name(),
            "email"              : fake.email(),
            "phone"              : fake.phone_number(),
            "address_street"     : fake.street_address(),
            "address_city"       : fake.city(),
            "address_zip"        : fake.postcode(),
            "country_code"       : country,
            "customer_segment"   : random.choices(
                                     ["Bronze", "Silver", "Gold", "Platinum"],
                                     weights=[50, 30, 15, 5]
                                   )[0],
            "acquisition_channel": random.choice(
                                     ["organic", "paid_search", "social", "referral", "email"]
                                   ),
            "newsletter_opt_in"  : random.choice([True, False]),
            "created_at"         : created_at.isoformat(),
            "updated_at"         : (created_at + timedelta(
                                     days=random.randint(0, 365)
                                   )).isoformat(),
        })

    df = pd.DataFrame(records)

    # Problèmes qualité intentionnels — seront corrigés en Silver
    df = introduce_nulls(df, "phone", rate=0.08)
    df = introduce_nulls(df, "email", rate=0.02)

    # Doublons intentionnels (même email, customer_id différent)
    n_dup = 50
    dups  = df.sample(n=n_dup, random_state=SEED).copy()
    dups["customer_id"] = [f"CUS-DUP-{i:04d}" for i in range(n_dup)]
    df = pd.concat([df, dups], ignore_index=True)

    logger.info(f"  → {len(df):,} clients ({n_dup} doublons intentionnels)")
    return df


def generate_products() -> pd.DataFrame:
    logger.info("Génération des produits (simulation catalogue SAP)...")
    records = []

    for i in range(N_PRODUCTS):
        category   = random.choice(CATEGORIES)
        cost_price = round(random.uniform(2.0, 500.0), 2)
        margin     = random.uniform(0.15, 0.60)

        records.append({
            "product_id"     : f"PRD-{i+1:05d}",
            "sku"            : fake.bothify(text="??-####-??").upper(),
            "product_name"   : fake.catch_phrase(),
            "category"       : category,
            "brand"          : fake.company(),
            "cost_price_eur" : cost_price,
            "sell_price_eur" : round(cost_price * (1 + margin), 2),
            "margin_pct"     : round(margin * 100, 2),
            "stock_quantity" : random.randint(0, 500),
            "weight_kg"      : round(random.uniform(0.1, 20.0), 3),
            "is_active"      : random.choices([True, False], weights=[85, 15])[0],
            "supplier_id"    : f"SUP-{random.randint(1, 50):03d}",
            "created_at"     : random_date(DATE_START, DATE_END).isoformat(),
        })

    df = pd.DataFrame(records)
    df = introduce_nulls(df, "brand", rate=0.05)
    logger.info(f"  → {len(df):,} produits")
    return df


def generate_orders(customer_ids: list) -> pd.DataFrame:
    logger.info("Génération des commandes (simulation Oracle ERP)...")
    records = []

    for i in range(N_ORDERS):
        order_date   = random_date(DATE_START, DATE_END)
        status       = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        shipped_at   = None
        delivered_at = None

        if status in ["shipped", "delivered"]:
            shipped_at = order_date + timedelta(days=random.randint(1, 3))
        if status == "delivered":
            delivered_at = shipped_at + timedelta(days=random.randint(1, 7))

        total_amount = round(random.uniform(5.0, 2000.0), 2)
        discount_pct = random.choices([0, 5, 10, 15, 20], weights=[50, 20, 15, 10, 5])[0]
        discount_amt = round(total_amount * discount_pct / 100, 2)

        records.append({
            "order_id"           : f"ORD-{i+1:08d}",
            "oracle_order_num"   : f"SO-{random.randint(100000, 999999)}",
            "customer_id"        : random.choice(customer_ids),
            "order_date"         : order_date.date().isoformat(),
            "order_datetime"     : order_date.isoformat(),
            "status"             : status,
            "channel"            : random.choice(CHANNELS),
            "payment_method"     : random.choice(PAYMENT_METHODS),
            "total_amount_eur"   : total_amount,
            "discount_pct"       : discount_pct,
            "discount_amount_eur": discount_amt,
            "net_amount_eur"     : round(total_amount - discount_amt, 2),
            "shipping_cost_eur"  : round(random.uniform(0, 15.0), 2),
            "currency"           : "EUR",
            "warehouse_id"       : f"WH-{random.randint(1, 5):02d}",
            "shipped_at"         : shipped_at.isoformat() if shipped_at else None,
            "delivered_at"       : delivered_at.isoformat() if delivered_at else None,
            "created_at"         : order_date.isoformat(),
        })

    df = pd.DataFrame(records)
    df = introduce_nulls(df, "shipping_cost_eur", rate=0.03)

    # Montants négatifs intentionnels — erreurs ERP à corriger en Silver
    neg_mask = np.random.rand(len(df)) < 0.005
    df.loc[neg_mask, "total_amount_eur"] *= -1

    logger.info(f"  → {len(df):,} commandes")
    return df


def generate_order_items(order_ids: list, product_ids: list) -> pd.DataFrame:
    logger.info("Génération des lignes de commande (simulation SAP SD)...")
    records     = []
    item_counter = 0

    for order_id in order_ids:
        n_items  = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5])[0]
        products = random.sample(product_ids, min(n_items, len(product_ids)))

        for product_id in products:
            item_counter += 1
            qty        = random.randint(1, 10)
            unit_price = round(random.uniform(5.0, 500.0), 2)

            records.append({
                "item_id"        : f"ITM-{item_counter:010d}",
                "order_id"       : order_id,
                "product_id"     : product_id,
                "quantity"       : qty,
                "unit_price_eur" : unit_price,
                "line_total_eur" : round(qty * unit_price, 2),
                "tax_rate_pct"   : random.choice([5.5, 10.0, 20.0]),
                "return_qty"     : random.choices([0, 1], weights=[95, 5])[0],
                "sap_line_num"   : item_counter,
            })

    df = pd.DataFrame(records)
    logger.info(f"  → {len(df):,} lignes de commande")
    return df


def generate_bq_summary(orders_df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Génération du résumé BigQuery (simulation export DWH existant)...")

    orders_df["order_date"] = pd.to_datetime(orders_df["order_date"])
    orders_df["year_month"] = orders_df["order_date"].dt.to_period("M").astype(str)

    summary = (
        orders_df[orders_df["status"] == "delivered"]
        .groupby("year_month")
        .agg(
            total_orders      =("order_id",          "count"),
            total_revenue_eur =("net_amount_eur",     "sum"),
            avg_order_value   =("net_amount_eur",     "mean"),
            total_discount_eur=("discount_amount_eur","sum"),
        )
        .reset_index()
        .round(2)
    )
    summary["bq_load_timestamp"] = datetime.now().isoformat()
    summary["bq_table_name"]     = "dataretail_dw.fact_monthly_sales"

    logger.info(f"  → {len(summary):,} lignes résumé mensuel")
    return summary


# ── Sauvegarde locale ─────────────────────────────────────────────────────────

def save(df: pd.DataFrame, filename: str, fmt: str = "csv") -> Path:
    path = OUTPUT_DIR / filename
    if fmt == "csv":
        df.to_csv(path, index=False, encoding="utf-8")
    elif fmt == "parquet":
        df.to_parquet(path, index=False, engine="pyarrow")
    elif fmt == "json":
        df.to_json(path, orient="records", indent=2, force_ascii=False)
    size_kb = path.stat().st_size / 1024
    logger.info(f"  ✓ {filename} ({size_kb:.1f} KB)")
    return path


# ── Upload GCS ────────────────────────────────────────────────────────────────

def upload_to_gcs(local_path: Path, gcs_path: str) -> None:
    bucket_name = os.getenv("GCS_BUCKET_NAME", "dataretail-migration-source")
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob   = bucket.blob(gcs_path)
        blob.upload_from_filename(str(local_path))
        logger.info(f"  ✓ GCS : gs://{bucket_name}/{gcs_path}")
    except ImportError:
        logger.warning("  ⚠ google-cloud-storage non installé — upload ignoré")
    except Exception as e:
        logger.error(f"  ✗ Erreur upload GCS : {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 55)
    logger.info("DataRetail — Génération des données sources")
    logger.info("Sprint 1 · Fondations")
    logger.info("=" * 55)

    # 1. Clients
    customers_df = generate_customers()
    p = save(customers_df, "customers.csv")
    upload_to_gcs(p, "raw/customers/customers.csv")

    # 2. Produits
    products_df = generate_products()
    p = save(products_df, "products.json", fmt="json")
    upload_to_gcs(p, "raw/products/products.json")

    # 3. Commandes
    customer_ids = customers_df["customer_id"].tolist()
    orders_df    = generate_orders(customer_ids)
    p = save(orders_df, "orders.csv")
    upload_to_gcs(p, "raw/orders/orders.csv")

    # 4. Lignes de commande
    order_ids   = orders_df["order_id"].tolist()
    product_ids = products_df["product_id"].tolist()
    items_df    = generate_order_items(order_ids, product_ids)
    p = save(items_df, "order_items.csv")
    upload_to_gcs(p, "raw/orders/order_items.csv")

    # 5. Résumé BigQuery
    bq_df = generate_bq_summary(orders_df)
    p = save(bq_df, "bq_sales_summary.parquet", fmt="parquet")
    upload_to_gcs(p, "exports/bigquery/bq_sales_summary.parquet")

    # ── Rapport final ──────────────────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("RAPPORT DE GÉNÉRATION")
    logger.info("=" * 55)
    logger.info(f"Clients       : {len(customers_df):>10,} lignes")
    logger.info(f"Produits      : {len(products_df):>10,} lignes")
    logger.info(f"Commandes     : {len(orders_df):>10,} lignes")
    logger.info(f"Lignes cmde   : {len(items_df):>10,} lignes")
    logger.info(f"Résumé BQ     : {len(bq_df):>10,} lignes")
    logger.info(f"Fichiers dans : {OUTPUT_DIR.resolve()}")
    logger.info("Génération terminée avec succès ✓")


if __name__ == "__main__":
    main()