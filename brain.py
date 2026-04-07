"""Project Brain — auto-generated context.md per project.

Maintains a .tokenpilot/context.md in the project directory that acts as
persistent memory across Claude Code sessions. Captures what was worked on,
files modified, decisions made, and where the user left off.
"""

import os
import subprocess
import time
from datetime import datetime

import db

BRAIN_DIR = ".tokenpilot"
BRAIN_FILE = "context.md"
MAX_SESSIONS = 5  # Keep last N sessions in the brain


def _get_project_dir() -> str | None:
    """Get the current git project root, or cwd if not in a git repo."""
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
    """Get files modified in the current session (uncommitted + recent commits)."""
    files = set()
    try:
        # Uncommitted changes
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            files.update(f.strip() for f in result.stdout.strip().split("\n") if f.strip())

        # Staged changes
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            files.update(f.strip() for f in result.stdout.strip().split("\n") if f.strip())

        # Last commit (likely from this session)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            files.update(f.strip() for f in result.stdout.strip().split("\n") if f.strip())
    except Exception:
        pass
    return sorted(files)


def _get_recent_commits(n: int = 3) -> list[str]:
    """Get last N commit messages."""
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


def _get_project_name() -> str:
    project_dir = _get_project_dir()
    return os.path.basename(project_dir) if project_dir else "unknown"


def get_brain_path() -> str | None:
    """Get path to the brain file for the current project."""
    project_dir = _get_project_dir()
    if not project_dir:
        return None
    return os.path.join(project_dir, BRAIN_DIR, BRAIN_FILE)


def load_brain() -> str | None:
    """Load existing brain content. Returns None if no brain exists."""
    path = get_brain_path()
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None


def save_brain() -> dict:
    """Generate and save the project brain from current session data."""
    project_dir = _get_project_dir()
    if not project_dir:
        return {"status": "error", "message": "Could not determine project directory."}

    brain_dir = os.path.join(project_dir, BRAIN_DIR)
    brain_path = os.path.join(brain_dir, BRAIN_FILE)

    # Ensure .tokenpilot/ directory exists
    os.makedirs(brain_dir, exist_ok=True)

    # Add to .gitignore if not already there
    gitignore_path = os.path.join(brain_dir, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w") as f:
            f.write("# TokenPilot session data\n*.db\n")

    # Gather session data
    stats = db.get_stats()
    notes = db.get_brain_notes()
    modified_files = _get_git_modified_files()
    recent_commits = _get_recent_commits(3)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    project_name = _get_project_name()

    # Build current session entry
    session_entry = f"### {now} ({stats['session_minutes']} min, {stats['total_prompts']} prompts)\n"
    if modified_files:
        session_entry += "- Modified: " + ", ".join(modified_files[:10])
        if len(modified_files) > 10:
            session_entry += f" (+{len(modified_files) - 10} more)"
        session_entry += "\n"
    if recent_commits:
        session_entry += "- Recent commits:\n"
        for c in recent_commits:
            session_entry += f"  - {c}\n"
    if notes:
        session_entry += "- Notes:\n"
        for n in notes:
            session_entry += f"  - {n}\n"

    # Load existing brain and merge
    existing = load_brain()
    if existing:
        # Extract existing sessions section
        parts = existing.split("## Recent Sessions")
        header = parts[0]

        if len(parts) > 1:
            sessions_text = parts[1]
            # Count existing sessions (each starts with ###)
            existing_sessions = [s for s in sessions_text.split("### ") if s.strip()]
            # Keep only last MAX_SESSIONS - 1 (to make room for the new one)
            kept = existing_sessions[: MAX_SESSIONS - 1]
            sessions_block = session_entry + "\n" + "".join(f"### {s}" for s in kept)
        else:
            sessions_block = session_entry

        # Rebuild
        content = header + "## Recent Sessions\n" + sessions_block
    else:
        # New brain
        content = f"""# Project Context — {project_name}
Last updated: {now}

## Current Focus
(Auto-generated by TokenPilot. Add notes with `/tp note "..."`)

## Recent Sessions
{session_entry}
## Key Files
"""
        # Add most-read files from session
        try:
            conn = db._connect()
            top_files = conn.execute("""
                SELECT path, COUNT(*) as reads FROM file_reads
                GROUP BY path ORDER BY reads DESC LIMIT 5
            """).fetchall()
            conn.close()
            for f_path, reads in top_files:
                short = f_path.split("/")[-1] if "/" in f_path else f_path
                content += f"- {short} (read {reads}x)\n"
        except Exception:
            pass

        content += "\n## Notes\n"
        for n in notes:
            content += f"- {n}\n"

    # Update timestamp
    content = content.replace(
        content.split("\n")[1] if "Last updated:" in content else "",
        f"Last updated: {now}",
        1,
    )

    # Write
    with open(brain_path, "w") as f:
        f.write(content)

    return {
        "status": "saved",
        "path": brain_path,
        "session_prompts": stats["total_prompts"],
        "files_modified": len(modified_files),
        "notes": len(notes),
    }
