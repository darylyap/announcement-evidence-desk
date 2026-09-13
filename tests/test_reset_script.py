import importlib.util
import json
from zipfile import ZipFile

import httpx
import pytest

from desk import config

spec = importlib.util.spec_from_file_location(
    "reset_workspace", config.ROOT / "scripts/reset_workspace.py"
)
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


@pytest.mark.parametrize("confirmation,inside", [("wrong-host", False), ("127.0.0.1:8012", True)])
def test_reset_requires_exact_host_and_private_backup(monkeypatch, tmp_path, confirmation, inside):
    monkeypatch.setattr(
        "sys.argv",
        [
            "reset",
            "--confirm-reset",
            confirmation,
            "--backup-dir",
            str(config.ROOT / "backups" if inside else tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        reset.main()
    assert exc.value.code == 2


def test_reset_backs_up_before_deleting_and_keeps_builtins(monkeypatch, tmp_path):
    calls = []
    cases = [{"id": "old"}]
    detail = {
        "id": "old",
        "runs": [],
        "documents": [{"id": "doc1", "has_file": True}],
        "historical_documents": [],
    }
    workspaces = [{"id": "general"}, {"id": "examples"}, {"id": "custom"}]

    def handle(request):
        path = request.url.path
        calls.append((request.method, path))
        if request.method == "DELETE":
            archives = list(tmp_path.glob("*.zip"))
            assert len(archives) == 1
            with ZipFile(archives[0]) as z:
                assert z.read("files/doc1") == b"original document"
                assert json.loads(z.read("records.json"))["cases"][0]["id"] == "old"
            if path == "/api/cases/old":
                cases.clear()
            return httpx.Response(200, json={"deleted": True})
        if request.method == "POST":
            assert path == "/api/examples/dbs-two-claims"
            cases.append({"id": "starter"})
            return httpx.Response(201, json={"id": "starter"})
        values = {"/api/cases": cases, "/api/cases/old": detail, "/api/workspaces": workspaces}
        if path.endswith("/file"):
            return httpx.Response(200, content=b"original document")
        return httpx.Response(200, json=values[path])

    original = httpx.Client
    monkeypatch.setattr(
        reset.httpx, "Client", lambda **kw: original(**kw, transport=httpx.MockTransport(handle))
    )
    monkeypatch.setattr(
        "sys.argv", ["reset", "--confirm-reset", "127.0.0.1:8012", "--backup-dir", str(tmp_path)]
    )
    reset.main()
    assert ("DELETE", "/api/workspaces/custom") in calls
    assert ("DELETE", "/api/workspaces/general") not in calls
    assert ("DELETE", "/api/workspaces/examples") not in calls
    assert cases == [{"id": "starter"}]
