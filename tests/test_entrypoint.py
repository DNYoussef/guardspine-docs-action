"""Tests for entrypoint input parsing and orchestration."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from entrypoint import get_input, parse_bool, get_repo_file_list


def test_get_input_from_env():
    with patch.dict(os.environ, {"INPUT_MANIFEST_PATH": "custom.yaml"}):
        assert get_input("manifest_path") == "custom.yaml"


def test_get_input_default():
    # Ensure the env var is not set
    env = dict(os.environ)
    env.pop("INPUT_TEST_KEY", None)
    with patch.dict(os.environ, env, clear=True):
        assert get_input("test_key", "default_val") == "default_val"


def test_parse_bool():
    assert parse_bool("true") is True
    assert parse_bool("True") is True
    assert parse_bool("1") is True
    assert parse_bool("yes") is True
    assert parse_bool("false") is False
    assert parse_bool("0") is False
    assert parse_bool("no") is False
    assert parse_bool("") is False


def test_get_repo_file_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
        (root / "README.md").write_text("# Readme", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "config").write_text("", encoding="utf-8")

        files = get_repo_file_list(root)
        paths = set(files)
        assert "src/main.py" in paths
        assert "README.md" in paths
        # .git should be excluded
        assert ".git/config" not in paths


def test_get_repo_file_list_respects_limit():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for i in range(20):
            (root / f"file_{i}.txt").write_text("x", encoding="utf-8")

        files = get_repo_file_list(root, max_files=5)
        assert len(files) == 5
