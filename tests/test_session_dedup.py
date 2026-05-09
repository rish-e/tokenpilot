"""Tests for session_dedup.py — mtime-aware dedup tracker.

Covers the key delta vs tracker.py: file-edit invalidation.
All other behavior should match tracker.py exactly (backward compat).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from session_dedup import SessionTracker, get_session, reset_session


def fresh() -> SessionTracker:
    return SessionTracker(level=4)


# ---------------------------------------------------------------------------
# Backward-compat with tracker.py
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_first_read_allowed(self):
        s = fresh()
        with patch.object(SessionTracker, "_current_mtime", return_value=1.0):
            result = s.check_file("/f.py")
        assert result["action"] == "allow"

    def test_exact_duplicate_warns(self):
        s = fresh()
        with patch.object(SessionTracker, "_current_mtime", return_value=1.0):
            s.record_read("/f.py", offset=0, limit=0)
            result = s.check_file("/f.py", offset=0, limit=0)
        assert result["action"] == "warn"
        assert result["already_read"] is True

    def test_full_covers_partial(self):
        s = fresh()
        with patch.object(SessionTracker, "_current_mtime", return_value=1.0):
            s.record_read("/f.py", offset=0, limit=0)
            result = s.check_file("/f.py", offset=10, limit=50)
        assert result["action"] == "warn"

    def test_different_files_independent(self):
        s = fresh()
        with patch.object(SessionTracker, "_current_mtime", return_value=1.0):
            s.record_read("/a.py")
            result = s.check_file("/b.py")
        assert result["action"] == "allow"

    def test_return_shape(self):
        s = fresh()
        with patch.object(SessionTracker, "_current_mtime", return_value=1.0):
            result = s.check_file("/x.py")
        assert set(result.keys()) >= {"action", "message", "already_read", "previous_ranges"}


# ---------------------------------------------------------------------------
# mtime invalidation (the new behaviour)
# ---------------------------------------------------------------------------

class TestMtimeInvalidation:
    def test_changed_mtime_allows_reread(self):
        """Core fix: file was edited between reads → re-read should be allowed."""
        s = fresh()
        # First read — mtime 1.0
        with patch.object(SessionTracker, "_current_mtime", return_value=1.0):
            s.record_read("/edited.py", offset=0, limit=0)
        # File modified → mtime 2.0
        with patch.object(SessionTracker, "_current_mtime", return_value=2.0):
            result = s.check_file("/edited.py", offset=0, limit=0)
        assert result["action"] == "allow", (
            "After editing a file the re-read must be allowed, not warned"
        )

    def test_unchanged_mtime_still_warns(self):
        """Sanity: if mtime didn't change, dedup still fires."""
        s = fresh()
        with patch.object(SessionTracker, "_current_mtime", return_value=5.0):
            s.record_read("/same.py")
            result = s.check_file("/same.py")
        assert result["action"] == "warn"

    def test_zero_mtime_treated_conservatively(self):
        """mtime=0 (unreadable file) → keep record → warn on re-read."""
        s = fresh()
        with patch.object(SessionTracker, "_current_mtime", return_value=0.0):
            s.record_read("/tmp_virtual.py")
            result = s.check_file("/tmp_virtual.py")
        # With mtime=0 on both sides, we keep the record conservatively
        assert result["action"] == "warn"

    def test_multiple_edits(self):
        """Read → edit → read → edit → read: each post-edit read should be allowed."""
        s = fresh()
        with patch.object(SessionTracker, "_current_mtime", return_value=1.0):
            s.record_read("/f.py")
        with patch.object(SessionTracker, "_current_mtime", return_value=2.0):
            result = s.check_file("/f.py")
            assert result["action"] == "allow"
            s.record_read("/f.py")  # now record the second read (mtime=2)
        with patch.object(SessionTracker, "_current_mtime", return_value=3.0):
            result = s.check_file("/f.py")
            assert result["action"] == "allow"


# ---------------------------------------------------------------------------
# Stats (same interface as tracker.py)
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_shape(self):
        s = fresh()
        st = s.get_stats()
        expected_keys = {
            "session_minutes", "level", "total_prompts", "classifications",
            "files_read", "total_reads", "redundant_reads_blocked",
            "estimated_file_tokens", "estimated_tokens_saved",
        }
        assert expected_keys <= set(st.keys())

    def test_savings_shape(self):
        s = fresh()
        sv = s.get_savings()
        assert "tokens_saved_file_dedup" in sv
        assert "reads_blocked" in sv
        assert "tip" in sv


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def setup_method(self):
        reset_session()

    def teardown_method(self):
        reset_session()

    def test_same_object(self):
        assert get_session() is get_session()

    def test_reset_gives_new(self):
        s1 = get_session()
        s2 = reset_session()
        assert s1 is not s2
        assert get_session() is s2
