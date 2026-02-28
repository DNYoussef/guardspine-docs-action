"""Tests for AI suggestion module (mocked, no API calls)."""

from unittest.mock import patch, MagicMock
import json

from docsync.claims import ClaimResult, ClaimStatus
from src.ai_suggest import suggest_fixes, _parse_suggestions, _build_batch_prompt, DocSuggestion


def _make_failed(claim_id="c0000", text="Port is 8080"):
    return ClaimResult(
        claim_id=claim_id,
        claim_text=text,
        status=ClaimStatus.FAIL,
        message="no matching evidence found",
    )


def test_suggest_fixes_no_api_key():
    result = suggest_fixes(
        [("docs/API.md", _make_failed())],
        ["backend/server.py"],
        api_key="",
        model="test",
    )
    assert result == []


def test_suggest_fixes_no_failures():
    result = suggest_fixes(
        [],
        ["backend/server.py"],
        api_key="sk-test",
        model="test",
    )
    assert result == []


def test_build_batch_prompt():
    failed = [("docs/API.md", _make_failed())]
    prompt = _build_batch_prompt(failed, ["server.py", "app.js"])
    assert "Port is 8080" in prompt
    assert "server.py" in prompt
    assert "JSON array" in prompt


def test_parse_suggestions_valid():
    content = json.dumps([
        {"index": 0, "suggestion": "Update port to 3000"},
    ])
    failed = [("docs/API.md", _make_failed())]
    suggestions = _parse_suggestions(content, failed)
    assert len(suggestions) == 1
    assert suggestions[0].suggestion == "Update port to 3000"
    assert suggestions[0].doc_path == "docs/API.md"


def test_parse_suggestions_with_markdown_fences():
    content = '```json\n[{"index": 0, "suggestion": "Fix the doc"}]\n```'
    failed = [("docs/API.md", _make_failed())]
    suggestions = _parse_suggestions(content, failed)
    assert len(suggestions) == 1


def test_parse_suggestions_invalid_json():
    content = "This is not JSON"
    failed = [("docs/API.md", _make_failed())]
    suggestions = _parse_suggestions(content, failed)
    assert suggestions == []


def test_parse_suggestions_out_of_range_index():
    content = json.dumps([{"index": 99, "suggestion": "bad index"}])
    failed = [("docs/API.md", _make_failed())]
    suggestions = _parse_suggestions(content, failed)
    assert suggestions == []


@patch("src.ai_suggest.openai")
def test_suggest_fixes_api_error_returns_empty(mock_openai):
    mock_client = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API error")

    result = suggest_fixes(
        [("docs/API.md", _make_failed())],
        ["server.py"],
        api_key="sk-test",
        model="test",
    )
    assert result == []


@patch("src.ai_suggest.openai")
def test_suggest_fixes_success(mock_openai):
    mock_client = MagicMock()
    mock_openai.OpenAI.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps([
        {"index": 0, "suggestion": "Change port to 3000"},
    ])
    mock_client.chat.completions.create.return_value = mock_response

    result = suggest_fixes(
        [("docs/DEPLOY.md", _make_failed())],
        ["docker-compose.yml"],
        api_key="sk-test",
        model="anthropic/claude-sonnet-4",
    )
    assert len(result) == 1
    assert result[0].suggestion == "Change port to 3000"
