"""Per-line clipping must surface in truncation metadata (Fas #1152).

``read_file`` used to clip a pathological line but return ``truncated: false``,
so a machine consumer parsing the rendered content got silently invalid JSON
(the closing syntax lived past the clip point) with no metadata saying data
was lost. Every clip now: ``truncated=True``, the clipped line numbers +
reason in ``truncated_lines``, and a hint naming a bounded recovery path.

Cases mirror the issue: below / at / above the per-line char limit, a one-line
JSON fixture, and a long line inside a multi-line file — asserting metadata
and continuation behavior, not merely the visible ``... [truncated]`` marker.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.environments.local import LocalEnvironment
from tools.file_operations import ShellFileOperations
from tools.tool_output_limits import get_max_line_length


@pytest.fixture
def ops():
    return ShellFileOperations(LocalEnvironment())


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# --- Review-round regressions (bounded metadata, extracted docs, hint merge) ---

def test_extracted_document_clipping_sets_metadata(tmp_path):
    """file_tools.py's extracted-document path (.ipynb) must report clipping.

    Review finding (major): read_file on a document whose extracted text has a
    line over the per-line limit used to show visible '... [truncated]' markers
    while reporting truncated=false with no metadata and no hint. First-class
    dispatch path — clips here are content clipping and must be surfaced.
    """
    from tools.file_tools import read_file_tool

    nb = {
        "cells": [
            {"cell_type": "code",
             "outputs": [{"output_type": "stream", "text": ["x" * 5000]}],
             "source": ["print(1)"]}
        ],
        "metadata": {},
        "nbformat": 4,
    }
    p = tmp_path / "t.ipynb"
    p.write_text(json.dumps(nb), encoding="utf-8")

    raw = read_file_tool(str(p), 1, 2000)
    if raw.startswith('{"content"') is False and not raw.startswith("{"):
        pytest.fail(f"unexpected non-JSON result: {raw[:120]}")
    d = json.loads(raw)
    assert d["truncated"] is True
    assert d.get("truncated_lines"), "extracted-doc clip must populate truncated_lines"
    assert any(n > 0 for n, _ in d["truncated_lines"]), "real line numbers expected"
    hint = d.get("hint") or ""
    assert "per-line limit" in hint or "byte-range" in hint or "execute_code" in hint


def test_truncated_lines_bounded_on_bundle_page(tmp_path, ops):
    """truncated_lines must be bounded: minified-bundle pages where every line
    clips cannot amplify the tool response past the char budget.

    Review finding (major): 2000 clipped lines used to serialize ~280K chars of
    repeated identical reason strings (3.8x the content described). The list is
    now capped at ShellFileOperations._MAX_TRUNCATED_LINES entries plus one
    terminal count marker.
    """
    p = _write(tmp_path, "bundle.js", "\n".join("A" * (get_max_line_length() + 100) for _ in range(2000)))
    result = ops.read_file(p, limit=2000)
    assert result.error is None
    assert result.truncated is True
    tl = result.truncated_lines
    assert tl is not None
    cap = ShellFileOperations._MAX_TRUNCATED_LINES
    assert len(tl) <= cap + 1
    if len(tl) == cap + 1:
        line_no, reason = tl[-1]
        assert line_no == -1
        assert "clipped" in reason
    d = result.to_dict()
    # The metadata field is bounded (the 100K content budget is applied by the
    # file_tools layer, not ops.read_file): the serialized truncated_lines must
    # stay small even when every line on the page clipped.
    assert len(json.dumps(d["truncated_lines"])) < 8_000  # bounded, not 3.8x amplified


def test_hint_merges_budget_and_clip_guidance(tmp_path):
    """A page that both clips lines and exceeds the char budget must carry BOTH
    the per-line recovery recipe and the budget continuation hint.

    Review finding (minor): _apply_char_budget used to overwrite the clip
    recovery hint; the model following offset= never saw the byte-range recipe.
    Asserts at the tool layer (file_tools), where the char budget is applied.
    """
    from tools.file_tools import read_file_tool

    # enough over-limit lines to blow past the 100K read budget
    p = _write(tmp_path, "big.txt", "\n".join("B" * (get_max_line_length() + 100) for _ in range(600)))
    raw = read_file_tool(p, 1, 5000)
    d = json.loads(raw)
    assert d["truncated"] is True
    hint = d.get("hint") or ""
    assert "Use offset=" in hint  # budget continuation survives
    assert "per-line" in hint or "byte-range" in hint  # clip recipe survives


def test_below_limit_no_clip_metadata(tmp_path, ops):
    """A line below the per-line limit: truncated_lines absent, truncated False."""
    max_len = get_max_line_length()
    p = _write(tmp_path, "short.txt", "x" * (max_len - 1) + "\n")
    result = ops.read_file(p)
    assert result.error is None
    assert result.truncated is False
    assert result.truncated_lines is None
    assert "[truncated]" not in result.content
    d = result.to_dict()
    assert "truncated_lines" not in d  # omitted when empty, backward-compatible


def test_at_limit_no_clip_metadata(tmp_path, ops):
    """Exactly at the limit is NOT clipped (the clamp is len(line) > max)."""
    max_len = get_max_line_length()
    p = _write(tmp_path, "exact.txt", "x" * max_len + "\n")
    result = ops.read_file(p)
    assert result.error is None
    assert result.truncated is False
    assert result.truncated_lines is None
    assert "[truncated]" not in result.content


def test_above_limit_one_line_json_fixture(tmp_path, ops):
    """The issue's reproduction: one long JSON line clips and MUST be truncated=True.

    A metadata consumer must not mistake the rendered (invalid) JSON for the
    complete artifact: the clip point sits inside the evidence string, so the
    closing syntax is gone.
    """
    payload = json.dumps({"evidence": "x" * 3000})
    p = _write(tmp_path, "fixture.json", payload + "\n")
    result = ops.read_file(p, limit=10)
    assert result.error is None
    assert result.total_lines == 1
    # The core regression: clipping marks the response truncated.
    assert result.truncated is True
    # The clipped line is named with a reason.
    assert result.truncated_lines == [(1, result.truncated_lines[0][1])]
    assert result.truncated_lines[0][0] == 1
    assert "display limit" in result.truncated_lines[0][1]
    # The recovery hint names a bounded/lossless path.
    assert "Per-line clipping occurred" in result.hint
    assert "1" in result.hint
    # And the rendered marker is still there for visual consumers.
    assert "... [truncated]" in result.content
    # Metadata serializes: to_dict carries the new field when clipping happened.
    d = result.to_dict()
    assert d["truncated"] is True
    assert d["truncated_lines"] == [(1, result.truncated_lines[0][1])]
    assert "truncated_lines" in json.dumps(d)  # JSON-safe shapes


def test_long_line_inside_multiline_file(tmp_path, ops):
    """A clipped line among normal lines: only that line is reported, neighbors
    intact, and reading CONTINUES past it — the clip does not truncate the page."""
    max_len = get_max_line_length()
    p = _write(
        tmp_path, "mixed.txt",
        "first\n" + "y" * (2 * max_len) + "\nthird\n" + "z" * (3 * max_len) + "\nlast\n")
    result = ops.read_file(p)
    assert result.error is None
    # Page contains every requested line (line truncation did not fire).
    assert result.truncated is True  # per-line clipping alone sets it now
    lines = result.content.split("\n")
    assert lines[0] == "1|first"
    assert lines[1] == "2|" + "y" * max_len + "... [truncated]"
    assert lines[2] == "3|third"
    assert lines[3] == "4|" + "z" * max_len + "... [truncated]"
    assert lines[4] == "5|last"
    # Metadata names exactly the two clipped lines.
    assert [n for n, _ in result.truncated_lines] == [2, 4]
    # total_lines is the real file line count — the page itself was complete.
    assert result.total_lines == 5
    # Continuation: the hint carries the clip notice (no offset hint needed —
    # the whole file fit in the page).
    assert "Per-line clipping" in result.hint
    assert "Use offset=" not in (result.hint or "")


def test_offset_page_reports_in_file_line_numbers(tmp_path, ops):
    """Clipped lines are reported with IN-FILE line numbers even on later pages."""
    max_len = get_max_line_length()
    body = "a\n" * 3 + "b" * (2 * max_len) + "\n" + "tail\n"
    p = _write(tmp_path, "paged.txt", body)
    result = ops.read_file(p, offset=3, limit=3)  # lines 3,4,5
    assert result.error is None
    assert [n for n, _ in result.truncated_lines] == [4]
    assert result.content.split("\n")[1] == "4|" + "b" * max_len + "... [truncated]"


def test_clip_and_page_truncation_combine(tmp_path, ops):
    """Both truncations at once: the page hint and the clip notice are joined."""
    max_len = get_max_line_length()
    body = "c" * (2 * max_len) + "\n" + ("line\n" * 50)
    p = _write(tmp_path, "both.txt", body)
    result = ops.read_file(p, limit=10)
    assert result.error is None
    assert result.truncated is True
    assert result.total_lines == 51
    assert [n for n, _ in result.truncated_lines] == [1]
    assert "Use offset=11" in result.hint        # page continuation
    assert "Per-line clipping occurred: lines 1" in result.hint  # clip notice


def test_shell_fallback_path_reports_clipping(tmp_path, ops, monkeypatch):
    """The sequential fallback path (no native read, unparseable probe) reports
    clipping too — the metadata contract holds on every read path."""
    max_len = get_max_line_length()
    p = _write(tmp_path, "fallback.txt", "q" * (2 * max_len) + "\nnormal\n")
    # Force the sequential path: disable the native fast path AND break the
    # compound probe by neutering _split_segments recognition.
    monkeypatch.setattr(ops, "_native_read_enabled", lambda: False)
    monkeypatch.setattr(ops, "_read_probe_cmd",
                        lambda *a, **k: "echo __hr_no_sentinel__")
    result = ops.read_file(p)
    assert result.error is None
    assert result.truncated is True
    assert [n for n, _ in result.truncated_lines] == [1]


def test_reason_is_stable_and_path_agnostic():
    """The reason string is deterministic (same limit → same text) and never
    names an internal layer, so rendered docs stay stable across transports."""
    from tools.file_operations import ShellFileOperations as S
    r1 = S._line_clip_reason()
    r2 = S._line_clip_reason()
    assert r1 == r2
    assert "sed" not in r1 and "cut" not in r1