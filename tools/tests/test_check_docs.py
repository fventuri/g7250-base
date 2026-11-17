"""Self-test for tools/check_docs.py (CONF check), on synthetic Markdown only.

Run from the repository root:
    python3 -m unittest discover -s tools/tests -v
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_TOOL = Path(__file__).resolve().parent.parent / "check_docs.py"
_spec = importlib.util.spec_from_file_location("check_docs", _TOOL)
check_docs = importlib.util.module_from_spec(_spec)
sys.modules["check_docs"] = check_docs
_spec.loader.exec_module(check_docs)


def conf_lines(markdown: str, conf_all: bool = False) -> list[int]:
    """Line numbers of the CONF warnings check_docs reports for this document."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        doc = root / "docs" / "synthetic.md"
        doc.write_text(textwrap.dedent(markdown).lstrip("\n"), encoding="utf-8")
        findings: list = []
        check_docs.check_file(doc, root, {}, set(), findings, conf_all)
    return [no for sev, kind, _rel, no, _msg in findings if kind == "CONF"]


class BaselineTest(unittest.TestCase):
    def test_untagged_finding_warns(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            The handler `FUN_0802abcd` writes the flag.
            """), [5])

    def test_tagged_paragraph_and_table_column(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            The handler `FUN_0802abcd` writes the flag (HIGH CONFIDENCE).

            | addr | what | confidence |
            | --- | --- | --- |
            | `0x0802abcd` | handler | VERIFIED |
            | `0x0802abd0` | helper | |
            """), [10])  # the empty confidence cell is still reported

    def test_paragraph_tag_wrapped_inside_paragraph(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            The handler `FUN_0802abcd` writes the flag (HIGH
            CONFIDENCE).
            """), [])


class WrappedStatusTest(unittest.TestCase):  # (a)
    def test_document_status_wrapped_onto_next_line(self):
        self.assertEqual(conf_lines("""
            # Doc

            Status: the structure and data paths described here are VERIFIED
            unless noted.

            ## Section

            The handler `FUN_0802abcd` writes the flag.
            """), [])

    def test_status_split_by_blank_line_does_not_count(self):
        self.assertEqual(conf_lines("""
            # Doc

            Status: the structure and data paths described here are VERIFIED

            unless noted.

            ## Section

            The handler `FUN_0802abcd` writes the flag.
            """), [9])

    def test_unless_marked(self):
        self.assertEqual(conf_lines("""
            # Doc

            Status: VERIFIED unless marked.

            ## Section

            The handler `FUN_0802abcd` writes the flag.
            """), [])

    def test_conf_all_ignores_document_status(self):
        self.assertEqual(conf_lines("""
            # Doc

            Status: VERIFIED unless
            noted.

            ## Section

            The handler `FUN_0802abcd` writes the flag.
            """, conf_all=True), [8])


class SectionStatusTest(unittest.TestCase):  # (b)
    DOC = """
        # Doc

        intro without a status line, padding the first lines of the document so
        that the document-level status search does not reach the sections below.
        .
        .
        .
        .
        .
        .
        .
        .

        ## Tagged — VERIFIED unless noted

        The handler `FUN_0802abcd` writes the flag.

        ### Sub-section

        The helper `FUN_0802abd0` reads it.

        ## Second section

        Status: HIGH CONFIDENCE unless
        marked.

        The helper `FUN_0802abe0` clears it.

        ### Deeper

        The helper `FUN_0802abf0` sets it.

        ## Untagged

        The helper `FUN_0802ac00` toggles it.
        """

    def test_heading_and_section_status_tag_their_sections(self):
        lines = textwrap.dedent(self.DOC).lstrip("\n").splitlines()
        untagged = next(i for i, l in enumerate(lines, 1) if "FUN_0802ac00" in l)
        self.assertEqual(conf_lines(self.DOC), [untagged])

    def test_conf_all_ignores_section_status_but_not_heading(self):
        lines = textwrap.dedent(self.DOC).lstrip("\n").splitlines()
        want = [i for i, l in enumerate(lines, 1)
                if any(f in l for f in ("FUN_0802abe0", "FUN_0802abf0", "FUN_0802ac00"))]
        self.assertEqual(conf_lines(self.DOC, conf_all=True), want)

    def test_status_must_open_the_section(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            The handler `FUN_0802abcd` writes the flag.

            Everything else is VERIFIED unless noted.
            """), [5])


class BoldLeadInTest(unittest.TestCase):  # (c)
    def test_tagged_lead_in_covers_bullets(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            **Audio packets (HIGH).** The stream is paced by a timer.
            - **Header.** a fixed `0x0080` ident at offset 0x10.
            - Packet table: see `FUN_0802abcd`.
              continued on a second line `0x0802abd0`.
            """), [])

    def test_tag_after_bold_on_the_lead_line(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            **Screens** (`state`, offset +0x920; VERIFIED unless noted).
            - **Writers:** the handler `FUN_0802abcd`.
            - **Readers:** the dispatcher `FUN_0802abd0`.
            """), [])

    def test_untagged_lead_in_still_warns(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            **What it does:**
            - turns the frequency into `0x0103` commands.
            """), [6])

    def test_plain_lead_in_paragraph_is_not_a_bold_lead_in(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            No match falls outside the regions (VERIFIED). Results:
            - `FUN_0802abcd` is the wrapper.
            """), [6])

    def test_list_must_follow_directly(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            **Audio packets (HIGH).** The stream is paced by a timer.

            - the handler `FUN_0802abcd`.
            """), [7])

    def test_loose_list_and_end_of_list(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            **Audio packets (HIGH).**
            - the handler `FUN_0802abcd`.

            - the helper `FUN_0802abd0`.

            After the list `FUN_0802abe0` is no longer covered.
            """), [10])

    def test_nested_items_under_tagged_bold_item(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            - **Playback** (`FUN_0802abcd`, VERIFIED).
              - checks the header, then `FUN_0802abd0`;
                1. step one `0x0802abe0`.
            - **Other** (`FUN_0802abf0`, HIGH).
            - plain item `FUN_0802ac00`.
            """), [9])

    def test_exempt_lead_in_topic(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            **Blocking unknowns:**
            - whether `0x0103` retunes the VFO;
            - the scaling in `0x0202`.
            """), [])

    def test_lead_in_does_not_leak_past_heading_or_table(self):
        self.assertEqual(conf_lines("""
            # Doc

            ## Section

            **Audio packets (HIGH).**
            - the handler `FUN_0802abcd`.

            ## Next

            - the helper `FUN_0802abd0`.
            """), [10])


if __name__ == "__main__":
    unittest.main()
