"""TIGGE (ECDS) ve Hugging Face hesaplarını anahtarları yazdırmadan denetler (Faz 4 ön koşulu).

    docker compose run --rm --no-deps worker python -m hava.ops.accounts_check

Yalnız kimlik ve erişim uçlarını çağırır, veri indirmez. Çıktıda anahtar değeri yer almaz.
Uçlar ``ecmwf-datastores-client`` (``Profile``) ve ``huggingface_hub`` kaynak kodundan alındı.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx

from hava.settings import get_settings

ECDS_DEFAULT_URL = "https://ecds.ecmwf.int/api"
HF_BASE = "https://huggingface.co"
HF_DATASETS = ("openclimatefix/dwd-icon-eu", "openclimatefix/dwd-icon-global")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def check_ecds(client: httpx.Client, url: str, key: str) -> list[Check]:
    """Anahtar geçerli mi, TIGGE lisansı kabul edilmiş mi."""
    if not key:
        return [Check("ECDS anahtarı", False, "ECMWF_DATASTORES_KEY boş")]
    base = f"{url.rstrip('/')}/profiles/v1/account"
    headers = {"PRIVATE-TOKEN": key}
    auth = client.post(f"{base}/verification/pat", headers=headers)
    if auth.status_code != 200:
        return [Check("ECDS anahtarı", False, f"HTTP {auth.status_code}")]
    checks = [Check("ECDS anahtarı", True, "geçerli")]
    licences = client.get(f"{base}/licences", headers=headers)
    if licences.status_code != 200:
        return [*checks, Check("TIGGE lisansı", False, f"HTTP {licences.status_code}")]
    accepted = any("tigge" in str(x.get("id")) for x in licences.json().get("licences", []))
    detail = "kabul edilmiş" if accepted else "kabul edilmemiş (Download sekmesinin en altı)"
    return [*checks, Check("TIGGE lisansı", accepted, detail)]


def check_hf(client: httpx.Client, token: str, base: str = HF_BASE) -> list[Check]:
    """Token geçerli mi, gated veri kümelerine erişim açılmış mı."""
    if not token:
        return [Check("HF token", False, "HF_TOKEN boş")]
    headers = {"Authorization": f"Bearer {token}"}
    who = client.get(f"{base}/api/whoami-v2", headers=headers)
    if who.status_code != 200:
        return [Check("HF token", False, f"HTTP {who.status_code}")]
    checks = [Check("HF token", True, "geçerli")]
    for repo in HF_DATASETS:
        status = client.get(f"{base}/api/datasets/{repo}/auth-check", headers=headers).status_code
        detail = "erişim var" if status == 200 else f"erişim yok (HTTP {status})"
        checks.append(Check(repo, status == 200, detail))
    return checks


def main() -> int:
    headers = {"User-Agent": get_settings().http_user_agent}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        checks = [
            *check_ecds(
                client,
                os.environ.get("ECMWF_DATASTORES_URL") or ECDS_DEFAULT_URL,
                os.environ.get("ECMWF_DATASTORES_KEY", ""),
            ),
            *check_hf(client, os.environ.get("HF_TOKEN", "")),
        ]
    for c in checks:
        sys.stdout.write(f"{'tamam' if c.ok else 'EKSİK'}  {c.name}: {c.detail}\n")
    return 0 if all(c.ok for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
