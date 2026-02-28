#!/usr/bin/env python3
"""GuardSpine Docs Guard -- GitHub Action entrypoint.

Parses action inputs from INPUT_* env vars, runs docsync claim
verification, optionally calls OpenRouter for AI suggestions,
and posts a PR comment with the health report.
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from docsync.manifest import load_manifest_from_dict, validate_manifest
from docsync.runner import NightlyRunner
from docsync.claims import ClaimStatus
from src.ai_suggest import suggest_fixes
from src.report import build_report, format_pr_comment, DocsHealthReport
from src.bootstrap import bootstrap_manifest


def get_input(name: str, default: str = "") -> str:
    """Read a GitHub Action input from environment."""
    return os.environ.get(f"INPUT_{name.upper()}", default)


def parse_bool(value: str) -> bool:
    return value.lower() in ("true", "1", "yes")


def set_output(name: str, value: str) -> None:
    """Set a GitHub Actions output using delimiter syntax."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    text = str(value)
    if output_file:
        delimiter = f"EOF_{hashlib.sha256(f'{name}:{text}'.encode()).hexdigest()[:16]}"
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{name}<<{delimiter}\n")
            f.write(f"{text}\n")
            f.write(f"{delimiter}\n")
    else:
        print(f"::set-output name={name}::{text}")


def get_repo_file_list(repo_root: Path, max_files: int = 500) -> list[str]:
    """List repo files for AI grounding. Skips hidden dirs and node_modules."""
    files: list[str] = []
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"}
    for p in repo_root.rglob("*"):
        if any(part in skip for part in p.parts):
            continue
        if p.is_file():
            files.append(str(p.relative_to(repo_root)).replace("\\", "/"))
            if len(files) >= max_files:
                break
    return files


def post_pr_comment(comment_body: str, github_token: str) -> None:
    """Post or update a PR comment. Only works in PR context."""
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path or not Path(event_path).exists():
        print("Not in a GitHub Actions event context, skipping PR comment")
        return

    try:
        from github import Auth, Github
    except ImportError:
        print("WARNING: PyGithub not installed, skipping PR comment", file=sys.stderr)
        return

    try:
        with open(event_path, "r", encoding="utf-8") as f:
            event = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: Could not read event file: {exc}", file=sys.stderr)
        return

    pr_number = None
    if "pull_request" in event:
        pr_number = event["pull_request"].get("number")
    elif "number" in event:
        pr_number = event["number"]

    if not pr_number:
        print("No PR number found in event, skipping PR comment")
        return

    repo_name = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo_name:
        print("GITHUB_REPOSITORY not set, skipping PR comment")
        return

    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    # Update existing comment if found, otherwise create new
    marker = "<!-- guardspine-docs-guard -->"
    for comment in pr.get_issue_comments():
        if marker in (comment.body or ""):
            comment.edit(f"{marker}\n{comment_body}")
            print(f"Updated existing PR comment #{comment.id}")
            return

    pr.create_issue_comment(f"{marker}\n{comment_body}")
    print(f"Posted new PR comment on #{pr_number}")


def main() -> int:
    # Parse inputs
    manifest_path = get_input("manifest_path", "guardspine.docs.yaml")
    api_key = get_input("openrouter_api_key", "")
    model = get_input("model", "anthropic/claude-sonnet-4")
    fail_on_drift = parse_bool(get_input("fail_on_drift", "false"))
    github_token = get_input("github_token", "")

    workspace = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    manifest_file = workspace / manifest_path

    # Bootstrap if no manifest exists
    if not manifest_file.exists():
        print(f"No manifest at {manifest_path}, bootstrapping from docs/...")
        docs_dir = workspace / "docs"
        if not docs_dir.exists():
            print("No docs/ directory found. Nothing to check.")
            set_output("total_claims", "0")
            set_output("passed", "0")
            set_output("failed", "0")
            set_output("report_json", "{}")
            return 0

        manifest_data = bootstrap_manifest(docs_dir, workspace)
        if not manifest_data.get("docs"):
            print("Bootstrap found no claims in docs/. Nothing to check.")
            set_output("total_claims", "0")
            set_output("passed", "0")
            set_output("failed", "0")
            set_output("report_json", "{}")
            return 0

        print(f"Bootstrapped {sum(len(d.get('claims', [])) for d in manifest_data['docs'])} claims from {len(manifest_data['docs'])} docs")
    else:
        # Load manifest
        manifest_text = manifest_file.read_text(encoding="utf-8")
        try:
            manifest_data = yaml.safe_load(manifest_text) or {}
        except yaml.YAMLError as exc:
            print(f"ERROR: Failed to parse manifest: {exc}", file=sys.stderr)
            return 1

    # Parse and validate
    manifest = load_manifest_from_dict(manifest_data)
    errors = validate_manifest(manifest)
    if errors:
        for err in errors:
            print(f"Manifest error: {err}", file=sys.stderr)
        return 1

    # Run verification
    manifest_yaml = yaml.dump(manifest_data, default_flow_style=False)
    runner = NightlyRunner(repo_root=workspace, manifest_text=manifest_yaml)
    packs = runner.run(manifest)

    doc_paths = [doc.path for doc in manifest.docs]

    # Collect failed claims for AI suggestions
    failed_results: list[tuple[str, Any]] = []
    for doc, pack in zip(manifest.docs, packs):
        for result in pack.results:
            if result.status == ClaimStatus.FAIL:
                failed_results.append((doc.path, result))

    # AI suggestions (optional, never blocks)
    suggestions = []
    if api_key and failed_results:
        print(f"Requesting AI suggestions for {len(failed_results)} failed claims...")
        file_list = get_repo_file_list(workspace)
        suggestions = suggest_fixes(failed_results, file_list, api_key, model)
        print(f"Got {len(suggestions)} suggestions")

    # Build report
    report = build_report(doc_paths, packs, suggestions)

    # Set outputs
    set_output("total_claims", str(report.total_claims))
    set_output("passed", str(report.passed))
    set_output("failed", str(report.failed))
    set_output("report_json", report.to_json())

    # Print summary
    print(f"\nDocs Health: {report.passed}/{report.total_claims} passing, "
          f"{report.failed} failed, {report.skipped} skipped")

    # Post PR comment
    if github_token:
        comment = format_pr_comment(report, doc_paths, packs)
        post_pr_comment(comment, github_token)

    # Exit code
    if fail_on_drift and report.failed > 0:
        print(f"\nFailing: {report.failed} claims drifted (fail_on_drift=true)")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
