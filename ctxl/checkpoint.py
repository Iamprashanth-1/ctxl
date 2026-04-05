"""
ctx checkpoint — Session state manager.

Tracks what the AI agent has learned during a session (files edited,
schemas discovered, errors resolved) and saves a compressed checkpoint.
This allows you to safely run /clear in Copilot Chat without losing context.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


CHECKPOINT_DIR = ".ctx_checkpoints"


def _ensure_dir(project_root: str) -> Path:
    """Ensure the checkpoint directory exists."""
    path = Path(project_root).resolve() / CHECKPOINT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_checkpoint(
    project_root: str,
    task: str,
    completed_steps: List[str],
    current_state: str,
    next_steps: List[str],
    files_modified: Optional[List[str]] = None,
    key_discoveries: Optional[List[str]] = None,
    errors_resolved: Optional[List[str]] = None,
) -> str:
    """
    Create a checkpoint file capturing the current session state.

    Args:
        project_root: Path to the project root directory.
        task: The high-level task description.
        completed_steps: List of steps already completed.
        current_state: Brief description of where things stand right now.
        next_steps: List of planned next steps.
        files_modified: List of files that were modified.
        key_discoveries: Key things learned (schemas, configs, etc.).
        errors_resolved: Errors that were encountered and resolved.

    Returns:
        Path to the created checkpoint file.
    """
    checkpoint_dir = _ensure_dir(project_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"checkpoint_{timestamp}.md"
    filepath = checkpoint_dir / filename

    lines = []
    lines.append(f"# Session Checkpoint")
    lines.append(f"_Saved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n")

    lines.append(f"## Task")
    lines.append(f"{task}\n")

    lines.append(f"## Current State")
    lines.append(f"{current_state}\n")

    if completed_steps:
        lines.append("## Completed Steps")
        for step in completed_steps:
            lines.append(f"- [x] {step}")
        lines.append("")

    if next_steps:
        lines.append("## Next Steps")
        for step in next_steps:
            lines.append(f"- [ ] {step}")
        lines.append("")

    if files_modified:
        lines.append("## Files Modified")
        for f in files_modified:
            lines.append(f"- `{f}`")
        lines.append("")

    if key_discoveries:
        lines.append("## Key Discoveries")
        for d in key_discoveries:
            lines.append(f"- {d}")
        lines.append("")

    if errors_resolved:
        lines.append("## Errors Resolved")
        for e in errors_resolved:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("---")
    lines.append("_Paste this into your active file or Copilot Chat after running `/clear`._")

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")

    return str(filepath)


def list_checkpoints(project_root: str) -> List[Dict]:
    """List all checkpoints in the project, newest first."""
    checkpoint_dir = Path(project_root).resolve() / CHECKPOINT_DIR
    if not checkpoint_dir.exists():
        return []

    checkpoints = []
    for f in sorted(checkpoint_dir.glob("checkpoint_*.md"), reverse=True):
        stat = f.stat()
        checkpoints.append({
            "filename": f.name,
            "path": str(f),
            "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size_bytes": stat.st_size,
        })

    return checkpoints


def get_latest_checkpoint(project_root: str) -> Optional[str]:
    """Read the content of the most recent checkpoint."""
    checkpoints = list_checkpoints(project_root)
    if not checkpoints:
        return None
    latest_path = checkpoints[0]["path"]
    return Path(latest_path).read_text(encoding="utf-8")
