"""The SIGIA client sends the same form the official page sends, without touching the network."""
import json
from urllib.parse import parse_qs

import httpx

from knowledge.sources.sigia.client import BASE_URL, SigiaClient


def _client(captured: list):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((str(request.url), parse_qs(request.content.decode())))
        return httpx.Response(200, text=json.dumps([["023075", "Vaccinium corymbosum  ", "Arándano"]]))
    return SigiaClient(transport=httpx.MockTransport(handler), pause_s=0)


def test_crops_query():
    captured = []
    with _client(captured) as c:
        rows = c.crops(common_name="arandano")
    url, form = captured[0]
    assert url == BASE_URL
    assert form["C"] == ["CULTIVO"] and form["S"] == ["GETLIST"] and form["nombrecomun"] == ["arandano"]
    assert rows[0][0] == "023075"


def test_products_query_joins_pests_and_uses():
    captured = []
    with _client(captured) as c:
        c.products("023075", ["000626", "000700"], ["0199"])
    _, form = captured[0]
    assert form["S"] == ["PLAGAPRODUCTOGETLIST"]
    assert form["plagas"] == ["000626,000700"] and form["idclaseotrouso"] == ["0199"]


def test_two_crops_on_the_same_day_keep_their_own_manifest(tmp_path):
    import json
    from datetime import date

    from knowledge.sources.sigia.snapshot import take_snapshot

    class FakeClient:
        def pests(self, crop_id):
            return []

        def products(self, crop_id, pests, uses):
            return []

    day = date(2026, 10, 28)
    take_snapshot("020732", FakeClient(), day, root=tmp_path)
    take_snapshot("020772", FakeClient(), day, root=tmp_path)
    for crop_id in ("020732", "020772"):
        manifest = json.loads((tmp_path / "sigia" / crop_id / "2026-10-28" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["params"]["crop_id"] == crop_id
        assert [f["name"] for f in manifest["files"]] == [f"pests_{crop_id}.json"]
