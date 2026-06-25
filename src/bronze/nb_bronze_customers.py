"""
nb_bronze_customers.py
----------------------
Ingestion des données clients depuis GCS vers LH_Bronze (Delta Lake).

Source  : gs://dataretail-migration-source/raw/customers/customers.csv
Cible   : LH_Bronze/Tables/bronze_customers (Delta)

Règles Bronze :
    - Aucune transformation métier
    - Ajout de métadonnées techniques uniquement
    - Données invalides → quarantaine (jamais perdues)
    - Logs structurés à chaque étape

Sprint  : 2 — Couche Bronze
"""

import hashlib
import io
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
from google.cloud import storage

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append(str(Path(__file__).parent.parent))
from shared.config import (
    GCP_PROJECT_ID,
    GCS_BUCKET_NAME,
    GCS_PATHS,
    BRONZE_VALIDATION,
    QUARANTINE_DIR,
)
from shared.logger import get_logger

# ── Init ──────────────────────────────────────────────────────────────────────
logger    = get_logger("bronze.customers", log_file="bronze_customers.log")
ENTITY    = "customers"
LOAD_TS   = datetime.now(timezone.utc).isoformat()
RUN_ID    = datetime.now().strftime("%Y%m%d_%H%M%S")


# ── Helpers ───────────────────────────────────────────────────────────────────

def compute_row_hash(row: pd.Series) -> str:
    """Hash MD5 de la ligne pour détecter les doublons exacts en Silver."""
    content = "|".join(str(v) for v in row.values)
    return hashlib.md5(content.encode()).hexdigest()


