"""The EU client follows nextLink and filters the residue catalog by language, without touching the network."""
import httpx

from knowledge.sources.eu_mrl.client import BASE, EuMrlClient


def test_mrls_follow_next_link():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "$after" in str(request.url):
            return httpx.Response(200, json={"value": [{"pesticide_residue_id": 2}]})
        return httpx.Response(200, json={"value": [{"pesticide_residue_id": 1}],
                                         "nextLink": f"{BASE}/pesticide-residues-mrls?$after=abc&product_id=46"})

    with EuMrlClient(transport=httpx.MockTransport(handler)) as c:
        items = c.mrls(46)
    assert [i["pesticide_residue_id"] for i in items] == [1, 2]
    assert "product_id=46" in calls[0] and "api-version=v3.0" in calls[0]


def test_residue_catalog_keeps_requested_languages():
    rows = [{"pesticide_residue_id": 7, "pesticide_residue_lg": lg, "pesticide_residue_name": f"name {lg}"}
            for lg in ("EN", "ES", "FR", "DE")]
    with EuMrlClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"value": rows}))) as c:
        catalog = c.residue_catalog()
    assert {r["pesticide_residue_lg"] for r in catalog} == {"EN", "ES"}
