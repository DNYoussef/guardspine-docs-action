"""Auto-generate a guardspine.docs.yaml manifest from existing docs.

No AI required. Extracts conservative claims from markdown files
by looking for bold assertions and code-reference patterns.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


# Patterns that suggest a verifiable claim
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_REF_RE = re.compile(r"`([a-zA-Z0-9_/.\-]+\.[a-z]{1,4})`")
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)")


def bootstrap_manifest(
    docs_dir: str | Path,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Scan docs_dir for markdown files, extract candidate claims.

    Returns a manifest dict ready to be dumped as YAML.
    """
    docs_path = Path(docs_dir)
    repo_path = Path(repo_root) if repo_root else docs_path.parent

    if not docs_path.exists():
        return {"version": "1.0", "docs": []}

    doc_entries: list[dict[str, Any]] = []
    claim_counter = 0

    for md_file in sorted(docs_path.rglob("*.md")):
        rel_path = str(md_file.relative_to(repo_path)).replace("\\", "/")
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        claims = _extract_claims(content, rel_path, claim_counter)
        claim_counter += len(claims)

        if claims:
            doc_entries.append({
                "path": rel_path,
                "mode": "spec-first",
                "claims": claims,
            })

    return {"version": "1.0", "docs": doc_entries}


def bootstrap_to_yaml(
    docs_dir: str | Path,
    output_path: str | Path,
    repo_root: str | Path | None = None,
) -> Path:
    """Generate manifest and write it as YAML."""
    manifest = bootstrap_manifest(docs_dir, repo_root)
    out = Path(output_path)
    out.write_text(
        yaml.dump(manifest, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return out


def _extract_claims(
    content: str,
    doc_path: str,
    start_id: int,
) -> list[dict[str, Any]]:
    """Extract candidate claims from markdown content."""
    claims: list[dict[str, Any]] = []
    lines = content.splitlines()
    current_heading = ""

    for line in lines:
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            current_heading = heading_match.group(2).strip()
            continue

        # Look for bold text that looks like a verifiable assertion
        for bold_match in _BOLD_RE.finditer(line):
            bold_text = bold_match.group(1).strip()
            # Skip very short or very long bold text (unlikely to be claims)
            if len(bold_text) < 10 or len(bold_text) > 200:
                continue
            # Skip bold text that's just a heading reference or link
            if bold_text.startswith("[") or bold_text.startswith("http"):
                continue

            # Try to find a code reference nearby for evidence
            code_refs = _CODE_REF_RE.findall(line)
            evidence = []
            for ref in code_refs:
                # Guess evidence type from extension
                if any(ref.endswith(ext) for ext in (".py", ".js", ".ts", ".go", ".rs")):
                    evidence.append({
                        "type": "code",
                        "pattern": re.escape(ref.split("/")[-1].split(".")[0]),
                        "scope": "/".join(ref.split("/")[:-1]) if "/" in ref else "",
                    })

            claim_id = f"c{start_id + len(claims):04d}"
            claim: dict[str, Any] = {
                "id": claim_id,
                "text": bold_text,
            }
            if evidence:
                claim["evidence"] = evidence
            else:
                # Add a markdown evidence spec searching for the claim text
                claim["evidence"] = [{
                    "type": "markdown",
                    "pattern": re.escape(bold_text[:60]),
                    "scope": "/".join(doc_path.split("/")[:-1]),
                }]

            claims.append(claim)

    return claims
