"""Parser tests. Every finding's location comes from this parser."""

from __future__ import annotations

from greenwash.core.diff import parse_diff


def test_simple_modification_tracks_line_numbers():
    diff = """diff --git a/billing.py b/billing.py
--- a/billing.py
+++ b/billing.py
@@ -10,1 +10,1 @@
-    return round(price, 2)
+    return round(price, 3)
"""
    (change,) = parse_diff(diff)
    assert change.path == "billing.py"
    assert change.removed[0].old_lineno == 10
    assert change.added[0].new_lineno == 10
    assert change.added[0].text == "    return round(price, 3)"


def test_multi_hunk_line_arithmetic():
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -5,0 +6,2 @@
+first
+second
@@ -40,2 +42,1 @@
-old_a
-old_b
+merged
"""
    (change,) = parse_diff(diff)
    assert [ln.new_lineno for ln in change.added] == [6, 7, 42]
    assert [ln.old_lineno for ln in change.removed] == [40, 41]


def test_added_lines_from_different_hunks_are_not_adjacent():
    """Lines from different hunks must not be treated as neighbours.

    A flat `added` list makes line 7 and line 300 neighbours. Body lookups must
    therefore be scoped to a hunk, which requires the hunks to stay separate.
    """
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -5,0 +6,1 @@
+def process(order):
@@ -299,0 +301,1 @@
+    pass
"""
    (change,) = parse_diff(diff)
    assert len(change.hunks) == 2
    assert len(change.hunks[0].added) == 1
    assert len(change.hunks[1].added) == 1
    first, second = change.added
    assert second.new_lineno - first.new_lineno > 1  # not really adjacent


def test_new_file():
    diff = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+import os
+print(os)
"""
    (change,) = parse_diff(diff)
    assert change.is_new and not change.is_deleted
    assert [ln.new_lineno for ln in change.added] == [1, 2]


def test_deleted_file_recovers_path_from_old_header():
    diff = """diff --git a/tests/test_billing.py b/tests/test_billing.py
deleted file mode 100644
--- a/tests/test_billing.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def test_x():
-    assert True
"""
    (change,) = parse_diff(diff)
    assert change.path == "tests/test_billing.py"
    assert change.is_deleted
    assert len(change.removed) == 2


def test_rename_is_one_file_change():
    diff = """diff --git a/old/mod.py b/new/mod.py
similarity index 95%
rename from old/mod.py
rename to new/mod.py
--- a/old/mod.py
+++ b/new/mod.py
@@ -1,1 +1,1 @@
-x = 1
+x = 2
"""
    (change,) = parse_diff(diff)
    assert change.path == "new/mod.py"
    assert change.old_path == "old/mod.py"
    assert change.is_renamed


def test_binary_file_is_flagged_not_parsed():
    diff = """diff --git a/logo.png b/logo.png
index 1234567..89abcde 100644
Binary files a/logo.png and b/logo.png differ
"""
    (change,) = parse_diff(diff)
    assert change.path == "logo.png"
    assert change.is_binary
    assert change.added == [] and change.removed == []


def test_no_newline_marker_is_not_counted_as_a_line():
    diff = r"""diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1,1 +1,1 @@
-old
\ No newline at end of file
+new
\ No newline at end of file
"""
    (change,) = parse_diff(diff)
    assert len(change.added) == 1 and len(change.removed) == 1
    assert change.added[0].text == "new"


def test_crlf_is_stripped():
    diff = "diff --git a/a.py b/a.py\r\n--- a/a.py\r\n+++ b/a.py\r\n@@ -1,0 +1,1 @@\r\n+x = 1\r\n"
    (change,) = parse_diff(diff)
    assert change.added[0].text == "x = 1"


def test_windows_paths_are_normalised():
    diff = r"""diff --git a/src\pkg\mod.py b/src\pkg\mod.py
--- a/src\pkg\mod.py
+++ b/src\pkg\mod.py
@@ -1,0 +1,1 @@
+x = 1
"""
    (change,) = parse_diff(diff)
    assert change.path == "src/pkg/mod.py"


def test_empty_diff():
    assert parse_diff("") == []


def test_context_lines_advance_both_counters():
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -10,3 +10,3 @@
 unchanged
-removed
+added
"""
    (change,) = parse_diff(diff)
    assert change.removed[0].old_lineno == 11
    assert change.added[0].new_lineno == 11


def test_multiple_files_in_one_diff():
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,0 +1,1 @@
+a = 1
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,0 +1,1 @@
+b = 2
"""
    changes = parse_diff(diff)
    assert [c.path for c in changes] == ["a.py", "b.py"]


def test_removed_line_that_looks_like_a_header():
    """A removed `-- comment` line is emitted as `--- comment` inside a hunk.

    The hunk's line counts, not the prefix, decide what is a body line.
    """
    diff = """diff --git a/schema.sql b/schema.sql
--- a/schema.sql
+++ b/schema.sql
@@ -3,2 +3,1 @@
--- drop this comment
-SELECT 1;
+SELECT 2;
"""
    (change,) = parse_diff(diff)
    assert change.path == "schema.sql"
    assert [ln.text for ln in change.removed] == ["-- drop this comment", "SELECT 1;"]
    assert [ln.text for ln in change.added] == ["SELECT 2;"]


def test_added_line_that_looks_like_a_header():
    diff = """diff --git a/notes.md b/notes.md
--- a/notes.md
+++ b/notes.md
@@ -1,0 +1,1 @@
+++ bold claim
"""
    (change,) = parse_diff(diff)
    assert [ln.text for ln in change.added] == ["++ bold claim"]
