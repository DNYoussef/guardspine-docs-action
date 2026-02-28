"""Tests for report building and PR comment formatting."""

from docsync.claims import ClaimResult, ClaimStatus, EvidenceRef
from docsync.evidence import DocEvidencePack
from src.report import build_report, format_pr_comment, DocsHealthReport
from src.ai_suggest import DocSuggestion


def _make_pack(statuses):
    results = [
        ClaimResult(claim_id=f"c{i:04d}", claim_text=f"Claim {i}", status=s)
        for i, s in enumerate(statuses)
    ]
    pack = DocEvidencePack(manifest_hash="test", results=results)
    pack.build_hash_chain()
    return pack


def test_build_report_all_pass():
    pack = _make_pack([ClaimStatus.PASS, ClaimStatus.PASS])
    report = build_report(["docs/API.md"], [pack])
    assert report.total_claims == 2
    assert report.passed == 2
    assert report.failed == 0
    assert report.skipped == 0


def test_build_report_mixed():
    pack = _make_pack([ClaimStatus.PASS, ClaimStatus.FAIL, ClaimStatus.SKIP])
    report = build_report(["docs/DEPLOY.md"], [pack])
    assert report.total_claims == 3
    assert report.passed == 1
    assert report.failed == 1
    assert report.skipped == 1


def test_build_report_with_suggestions():
    pack = _make_pack([ClaimStatus.FAIL])
    suggestion = DocSuggestion(
        doc_path="docs/API.md",
        claim_id="c0000",
        claim_text="Claim 0",
        suggestion="Update the port number",
        evidence_expected="port 8080",
        evidence_found="none",
    )
    report = build_report(["docs/API.md"], [pack], [suggestion])
    assert len(report.suggestions) == 1


def test_format_pr_comment_all_pass():
    pack = _make_pack([ClaimStatus.PASS, ClaimStatus.PASS])
    report = build_report(["docs/API.md"], [pack])
    comment = format_pr_comment(report, ["docs/API.md"], [pack])
    assert "2/2 claims passing" in comment
    assert "PASS" in comment
    assert "DRIFT" not in comment


def test_format_pr_comment_with_failures():
    results = [
        ClaimResult(
            claim_id="c0000",
            claim_text="Backend runs on port 8080",
            status=ClaimStatus.FAIL,
            message="no matching evidence found",
            evidence=[EvidenceRef(source_type="code", path="docker-compose.yml", line=5, matched=False)],
        ),
        ClaimResult(claim_id="c0001", claim_text="Uses JWT", status=ClaimStatus.PASS),
    ]
    pack = DocEvidencePack(manifest_hash="test", results=results)
    pack.build_hash_chain()

    suggestion = DocSuggestion(
        doc_path="docs/DEPLOY.md",
        claim_id="c0000",
        claim_text="Backend runs on port 8080",
        suggestion="Change port to 3000",
        evidence_expected="port 8080",
        evidence_found="none",
    )
    report = build_report(["docs/DEPLOY.md"], [pack], [suggestion])
    comment = format_pr_comment(report, ["docs/DEPLOY.md"], [pack])

    assert "1 DRIFT" in comment
    assert "drifted claims" in comment
    assert "Change port to 3000" in comment


def test_report_to_json():
    pack = _make_pack([ClaimStatus.PASS])
    report = build_report(["docs/API.md"], [pack])
    json_str = report.to_json()
    assert '"total_claims": 1' in json_str
    assert '"passed": 1' in json_str
