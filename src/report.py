"""Build DocsHealthReport and format PR comments.

Aggregates runner results + AI suggestions into a single report,
then formats as a GitHub-flavored markdown PR comment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from docsync.claims import ClaimResult, ClaimStatus
from docsync.evidence import DocEvidencePack
from src.ai_suggest import DocSuggestion


@dataclass(frozen=True)
class DocsHealthReport:
    """Summary of a docs verification run."""

    total_claims: int
    passed: int
    failed: int
    skipped: int
    suggestions: list[DocSuggestion] = field(default_factory=list)
    evidence_pack_hashes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "suggestions": [
                {
                    "doc_path": s.doc_path,
                    "claim_id": s.claim_id,
                    "claim_text": s.claim_text,
                    "suggestion": s.suggestion,
                }
                for s in self.suggestions
            ],
            "evidence_pack_hashes": self.evidence_pack_hashes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def build_report(
    doc_paths: list[str],
    packs: list[DocEvidencePack],
    suggestions: list[DocSuggestion] | None = None,
) -> DocsHealthReport:
    """Build a health report from runner output."""
    total = 0
    passed = 0
    failed = 0
    skipped = 0
    hashes: list[str] = []

    for pack in packs:
        for result in pack.results:
            total += 1
            if result.status == ClaimStatus.PASS:
                passed += 1
            elif result.status == ClaimStatus.FAIL:
                failed += 1
            else:
                skipped += 1

        if pack.immutability_proof:
            root = pack.immutability_proof.get("root_hash", "")
            if root:
                hashes.append(root)

    return DocsHealthReport(
        total_claims=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        suggestions=suggestions or [],
        evidence_pack_hashes=hashes,
    )


def format_pr_comment(
    report: DocsHealthReport,
    doc_paths: list[str],
    packs: list[DocEvidencePack],
) -> str:
    """Format the report as a GitHub PR comment."""
    # Header
    if report.failed == 0:
        header = f"## Docs Health: {report.passed}/{report.total_claims} claims passing"
    else:
        header = f"## Docs Health: {report.passed}/{report.total_claims} claims passing ({report.failed} drifted)"

    # Per-doc table
    rows: list[str] = []
    rows.append("| Doc | Claims | Status |")
    rows.append("|-----|--------|--------|")

    for doc_path, pack in zip(doc_paths, packs):
        doc_total = len(pack.results)
        doc_pass = sum(1 for r in pack.results if r.status == ClaimStatus.PASS)
        doc_fail = sum(1 for r in pack.results if r.status == ClaimStatus.FAIL)
        if doc_fail == 0:
            status = "PASS"
        else:
            status = f"{doc_fail} DRIFT"
        rows.append(f"| `{doc_path}` | {doc_pass}/{doc_total} | {status} |")

    table = "\n".join(rows)

    # Failed claims details
    details = ""
    failed_claims: list[tuple[str, ClaimResult]] = []
    for doc_path, pack in zip(doc_paths, packs):
        for result in pack.results:
            if result.status == ClaimStatus.FAIL:
                failed_claims.append((doc_path, result))

    if failed_claims:
        detail_lines = []
        # Cap at 20 to avoid GitHub comment length limits
        shown = failed_claims[:20]
        for doc_path, result in shown:
            detail_lines.append(f"**`{doc_path}`** - \"{result.claim_text}\"")
            if result.evidence:
                for e in result.evidence[:3]:
                    detail_lines.append(f"- Looked in: `{e.path}:{e.line}`")
            detail_lines.append(f"- Result: {result.message}")

            # Find matching suggestion
            for s in report.suggestions:
                if s.claim_id == result.claim_id and s.doc_path == doc_path:
                    detail_lines.append(f"- **Suggestion**: {s.suggestion}")
                    break

            detail_lines.append("")

        if len(failed_claims) > 20:
            detail_lines.append(f"*... and {len(failed_claims) - 20} more drifted claims*\n")

        inner = "\n".join(detail_lines)
        details = (
            f"\n<details><summary>{report.failed} drifted claims (click to expand)</summary>\n\n"
            f"{inner}"
            f"</details>\n"
        )

    # Evidence hashes
    hash_line = ""
    if report.evidence_pack_hashes:
        short_hashes = [h[:16] + "..." for h in report.evidence_pack_hashes if h]
        if short_hashes:
            hash_line = f"\nEvidence packs: {', '.join(short_hashes)}"

    return f"{header}\n\n{table}{details}{hash_line}\n"
