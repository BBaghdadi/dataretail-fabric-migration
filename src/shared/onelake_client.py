"""
onelake_client.py
-----------------
Client OneLake via ADLS Gen2.
Utilise les noms workspace/lakehouse (requis sur tenant M365 Developer).
"""

import io
import logging
import requests

import pandas as pd
from azure.identity import InteractiveBrowserCredential

logger = logging.getLogger(__name__)

STORAGE_SCOPE = "https://storage.azure.com/.default"


class OneLakeClient:

    def __init__(self, workspace_name: str, lakehouse_name: str):
        self.workspace_name = workspace_name
        self.lakehouse_name = lakehouse_name
        self._credential    = None

    def connect(self) -> None:
        logger.info("Connexion OneLake - authentification Microsoft...")
        self._credential = InteractiveBrowserCredential()
        self._credential.get_token(STORAGE_SCOPE)
        logger.info("[OK] Connexion OneLake etablie")

    def _get_headers(self, extra: dict = None) -> dict:
        token   = self._credential.get_token(STORAGE_SCOPE).token
        headers = {
            "Authorization" : f"Bearer {token}",
            "x-ms-version"  : "2023-11-03",
        }
        if extra:
            headers.update(extra)
        return headers

    def _build_url(self, folder: str, filename: str) -> str:
        return (
            f"https://onelake.dfs.fabric.microsoft.com"
            f"/{self.workspace_name}"
            f"/{self.lakehouse_name}.Lakehouse"
            f"/Files/{folder}/{filename}"
        )

    def write_parquet(
        self,
        df: pd.DataFrame,
        folder: str,
        filename: str,
    ) -> str:
        """Ecrit un DataFrame Parquet dans OneLake en 3 etapes ADLS Gen2."""
        if self._credential is None:
            raise RuntimeError("Client non connecte — appelle connect() d'abord")

        # Serialiser
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False, engine="pyarrow")
        buffer.seek(0)
        data   = buffer.read()
        length = len(data)

        url = self._build_url(folder, filename)
        logger.info(f"  Cible  : {url}")
        logger.info(f"  Taille : {length/1024:.1f} KB")

        # Etape 1 — Creer le fichier
        r1 = requests.put(
            url,
            headers=self._get_headers(),
            params={"resource": "file"},
        )
        if r1.status_code not in [200, 201, 409]:
            raise Exception(f"Creation fichier echouee : {r1.status_code} - {r1.text[:300]}")
        logger.info(f"  [OK] Fichier cree (status {r1.status_code})")

        # Etape 2 — Uploader le contenu
        r2 = requests.patch(
            url,
            headers=self._get_headers({
                "Content-Type"   : "application/octet-stream",
                "Content-Length" : str(length),
            }),
            params={"action": "append", "position": "0"},
            data=data,
        )
        if r2.status_code not in [200, 202]:
            raise Exception(f"Upload contenu echoue : {r2.status_code} - {r2.text[:300]}")
        logger.info(f"  [OK] Contenu uploade (status {r2.status_code})")

        # Etape 3 — Finaliser
        r3 = requests.patch(
            url,
            headers=self._get_headers(),
            params={"action": "flush", "position": str(length)},
        )
        if r3.status_code not in [200, 202]:
            raise Exception(f"Flush echoue : {r3.status_code} - {r3.text[:300]}")
        logger.info(f"  [OK] Fichier finalise (status {r3.status_code})")

        full_path = (
            f"onelake://{self.workspace_name}"
            f"/{self.lakehouse_name}.Lakehouse"
            f"/Files/{folder}/{filename}"
        )
        return full_path