# Issue #1152 — Report per-line clipping in read_file truncation metadata

**Branch:** `fix/gh-1152-225b4f7b2c45`
**Commits:** 73a05e175 (fix), 548337e46 (tests)
**Status:** Implemented, verified. Ready for pre-PR review.

## Root cause

`read_file` clamps each rendered line at `max_line_length` chars (the
`... [truncated]` marker), but `truncated` reflected only *page* truncation
(`total_lines > end_line`) — set solely in `_assemble_read_result`. Per-line
clipping therefore returned `truncated: false` with no metadata naming the
loss. A machine consumer parsing the rendered JSON fixture got invalid JSON
(clip point inside the string, closing syntax gone) that *looked complete*.

## Change

1. **`ReadResult.truncated_lines: Optional[List[tuple]]`** (`tools/file_operations_common.py`)
   — `(line_no, reason)` per clipped line, 1-indexed in-file; `None`/omitted
   when no clipping (backward-compatible `to_dict`).
2. **`_add_line_numbers(..., clip_log)`** (`tools/file_operations.py`) — the
   single renderer used by every read path now records each clip with a
   stable, path-agnostic reason string (`_line_clip_reason`).
3. **`_assemble_read_result`** — the choke point for compound/sequential/native
   paths: sets `truncated = True` on any clip, merges the clip notice into the
   hint (joined with the page-continuation hint when both fire), exposes
   `truncated_lines`, and names a bounded recovery path (terminal byte-range
   read or lossless `execute_code` load). Response-size limits untouched.
4. **UTF-16 transcode path** — same metadata treatment (`truncated`,
   `truncated_lines`, hint), since it renders through the same clamp.

No recovery-in-band: the issue's "bounded recovery" is directed to existing
lossless surfaces (`execute_code`, terminal byte ranges) rather than adding a
new tool, per the minimal-footprint rule in tools/AGENTS.md.

## Tests (`tests/tools/test_read_line_clip_metadata.py`, 8 cases)

Below/at/above the per-line limit; the issue's one-line JSON fixture;
long line inside multiline (only that line reported, neighbors intact, page
complete); in-file line numbers on later pages; clip+page truncation
combined (both hints joined); sequential-fallback path; reason stability.

Full read-related suites re-run: `test_read_shell_line_clamp`, `test_file_operations`,
`test_file_operations_edge_cases`, `test_read_past_eof_note`, `test_utf16_read`,
`test_read_extract`, `test_file_read_guards`, `test_file_ops_single_roundtrip`,
`test_read_loop_detection`, `test_tool_output_limits`, `test_file_ops_cwd_tracking`,
`test_file_staleness`, `test_patch_*`, `test_write_file_rewrite_hint`,
`test_search_*` — **412 passed, 7 skipped, 0 new failures**.

The 4 failures seen in `test_file_tools.py` / `test_read_special_file_guard.py` /
`test_read_file_utf8_binary_regression.py` reproduce identically on
`origin/main` (baseline-verified in a detached worktree) — pre-existing
environment issues (`AF_UNIX path too long` for socket tests; mock-assertion
mismatches), not caused by this change.

## Issue acceptance mapping

- "Mark any content clipping as truncated: true" → (3)
- "expose the affected line/range and truncation reason" → (1), (2), (3)
- "bounded way to recover a long line without silently dropping its suffix,
  or explicitly direct machine consumers to a lossless artifact-reading
  interface" → hint names both; per-line suffix stays bounded, suffix never
  silently dropped (marker + metadata always present)
- "Preserve response-size limits" → no limit changes anywhere in the diff
- "regression cases below, at and above the per-line limit, for one-line
  JSON and a long line within a multi-line file. Verify metadata and
  continuation behavior, not merely the visible marker" → all present