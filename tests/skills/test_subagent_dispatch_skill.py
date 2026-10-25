"""Tests for the subagent-dispatch bundled skill.

Covers ``scripts/verify_artifacts.py`` — the artifact manifest checker that
makes a delegated task verifiable instead of self-reported.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "autonomous-ai-agents" / "subagent-dispatch"
SCRIPT = SKILL_DIR / "scripts" / "verify_artifacts.py"


@pytest.fixture(scope="module")
def verifier():
    spec = importlib.util.spec_from_file_location("verify_artifacts", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ manifest


def test_parse_manifest_drops_blanks_and_comments(verifier) -> None:
    text = "a.txt\n\n  \n# a comment\n  b.txt  \n"
    assert verifier.parse_manifest(text) == ["a.txt", "b.txt"]


def test_parse_manifest_keeps_paths_with_spaces(verifier) -> None:
    assert verifier.parse_manifest("out dir/a b.txt\n") == ["out dir/a b.txt"]


# --------------------------------------------------------------------- check


def test_check_passes_on_existing_nonempty_file(verifier, tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("content", encoding="utf-8")
    path, status, ok = verifier.check(str(target))
    assert ok is True
    assert status == "PASS"
    assert path == str(target)


def test_check_fails_on_missing_file(verifier, tmp_path: Path) -> None:
    _, status, ok = verifier.check(str(tmp_path / "nope.txt"))
    assert ok is False
    assert "missing" in status


def test_check_fails_on_empty_file(verifier, tmp_path: Path) -> None:
    target = tmp_path / "empty.txt"
    target.write_text("", encoding="utf-8")
    _, status, ok = verifier.check(str(target))
    assert ok is False
    assert "empty" in status


def test_check_fails_on_directory(verifier, tmp_path: Path) -> None:
    _, status, ok = verifier.check(str(tmp_path))
    assert ok is False
    assert "directory" in status


def test_check_expands_user_home(verifier, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "home.txt").write_text("x", encoding="utf-8")
    _, _, ok = verifier.check("~/home.txt")
    assert ok is True


# ------------------------------------------------------------------------ cli


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_cli_exits_zero_when_all_artifacts_present(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("ok", encoding="utf-8")
    manifest = tmp_path / "m.txt"
    manifest.write_text(f"{good}\n", encoding="utf-8")
    result = _run([str(manifest)])
    assert result.returncode == 0
    assert "PASS" in result.stdout
    assert "1/1 artifacts present" in result.stdout


def test_cli_exits_nonzero_when_an_artifact_is_missing(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("ok", encoding="utf-8")
    manifest = tmp_path / "m.txt"
    manifest.write_text(f"{good}\n{tmp_path / 'absent.txt'}\n", encoding="utf-8")
    result = _run([str(manifest)])
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "1/2 artifacts present" in result.stdout


def test_cli_exits_nonzero_on_missing_manifest(tmp_path: Path) -> None:
    result = _run([str(tmp_path / "nope-manifest.txt")])
    assert result.returncode == 1
    assert "manifest missing" in result.stdout


def test_cli_without_arguments_is_a_usage_error() -> None:
    result = _run([])
    assert result.returncode == 2
    assert "usage:" in result.stderr


# ------------------------------------------------------------ skill contract


def test_skill_frontmatter_is_complete() -> None:
    import hermes_yaml as yaml

    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    end = text.index("\n---\n", 3)
    fm = yaml.safe_load(text[4:end])
    for field in ("name", "description", "version", "author", "license", "platforms"):
        assert field in fm, f"missing frontmatter field: {field}"
    assert fm["name"] == SKILL_DIR.name
    assert len(fm["description"]) <= 60
    assert fm["description"].endswith(".")
    tags = (fm.get("metadata") or {}).get("hermes", {}).get("tags")
    assert tags, "no tags"


def test_skill_names_the_native_delegation_tool() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "delegate_task" in text
    assert "verify_artifacts.py" in text


def test_brief_contract_reference_exists() -> None:
    assert (SKILL_DIR / "references" / "brief-contract.md").is_file()