def add_bronze_metadata(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """
    Ajoute les colonnes techniques Bronze.
    Ces colonnes permettent la traçabilité complète jusqu'à la source.
    """
    df["_bronze_loaded_at"] = LOAD_TS
    df["_source_file"]      = source_file
    df["_run_id"]           = RUN_ID
    df["_row_hash"]         = df.apply(compute_row_hash, axis=1)
    df["_row_number"]       = range(1, len(df) + 1)
    return df


def send_to_quarantine(df: pd.DataFrame, reason: str) -> None:
    """Sauvegarde les lignes rejetées dans le dossier quarantaine."""
    if df.empty:
        return
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    path = QUARANTINE_DIR / f"{ENTITY}_{RUN_ID}_quarantine.csv"
    df["_quarantine_reason"] = reason
    df["_quarantine_ts"]     = LOAD_TS
    df.to_csv(path, index=False)
    logger.warning(f"  ⚠ {len(df):,} lignes en quarantaine → {path}")


# ── Étape 1 : Lecture depuis GCS ──────────────────────────────────────────────

def read_from_gcs() -> pd.DataFrame:
    logger.info("=" * 55)
    logger.info(f"Démarrage ingestion Bronze — {ENTITY.upper()}")
    logger.info(f"Run ID : {RUN_ID}")
    logger.info("=" * 55)
    logger.info("Étape 1 — Lecture depuis GCS...")

    gcs_path = GCS_PATHS[ENTITY]

    try:
        client  = storage.Client(project=GCP_PROJECT_ID)
        bucket  = client.bucket(GCS_BUCKET_NAME)
        blob    = bucket.blob(gcs_path)
        content = blob.download_as_bytes()
        df      = pd.read_csv(BytesIO(content), dtype=str)

        logger.info(f"  ✓ Fichier lu : gs://{GCS_BUCKET_NAME}/{gcs_path}")
        logger.info(f"  ✓ Dimensions : {df.shape[0]:,} lignes × {df.shape[1]} colonnes")
        return df, gcs_path

    except Exception as e:
        logger.error(f"  ✗ Erreur lecture GCS : {e}")
        raise


# ── Étape 2 : Validation basique Bronze ───────────────────────────────────────

def validate_bronze(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Validation MINIMALE en Bronze :
    - Colonnes requises présentes
    - Volume minimum respecté
    - Pas de validation métier (c'est le rôle de Silver)

    Retourne (df_valid, df_quarantine)
    """
    logger.info("Étape 2 — Validation basique Bronze...")

    rules      = BRONZE_VALIDATION[ENTITY]
    df_valid   = df.copy()
    df_quarant = pd.DataFrame()

    # Vérification colonnes requises
    required_cols = rules["required_columns"]
    missing_cols  = [c for c in required_cols if c not in df.columns]

    if missing_cols:
        logger.error(f"  ✗ Colonnes manquantes : {missing_cols}")
        raise ValueError(f"Schéma invalide — colonnes manquantes : {missing_cols}")

    logger.info(f"  ✓ Colonnes requises : OK ({len(required_cols)} vérifiées)")

    # Vérification volume minimum
    min_rows = rules["min_rows"]
    if len(df) < min_rows:
        logger.error(f"  ✗ Volume insuffisant : {len(df):,} < {min_rows:,}")
        raise ValueError(f"Volume insuffisant : {len(df):,} lignes reçues, minimum {min_rows:,}")

    logger.info(f"  ✓ Volume : {len(df):,} lignes (minimum {min_rows:,})")

    # Quarantaine : lignes sans customer_id (clé primaire indispensable)
    mask_no_id  = df["customer_id"].isna() | (df["customer_id"].str.strip() == "")
    df_quarant  = df[mask_no_id].copy()
    df_valid    = df[~mask_no_id].copy()

    if len(df_quarant) > 0:
        send_to_quarantine(df_quarant, reason="customer_id manquant")

    logger.info(f"  ✓ Lignes valides    : {len(df_valid):,}")
    logger.info(f"  ⚠ Lignes quarantaine: {len(df_quarant):,}")

    return df_valid, df_quarant


# ── Étape 3 : Ajout métadonnées et sauvegarde ─────────────────────────────────

def save_bronze_local(df: pd.DataFrame, source_file: str) -> None:
    """
    En local  : sauvegarde en Parquet (Delta simulé)
    Sur Fabric : écriture Delta via spark.write.format('delta')
    """
    logger.info("Étape 3 — Ajout métadonnées Bronze...")

    df = add_bronze_metadata(df, source_file)

    logger.info(f"  ✓ Métadonnées ajoutées : _bronze_loaded_at, _source_file, _run_id, _row_hash")
    logger.info(f"  ✓ Colonnes totales     : {df.shape[1]}")

    # ── Sauvegarde locale (simulation Delta) ──────────────────────────────────
    output_dir = Path("data/bronze")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"bronze_{ENTITY}.parquet"

    df.to_parquet(output_path, index=False, engine="pyarrow")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"  ✓ Sauvegardé en local : {output_path} ({size_mb:.2f} MB)")

    # ── Note Fabric ───────────────────────────────────────────────────────────
    # Sur Microsoft Fabric, remplacer par :
    # df_spark = spark.createDataFrame(df)
    # df_spark.write.format("delta").mode("overwrite") \
    #         .option("overwriteSchema", "true") \
    #         .saveAsTable("LH_Bronze.bronze_customers")

    return df

def save_bronze(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """
    Sauvegarde en deux endroits :
    1. Local  → data/bronze/bronze_customers.parquet  (tracabilite)
    2. Fabric → OneLake LH_Bronze/Files/bronze/       (production)
    """
    logger.info("Etape 3 - Ajout metadonnees Bronze...")
    df = add_bronze_metadata(df, source_file)
    logger.info(f"  [OK] Metadonnees ajoutees : {df.shape[1]} colonnes")

    # ── 1. Sauvegarde locale ──────────────────────────────────────────────────
    logger.info("Etape 4 - Sauvegarde locale...")
    output_dir  = Path("data/bronze")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"bronze_{ENTITY}.parquet"
    df.to_parquet(output_path, index=False, engine="pyarrow")
    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"  [OK] Local : {output_path} ({size_mb:.2f} MB)")

   # ── 2. Ecriture OneLake via API REST Fabric ───────────────────────────────────
    logger.info("Etape 5 - Ecriture sur Microsoft Fabric OneLake...")
    try:
        from shared.onelake_client import OneLakeClient
        from shared.config import (
         FABRIC_WORKSPACE_NAME,
         FABRIC_BRONZE_LAKEHOUSE_NAME,
        )

        client = OneLakeClient(
            workspace_name = FABRIC_WORKSPACE_NAME,
            lakehouse_name = FABRIC_BRONZE_LAKEHOUSE_NAME,
        )
        client.connect()

        path = client.write_parquet(
          df       = df,
          folder   = "customers",
          filename = f"bronze_customers_{RUN_ID}.parquet",
        )
        logger.info(f"  [OK] OneLake : {path}")

    except Exception as e:
      import traceback
      logger.error(f"  [ERR] Ecriture OneLake echouee : {e}")
      logger.error(traceback.format_exc())
      logger.warning("  Donnees sauvegardees en local uniquement")


    return df

# ── Étape 4 : Rapport de run ──────────────────────────────────────────────────

def print_report(df_raw, df_valid, df_quarant, df_bronze) -> None:
    logger.info("=" * 55)
    logger.info("RAPPORT D'INGESTION BRONZE — CUSTOMERS")
    logger.info("=" * 55)
    logger.info(f"Run ID          : {RUN_ID}")
    logger.info(f"Timestamp       : {LOAD_TS}")
    logger.info(f"Source          : gs://{GCS_BUCKET_NAME}/{GCS_PATHS[ENTITY]}")
    logger.info(f"Lignes lues     : {len(df_raw):,}")
    logger.info(f"Lignes valides  : {len(df_valid):,}")
    logger.info(f"Quarantaine     : {len(df_quarant):,}")
    logger.info(f"Colonnes Bronze : {df_bronze.shape[1]}")
    logger.info(f"Taux succès     : {len(df_valid)/len(df_raw)*100:.1f}%")
    logger.info("=" * 55)
    logger.info("Ingestion Bronze CUSTOMERS terminée ✓")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        # Étape 1 — Lecture GCS
        df_raw, source_file = read_from_gcs()

        # Étape 2 — Validation
        df_valid, df_quarant = validate_bronze(df_raw)

        # Étape 3 — Métadonnées + sauvegarde
        df_bronze = save_bronze(df_valid, source_file)

        # Étape 4 — Rapport
        print_report(df_raw, df_valid, df_quarant, df_bronze)

    except Exception as e:
        logger.error(f"ÉCHEC ingestion Bronze {ENTITY} : {e}")
        raise


if __name__ == "__main__":
    main()