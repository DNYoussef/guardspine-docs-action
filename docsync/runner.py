"""DocSync runner: iterate manifest, check claims, produce evidence packs.

Simplified from rlm-docsync -- no PII-Shield sanitization (not needed
for the GitHub Action). Core logic preserved verbatim.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .adapters.code import CodeAdapter
from .adapters.markdown import MarkdownAdapter
from .claims import ClaimResult, ClaimStatus, EvidenceRef
from .evidence import DocEvidencePack
from .manifest import DocManifest, ClaimEntry, EvidenceSpec


class NightlyRunner:
    """Walk docs, check claims against code, produce evidence packs."""

    def __init__(self, repo_root: str | Path, manifest_text: str = "") -> None:
        self.repo_root = Path(repo_root)
        self._manifest_text = manifest_text
        self._code_adapter = CodeAdapter(self.repo_root)
        self._md_adapter = MarkdownAdapter(self.repo_root)

    def _manifest_hash(self) -> str:
        if self._manifest_text:
            return hashlib.sha256(
                self._manifest_text.encode("utf-8")
            ).hexdigest()
        return hashlib.sha256(b"").hexdigest()

    def _inspect_claim(self, claim: ClaimEntry) -> ClaimResult:
        """Inspect a single claim against its evidence specs."""
        refs: list[EvidenceRef] = []
        for spec in claim.evidence:
            adapter_refs = self._inspect_evidence(spec)
            refs.extend(adapter_refs)

        any_matched = any(r.matched for r in refs)
        if not claim.evidence:
            status = ClaimStatus.SKIP
            message = "no evidence specs defined"
        elif not refs:
            status = ClaimStatus.FAIL
            message = "no matching evidence found in searched files"
        elif any_matched:
            status = ClaimStatus.PASS
            message = f"{sum(r.matched for r in refs)}/{len(refs)} evidence found"
        else:
            status = ClaimStatus.FAIL
            message = "no matching evidence found"

        return ClaimResult(
            claim_id=claim.id,
            claim_text=claim.text,
            status=status,
            evidence=refs,
            message=message,
        )

    def _inspect_evidence(self, spec: EvidenceSpec) -> list[EvidenceRef]:
        """Dispatch to the appropriate adapter."""
        if spec.type == "code":
            return self._code_adapter.search(spec.pattern, spec.scope)
        elif spec.type == "markdown":
            return self._md_adapter.search(spec.pattern, spec.scope)
        return []

    def run(self, manifest: DocManifest) -> list[DocEvidencePack]:
        """Run sync across all docs in the manifest."""
        packs: list[DocEvidencePack] = []
        manifest_hash = self._manifest_hash()

        for doc in manifest.docs:
            results: list[ClaimResult] = []
            for claim in doc.claims:
                result = self._inspect_claim(claim)
                results.append(result)

            pack = DocEvidencePack(
                manifest_hash=manifest_hash,
                results=results,
            )
            pack.build_hash_chain()
            packs.append(pack)

        return packs
