"""Hesap denetimi: sahte HTTP yanıtlarıyla (ağ yok; anahtarlar sentetik)."""

import httpx

from hava.ops.accounts_check import HF_DATASETS, check_ecds, check_hf

FAKE_KEY = "sentetik-anahtar"
ECDS = "https://ecds.test/api"
HF = "https://hf.test"


def client_for(routes: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(request.url.path, httpx.Response(404))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ecds_missing_key_makes_no_request() -> None:
    checks = check_ecds(client_for({}), ECDS, "")
    assert [c.ok for c in checks] == [False] and "boş" in checks[0].detail


def test_ecds_rejected_key_stops_early() -> None:
    routes = {"/api/profiles/v1/account/verification/pat": httpx.Response(401)}
    checks = check_ecds(client_for(routes), ECDS, FAKE_KEY)
    assert len(checks) == 1 and not checks[0].ok and checks[0].detail == "HTTP 401"


def test_ecds_licence_accepted_or_not() -> None:
    def run(ids: list[str]) -> bool:
        routes = {
            "/api/profiles/v1/account/verification/pat": httpx.Response(200, json={}),
            "/api/profiles/v1/account/licences": httpx.Response(
                200, json={"licences": [{"id": i, "revision": 1} for i in ids]}
            ),
        }
        checks = check_ecds(client_for(routes), ECDS, FAKE_KEY)
        assert checks[0].ok
        return checks[1].ok

    assert run(["tigge-licence"])
    assert not run(["baska-lisans"])


def test_hf_reports_each_dataset_and_never_the_token() -> None:
    routes = {
        "/api/whoami-v2": httpx.Response(200, json={"name": "sentetik"}),
        f"/api/datasets/{HF_DATASETS[0]}/auth-check": httpx.Response(200, json={}),
        f"/api/datasets/{HF_DATASETS[1]}/auth-check": httpx.Response(403),
    }
    checks = check_hf(client_for(routes), FAKE_KEY, HF)
    assert [c.ok for c in checks] == [True, True, False]
    assert all(FAKE_KEY not in f"{c.name} {c.detail}" for c in checks)


def test_hf_invalid_token() -> None:
    routes = {"/api/whoami-v2": httpx.Response(401)}
    checks = check_hf(client_for(routes), FAKE_KEY, HF)
    assert len(checks) == 1 and not checks[0].ok
