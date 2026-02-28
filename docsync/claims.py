"""Claim schema: ClaimResult and EvidenceRef.

Vendored from rlm-docsync. These are the output types of a doc-sync run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


_MAX_SNIPPET_LEN = 120


class ClaimStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class EvidenceRef:
    source_type: str
    path: str
    line: int = 0
    snippet: str = ""
    matched: bool = False

    def __post_init__(self) -> None:
        if len(self.snippet) > _MAX_SNIPPET_LEN:
            object.__setattr__(
                self, "snippet", self.snippet[:_MAX_SNIPPET_LEN]
            )


@dataclass
class ClaimResult:
    claim_id: str
    claim_text: str
    status: ClaimStatus = ClaimStatus.SKIP
    evidence: list[EvidenceRef] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "status": self.status.value,
            "evidence": [
                {
                    "source_type": e.source_type,
                    "path": e.path,
                    "line": e.line,
                    "snippet": e.snippet,
                    "matched": e.matched,
                }
                for e in self.evidence
            ],
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClaimResult:
        if not isinstance(data, dict):
            raise ValueError(
                f"ClaimResult.from_dict expects a dict, got {type(data).__name__}"
            )
        for key in ("claim_id", "claim_text"):
            if key not in data:
                raise KeyError(f"ClaimResult.from_dict: missing required key '{key}'")

        raw_evidence = data.get("evidence", [])
        if not isinstance(raw_evidence, list):
            raise ValueError("ClaimResult.from_dict: 'evidence' must be a list")

        evidence: list[EvidenceRef] = []
        for e in raw_evidence:
            if not isinstance(e, dict):
                raise ValueError(
                    "ClaimResult.from_dict: each evidence entry must be a dict"
                )
            snippet = str(e.get("snippet", ""))[:_MAX_SNIPPET_LEN]
            evidence.append(
                EvidenceRef(
                    source_type=str(e.get("source_type", "")),
                    path=str(e.get("path", "")),
                    line=int(e.get("line", 0)),
                    snippet=snippet,
                    matched=bool(e.get("matched", False)),
                )
            )

        status_raw = data.get("status", "skip")
        try:
            status = ClaimStatus(status_raw)
        except ValueError:
            status = ClaimStatus.SKIP

        return cls(
            claim_id=str(data["claim_id"]),
            claim_text=str(data["claim_text"]),
            status=status,
            evidence=evidence,
            message=str(data.get("message", "")),
        )
