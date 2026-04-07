"""Project Brain — auto-generated tpcontext.md per project.

Automatically maintains a tpcontext.md in the project root. No manual save needed.
- On session start: auto-save previous session + load brain into context
- On first install: bootstraps from git history
- Keeps last 5 sessions, stays under 2K tokens
"""

import os
import subprocess
import time
from datetime import datetime

import db

BRAIN_FILE = "tpcontext.md"
MAX_SESSIONS = 5


def _get_project_dir() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _get_git_modified_files() -> list[str]:
    files = set()
    try:
        for cmd in [
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "diff", "--name-only", "--cached"],
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        ]:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                files.update(f.strip() for f in result.stdout.strip().split("\n") if f.strip())
    except Exception:
        pass
    return sorted(files)


def _get_recent_commits(n: int = 5) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--oneline"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    except Exception:
        pass
    return []


def _get_git_summary_for_bootstrap() -> str:
    """Analyze git history to bootstrap a brain for an existing project."""
    lines = []

    # Project name
    project_dir = _get_project_dir()
    name = os.path.basename(project_dir) if project_dir else "unknown"

    # Recent activity (last 10 commits)
    commits = _get_recent_commits(10)

    # Most-changed files (from last 20 commits)
    hot_files = []
    try:
        result = subprocess.run(
            ["git", "log", "--pretty=format:", "--name-only", "-20"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            from collections import Counter
            files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
            hot_files = [f"{path} ({count}x)" for path, count in Counter(files).most_common(8)]
    except Exception:
        pass

    # Current branch
    branch = "unknown"
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except Exception:
        pass

    # Build bootstrap content
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"""# {name} — Project Context
Last updated: {now}

## Overview
Branch: {branch}

## Recent Activity
"""
    for c in commits[:7]:
        content += f"- {c}\n"

    if hot_files:
        content += "\n## Key Files (most active)\n"
        for f in hot_files[:6]:
            content += f"- {f}\n"

    content += "\n## Sessions\n(Auto-tracked by TokenPilot)\n"
    content += "\n## Notes\n(Add with `/tp note \"...\"`)\n"

    return content


def _get_project_name() -> str:
    project_dir = _get_project_dir()
    return os.path.basename(project_dir) if project_dir else "unknown"


def get_brain_path() -> str | None:
    project_dir = _get_project_dir()
    if not project_dir:
        return None
    return os.path.join(project_dir, BRAIN_FILE)


def load_brain() -> str | None:
    path = get_brain_path()
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None


def auto_save() -> dict:
    """Auto-save brain. Called on session start to capture previous session,
    or bootstraps from git history if no brain exists yet."""
    project_dir = _get_project_dir()
    if not project_dir:
        return {"status": "skip", "reason": "No project directory found."}

    # Skip if we're in the home directory (not a real project)
    home = os.path.expanduser("~")
    if project_dir == home:
        return {"status": "skip", "reason": "Home directory, not a project."}

    brain_path = os.path.join(project_dir, BRAIN_FILE)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Gather current state
    modified_files = _get_git_modified_files()
    recent_commits = _get_recent_commits(5)
    notes = db.get_brain_notes()

    # Try to get session stats (may be empty if this is first call)
    try:
        stats = db.get_stats()
        prompts = stats.get("total_prompts", 0)
        minutes = stats.get("session_minutes", 0)
    except Exception:
        prompts = 0
        minutes = 0

    existing = load_brain()

    if not existing:
        # First time — bootstrap from git history
        content = _get_git_summary_for_bootstrap()
        with open(brain_path, "w") as f:
            f.write(content)
        return {"status": "bootstrapped", "path": brain_path}

    # Build session entry (only if there's something to record)
    if prompts > 0 or modified_files:
        session_entry = f"### {now} ({minutes} min, {prompts} prompts)\n"
        if modified_files:
            session_entry += "- Modified: " + ", ".join(modified_files[:8])
            if len(modified_files) > 8:
                session_entry += f" (+{len(modified_files) - 8} more)"
            session_entry += "\n"
        if recent_commits:
            for c in recent_commits[:3]:
                session_entry += f"- {c}\n"
        if notes:
            for n in notes:
                session_entry += f"- Note: {n}\n"

        # Merge into existing brain
        if "## Sessions" in existing:
            parts = existing.split("## Sessions")
            header = parts[0]
            sessions_text = parts[1] if len(parts) > 1 else ""

            # Split into notes section and session entries
            notes_split = sessions_text.split("## Notes")
            session_part = notes_split[0]
            notes_part = notes_split[1] if len(notes_split) > 1 else ""

            # Keep last MAX_SESSIONS - 1 entries
            entries = [s for s in session_part.split("### ") if s.strip()]
            kept = entries[:MAX_SESSIONS - 1]

            content = header + "## Sessions\n"
            content += session_entry + "\n"
            for e in kept:
                content += f"### {e}"
            if notes_part:
                content += "\n## Notes" + notes_part
        else:
            content = existing + f"\n## Sessions\n{session_entry}\n"

        # Update timestamp
        for line in content.split("\n"):
            if line.startswith("Last updated:"):
                content = content.replace(line, f"Last updated: {now}")
                break

        with open(brain_path, "w") as f:
            f.write(content)
        return {"status": "updated", "path": brain_path, "prompts": prompts}

    return {"status": "unchanged", "path": brain_path}


def add_note(note: str) -> dict:
    """Add a note to both the DB (for session tracking) and directly to the brain file."""
    db.record_project_note(note)

    brain_path = get_brain_path()
    if not brain_path:
        return {"status": "saved_to_db_only"}

    existing = load_brain()
    if not existing:
        # Bootstrap first, then add note
        auto_save()
        existing = load_brain()

    if existing and "## Notes" in existing:
        content = existing.rstrip() + f"\n- {note}\n"
        with open(brain_path, "w") as f:
            f.write(content)
        return {"status": "saved", "note": note}

    return {"status": "saved_to_db_only", "note": note}
