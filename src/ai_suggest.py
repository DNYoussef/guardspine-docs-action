"""AI-powered suggestions for failed documentation claims.

Uses OpenRouter API (single batched call) to suggest fixes for all
failed claims at once. Degrades gracefully -- never blocks CI.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

from docsync.claims import ClaimResult, ClaimStatus


@dataclass(frozen=True)
class DocSuggestion:
    """AI-generated suggestion for a failed claim."""

    doc_path: str
    claim_id: str
    claim_text: str
    suggestion: str
    evidence_expected: str
    evidence_found: str


def suggest_fixes(
    failed_results: list[tuple[str, ClaimResult]],
    repo_file_list: list[str],
    api_key: str,
    model: str,
) -> list[DocSuggestion]:
    """Call OpenRouter once with all failed claims. Returns suggestions.

    Args:
        failed_results: List of (doc_path, ClaimResult) for failed claims.
        repo_file_list: List of file paths in the repo (for grounding).
        api_key: OpenRouter API key.
        model: Model identifier (e.g. anthropic/claude-sonnet-4).

    Returns empty list on any error (never blocks CI).
    """
    if not openai:
        print("WARNING: openai package not installed, skipping AI suggestions", file=sys.stderr)
        return []

    if not api_key or not failed_results:
        return []

    prompt = _build_batch_prompt(failed_results, repo_file_list)

    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            extra_headers={
                "HTTP-Referer": "https://github.com/DNYoussef/guardspine-docs-action",
            },
            temperature=0.2,
            max_tokens=2000,
        )
        content = response.choices[0].message.content or ""
        return _parse_suggestions(content, failed_results)
    except Exception as exc:
        print(f"WARNING: AI suggestion failed ({type(exc).__name__}: {exc}), continuing without suggestions", file=sys.stderr)
        return []


def _build_batch_prompt(
    failed_results: list[tuple[str, ClaimResult]],
    repo_file_list: list[str],
) -> str:
    """Build a single prompt covering all failed claims."""
    claims_block = []
    for i, (doc_path, result) in enumerate(failed_results):
        evidence_summary = "none found"
        if result.evidence:
            parts = []
            for e in result.evidence:
                parts.append(f"  {e.path}:{e.line} (matched={e.matched})")
            evidence_summary = "\n".join(parts)

        claims_block.append(
            f"[{i}] doc: {doc_path}\n"
            f"    claim_id: {result.claim_id}\n"
            f"    claim: {result.claim_text}\n"
            f"    evidence found:\n{evidence_summary}\n"
            f"    message: {result.message}"
        )

    # Truncate file list to avoid huge prompts
    files_sample = repo_file_list[:200]
    files_block = "\n".join(files_sample)
    if len(repo_file_list) > 200:
        files_block += f"\n... and {len(repo_file_list) - 200} more files"

    return (
        "You are a documentation accuracy assistant. The following documentation "
        "claims failed verification against the codebase. For each failed claim, "
        "suggest a specific fix: either update the doc text to match reality, or "
        "identify what code should change.\n\n"
        "FAILED CLAIMS:\n"
        + "\n\n".join(claims_block)
        + "\n\nREPO FILES (for reference):\n"
        + files_block
        + "\n\nRespond with a JSON array. Each element must have:\n"
        '  {"index": <int>, "suggestion": "<specific fix>"}\n'
        "Return ONLY the JSON array, no other text."
    )


def _parse_suggestions(
    content: str,
    failed_results: list[tuple[str, ClaimResult]],
) -> list[DocSuggestion]:
    """Parse AI response into DocSuggestion objects."""
    # Extract JSON array from response (may have markdown fences)
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        print(f"WARNING: Could not parse AI suggestion response as JSON", file=sys.stderr)
        return []

    if not isinstance(items, list):
        return []

    suggestions: list[DocSuggestion] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("index", -1)
        suggestion_text = str(item.get("suggestion", ""))
        if not suggestion_text or idx < 0 or idx >= len(failed_results):
            continue

        doc_path, result = failed_results[idx]
        evidence_expected = result.claim_text
        evidence_found = result.message

        suggestions.append(DocSuggestion(
            doc_path=doc_path,
            claim_id=result.claim_id,
            claim_text=result.claim_text,
            suggestion=suggestion_text,
            evidence_expected=evidence_expected,
            evidence_found=evidence_found,
        ))

    return suggestions
