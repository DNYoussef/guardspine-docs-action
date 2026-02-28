"""Integration test: full pipeline from manifest to report."""

import tempfile
from pathlib import Path

import yaml

from docsync.manifest import load_manifest_from_dict, validate_manifest
from docsync.runner import NightlyRunner
from docsync.claims import ClaimStatus
from src.report import build_report, format_pr_comment


def test_full_pipeline():
    """End-to-end: create a mini repo, write a manifest, run verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create a mini "repo"
        src_dir = root / "backend" / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "server.py").write_text(
            'app = Flask(__name__)\n'
            'PORT = 8080\n'
            '@app.route("/api/v1/health")\n'
            'def health(): return "ok"\n',
            encoding="utf-8",
        )

        docs_dir = root / "docs"
        docs_dir.mkdir()
        (docs_dir / "API.md").write_text(
            "# API\n\nThe server runs on port 8080.\n",
            encoding="utf-8",
        )

        # Create manifest
        manifest_data = {
            "version": "1.0",
            "docs": [
                {
                    "path": "docs/API.md",
                    "mode": "spec-first",
                    "claims": [
                        {
                            "id": "c0001",
                            "text": "Server runs on port 8080",
                            "evidence": [
                                {
                                    "type": "code",
                                    "pattern": "PORT.*8080",
                                    "scope": "backend/src",
                                }
                            ],
                        },
                        {
                            "id": "c0002",
                            "text": "Health endpoint exists at /api/v1/health",
                            "evidence": [
                                {
                                    "type": "code",
                                    "pattern": "/api/v1/health",
                                    "scope": "backend/src",
                                }
                            ],
                        },
                        {
                            "id": "c0003",
                            "text": "Uses GraphQL",
                            "evidence": [
                                {
                                    "type": "code",
                                    "pattern": "graphql|GraphQL",
                                    "scope": "backend/src",
                                }
                            ],
                        },
                    ],
                }
            ],
        }

        manifest_yaml = yaml.dump(manifest_data)
        manifest = load_manifest_from_dict(manifest_data)

        # Validate
        errors = validate_manifest(manifest)
        assert errors == [], f"Manifest errors: {errors}"

        # Run
        runner = NightlyRunner(repo_root=root, manifest_text=manifest_yaml)
        packs = runner.run(manifest)

        assert len(packs) == 1
        pack = packs[0]
        assert len(pack.results) == 3

        # c0001: PORT = 8080 should pass
        assert pack.results[0].status == ClaimStatus.PASS
        # c0002: /api/v1/health should pass
        assert pack.results[1].status == ClaimStatus.PASS
        # c0003: GraphQL should fail (not in code)
        assert pack.results[2].status == ClaimStatus.FAIL

        # Verify hash chain
        ok, msg = pack.verify()
        assert ok is True, f"Hash chain verification failed: {msg}"

        # Build report
        doc_paths = ["docs/API.md"]
        report = build_report(doc_paths, packs)
        assert report.total_claims == 3
        assert report.passed == 2
        assert report.failed == 1

        # Format comment
        comment = format_pr_comment(report, doc_paths, packs)
        assert "2/3 claims passing" in comment
        assert "1 DRIFT" in comment
        assert "Uses GraphQL" in comment


def test_full_pipeline_all_pass():
    """Verify clean run produces all-pass report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        src_dir = root / "src"
        src_dir.mkdir()
        (src_dir / "auth.py").write_text(
            'import jwt\ndef verify_token(token): return jwt.decode(token)\n',
            encoding="utf-8",
        )

        manifest_data = {
            "version": "1.0",
            "docs": [
                {
                    "path": "docs/AUTH.md",
                    "mode": "spec-first",
                    "claims": [
                        {
                            "id": "c0001",
                            "text": "Authentication uses JWT",
                            "evidence": [
                                {"type": "code", "pattern": "jwt", "scope": "src"},
                            ],
                        },
                    ],
                }
            ],
        }

        manifest = load_manifest_from_dict(manifest_data)
        runner = NightlyRunner(repo_root=root, manifest_text=yaml.dump(manifest_data))
        packs = runner.run(manifest)

        report = build_report(["docs/AUTH.md"], packs)
        assert report.failed == 0
        assert report.passed == 1

        comment = format_pr_comment(report, ["docs/AUTH.md"], packs)
        assert "DRIFT" not in comment
