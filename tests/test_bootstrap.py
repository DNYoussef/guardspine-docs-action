"""Tests for manifest bootstrap from existing docs."""

import tempfile
from pathlib import Path

from src.bootstrap import bootstrap_manifest, _extract_claims


def test_extract_claims_from_bold():
    content = (
        "## API Reference\n"
        "\n"
        "The **backend exposes a REST API on port 8080** for all operations.\n"
        "\n"
        "See `backend/src/server.py` for details.\n"
    )
    claims = _extract_claims(content, "docs/API.md", 0)
    assert len(claims) >= 1
    assert claims[0]["text"] == "backend exposes a REST API on port 8080"
    assert claims[0]["id"] == "c0000"


def test_extract_claims_skips_short_bold():
    content = "The **API** is documented.\n"
    claims = _extract_claims(content, "docs/API.md", 0)
    assert len(claims) == 0  # "API" is too short (<10 chars)


def test_extract_claims_with_code_ref():
    content = (
        "## Deploy\n"
        "The **deployment uses Docker Compose for orchestration** via `deploy/docker-compose.py`\n"
    )
    claims = _extract_claims(content, "docs/DEPLOY.md", 0)
    assert len(claims) >= 1
    # Should have code evidence since .py file was referenced
    assert any(
        e.get("type") == "code"
        for c in claims
        for e in c.get("evidence", [])
    )


def test_bootstrap_manifest_empty_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = bootstrap_manifest(tmpdir)
        assert result["version"] == "1.0"
        assert result["docs"] == []


def test_bootstrap_manifest_with_docs():
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "API.md").write_text(
            "## API\n\nThe **backend uses Express.js for routing** all requests.\n",
            encoding="utf-8",
        )
        result = bootstrap_manifest(str(docs_dir), tmpdir)
        assert len(result["docs"]) >= 1
        assert result["docs"][0]["path"].endswith("API.md")
        assert len(result["docs"][0]["claims"]) >= 1
