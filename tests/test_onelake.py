import os
import io
import requests
import pandas as pd
from dotenv import load_dotenv
from azure.identity import InteractiveBrowserCredential

load_dotenv()

SCOPE = "https://storage.azure.com/.default"

cred    = InteractiveBrowserCredential()
token   = cred.get_token(SCOPE).token
headers = {
    "Authorization" : f"Bearer {token}",
    "x-ms-version"  : "2023-11-03",
}

# Creer un petit fichier test
df   = pd.DataFrame({"test": [1, 2, 3]})
buf  = io.BytesIO()
df.to_parquet(buf, index=False)
buf.seek(0)
data = buf.read()

# Essai avec les NOMS (pas les GUIDs)
url = (
    "https://onelake.dfs.fabric.microsoft.com"
    "/DataRetail-DEV"          
    "/LH_Bronze.Lakehouse"     
    "/Files/test/test_connexion.parquet"
)

print(f"URL : {url}")

r1 = requests.put(url, headers=headers, params={"resource": "file"})
print(f"PUT  (create) : {r1.status_code} - {r1.text[:200]}")

if r1.status_code in [200, 201, 409]:
    r2 = requests.patch(
        url,
        headers={**headers, "Content-Type": "application/octet-stream"},
        params={"action": "append", "position": "0"},
        data=data,
    )
    print(f"PATCH (append): {r2.status_code} - {r2.text[:200]}")

    r3 = requests.patch(
        url,
        headers=headers,
        params={"action": "flush", "position": str(len(data))},
    )
    print(f"PATCH (flush) : {r3.status_code}")

    if r3.status_code in [200, 202]:
        print("[OK] Fichier ecrit dans OneLake !")
    else:
        print(f"[ERR] {r3.text[:300]}")