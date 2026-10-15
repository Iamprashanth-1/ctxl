"""
ctxl policy — Generate .github/AGENTOWNERS.yml governance policy.

Scans the repository for sensitive path patterns (CI workflows, auth config,
infrastructure, secrets) using filesystem heuristics and generates a
sensible-default AGENTOWNERS.yml policy file for AI agent governance.

AGENTOWNERS format: https://github.com/cschanhniem/AGENTOWNERS
Decision levels: block | require_approval | allow
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Directories that signal CI/CD workflow files → block
WORKFLOW_DIRS = {".github/workflows", ".gitlab/ci", ".circleci", ".travis"}

# Top-level directory names that signal infrastructure code → block
INFRA_DIRS = {
    "infra", "infrastructure", "terraform", "k8s", "kubernetes",
    "helm", "pulumi", "ansible", "cloudformation", "cdk",
}

# Top-level directory names / file prefixes that signal auth code → require_approval
AUTH_DIRS = {"auth", "authentication", "authorization", "oauth", "sso", "identity"}

# File glob patterns that signal auth files by name → require_approval
AUTH_FILE_PREFIXES = {"auth", "oauth", "jwt", "session", "token", "permission", "rbac", "acl"}
AUTH_FILE_SUFFIXES = {".py", ".ts", ".js", ".java", ".go", ".rb", ".rs"}

# Directory names signalling secrets / credential management → block
SECRETS_DIRS = {"secrets", "vault", ".secrets", "creds", "credentials"}

# File patterns that signal deployment scripts → block
DEPLOY_DIRS = {"deploy", "deployment", "release", "scripts/deploy", "scripts/release"}

# Top-level directory names for test code → allow (explicitly stated)
TEST_DIRS = {"tests", "test", "__tests__", "spec"}

# Top-level directory names for documentation → allow
DOCS_DIRS = {"docs", "doc", "documentation", "wiki"}


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------

@dataclass
class PolicySignals:
    """Detected signals from a repository scan."""

    has_workflows: bool = False
    workflow_paths: list = field(default_factory=list)

    has_auth: bool = False
    auth_paths: list = field(default_factory=list)

    has_infra: bool = False
    infra_paths: list = field(default_factory=list)

    has_secrets: bool = False
    secrets_paths: list = field(default_factory=list)

    has_deploy: bool = False
    deploy_paths: list = field(default_factory=list)

    has_tests: bool = False
    has_docs: bool = False


def _normalise(path: str) -> str:
    """Normalise a path to forward slashes."""
    return path.replace("\\", "/")


def scan_repository(root: Path) -> PolicySignals:
    """
    Walk the repository and detect governance-relevant path patterns.

    This is a pure filesystem scan — no Tree-sitter, no AI, no tokens.
    Returns a :class:`PolicySignals` summary of what was found.
    """
    signals = PolicySignals()

    # ── Top-level directory pass ──────────────────────────────────────────────
    try:
        top_level = [
            entry.name.lower()
            for entry in root.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        ]
        # Also include hidden top-level dirs that matter
        hidden_top = [
            entry.name.lower()
            for entry in root.iterdir()
            if entry.is_dir() and entry.name.startswith(".")
        ]
    except (OSError, PermissionError):
        return signals

    for name in top_level:
        if name in INFRA_DIRS:
            signals.has_infra = True
            signals.infra_paths.append(f"{name}/")
        if name in AUTH_DIRS:
            signals.has_auth = True
            signals.auth_paths.append(f"{name}/")
        if name in SECRETS_DIRS:
            signals.has_secrets = True
            signals.secrets_paths.append(f"{name}/")
        if name in DEPLOY_DIRS:
            signals.has_deploy = True
            signals.deploy_paths.append(f"{name}/")
        if name in TEST_DIRS:
            signals.has_tests = True
        if name in DOCS_DIRS:
            signals.has_docs = True

    for name in hidden_top:
        if name in {".secrets", ".vault"}:
            signals.has_secrets = True
            signals.secrets_paths.append(f"{name}/")

    # ── Workflow directories ──────────────────────────────────────────────────
    for wf_dir in WORKFLOW_DIRS:
        wf_path = root / Path(wf_dir)
        if wf_path.exists() and wf_path.is_dir():
            signals.has_workflows = True
            # Ensure trailing slash so _glob_lines emits "dir/**" not "dir"
            rel = _normalise(wf_dir).rstrip("/") + "/"
            if rel not in signals.workflow_paths:
                signals.workflow_paths.append(rel)

    # ── File-level auth detection (shallow scan, top 3 dirs deep) ────────────
    _scan_auth_files(root, signals)

    return signals


def _scan_auth_files(root: Path, signals: PolicySignals, max_depth: int = 3) -> None:
    """Scan for auth-pattern filenames within a bounded depth."""
    for dirpath_str, dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath_str)
        # Compute depth relative to root
        try:
            rel_parts = dirpath.relative_to(root).parts
        except ValueError:
            continue
        if len(rel_parts) > max_depth:
            dirnames.clear()  # Don't descend further
            continue

        # Skip hidden dirs and known noise
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in {"node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
        ]

        for fname in filenames:
            stem = Path(fname).stem.lower()
            suffix = Path(fname).suffix.lower()

            # auth-named files in source languages
            if any(stem.startswith(p) or stem == p for p in AUTH_FILE_PREFIXES):
                if suffix in AUTH_FILE_SUFFIXES:
                    rel = _normalise(str(dirpath.relative_to(root)))
                    pattern = f"{rel}/" if rel else ""
                    # Deduplicate: only record the containing directory once
                    candidate = f"{pattern}*"
                    if not any(candidate in p for p in signals.auth_paths):
                        signals.has_auth = True
                        display = f"{pattern}{fname}"
                        if display not in signals.auth_paths:
                            signals.auth_paths.append(display)


# ---------------------------------------------------------------------------
# YAML generation
# ---------------------------------------------------------------------------

_HEADER = """\
# AGENTOWNERS.yml — AI Agent Governance Policy
# Generated by `ctxl init --with-policy` on {timestamp}
#
# Format: https://github.com/cschanhniem/AGENTOWNERS
#
# Decision levels:
#   block            — agents may NOT modify these paths; CI will fail
#   require_approval — human review required before merging
#   allow            — agents may freely modify these paths
#
# To enforce this policy, add the AGENTOWNERS GitHub Action:
#   https://github.com/cschanhniem/AGENTOWNERS#quick-start
"""

_DEFAULTS_SECTION = """\
version: 1

defaults:
  known_agent: require_approval   # Identified AI agents need a human sign-off by default
  unknown_agent: require_approval # Unknown actors treated with same caution
  docs_only: allow                # Pure documentation changes are low-risk
  workflows: block                # CI/CD workflows must not be touched without review
  secrets: block                  # Secret files are always blocked
"""

_RULE_ALLOW_DOCS = """\
  - name: "Allow docs-only changes"
    when:
      docs_only: true
    effect: allow
    reason: "Documentation-only changes are safe for agents."
"""

_RULE_ALLOW_TESTS = """\
  - name: "Allow test changes"
    when:
      files:
{test_globs}
    effect: allow
    reason: "Test-only changes are generally low-risk."
"""

_RULE_BLOCK_WORKFLOWS = """\
  - name: "Block CI/CD workflow edits"
    when:
      files:
{workflow_globs}
    effect: block
    reason: "Agents may not modify CI/CD workflow definitions."
"""

_RULE_BLOCK_SECRETS = """\
  - name: "Block secrets and credentials"
    when:
      files:
{secrets_globs}
    effect: block
    reason: "Secret and credential files must never be modified by agents."
"""

_RULE_BLOCK_INFRA = """\
  - name: "Block infrastructure-as-code edits"
    when:
      files:
{infra_globs}
    effect: block
    reason: "Infrastructure changes carry high blast radius; require human ownership."
"""

_RULE_BLOCK_DEPLOY = """\
  - name: "Block deployment scripts"
    when:
      files:
{deploy_globs}
    effect: block
    reason: "Deployment scripts must be controlled by human engineers."
"""

_RULE_REQUIRE_AUTH = """\
  - name: "Require approval for auth/session changes"
    when:
      files:
{auth_globs}
    effect: require_approval
    reason: "Auth, session, and permission changes require security review."
    notify:
      - "@maintainers"
"""

_RULE_REQUIRE_DEPS = """\
  - name: "Require approval for dependency changes"
    when:
      changes_package_files: true
    effect: require_approval
    reason: "Dependency updates require maintainer review for supply-chain safety."
"""

_FOOTER = """\
# ─────────────────────────────────────────────────────────────────────────────
# Tip: Run `agentowners validate .github/AGENTOWNERS.yml` to check this file.
# Install: npm install -g @agent-owners/cli
# ─────────────────────────────────────────────────────────────────────────────
"""


def _glob_lines(paths: list, suffix: str = "/**") -> str:
    """Format a list of paths as YAML list items under 'files:'."""
    items = []
    for p in paths:
        # If already ends with /, append glob suffix
        if p.endswith("/"):
            items.append(f'        - "{p.rstrip("/")}{suffix}"')
        else:
            # It's a file — use as-is
            items.append(f'        - "{p}"')
    return "\n".join(items) if items else '        - "PLACEHOLDER/**"'


def generate_policy(
    project_root: str,
    output_path: Optional[str] = None,
) -> str:
    """
    Generate a .github/AGENTOWNERS.yml policy file by scanning the repository.

    Args:
        project_root: Path to the project root directory.
        output_path: Custom output path. Defaults to .github/AGENTOWNERS.yml.

    Returns:
        The path to the generated policy file.
    """
    root = Path(project_root).resolve()
    signals = scan_repository(root)

    parts = [
        _HEADER.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")),
        _DEFAULTS_SECTION,
        "rules:",
    ]

    # Always include: allow docs
    parts.append(_RULE_ALLOW_DOCS)

    # Allow tests if detected
    if signals.has_tests:
        test_dirs = [d for d in ["tests/", "test/", "__tests__/", "spec/"] if (root / d.rstrip("/")).exists()]
        if not test_dirs:
            test_dirs = ["tests/"]
        parts.append(_RULE_ALLOW_TESTS.format(
            test_globs=_glob_lines(test_dirs)
        ))

    # Block workflows if detected
    if signals.has_workflows:
        parts.append(_RULE_BLOCK_WORKFLOWS.format(
            workflow_globs=_glob_lines(signals.workflow_paths)
        ))

    # Block secrets if detected
    if signals.has_secrets:
        parts.append(_RULE_BLOCK_SECRETS.format(
            secrets_globs=_glob_lines(signals.secrets_paths)
        ))

    # Block infra if detected
    if signals.has_infra:
        parts.append(_RULE_BLOCK_INFRA.format(
            infra_globs=_glob_lines(signals.infra_paths)
        ))

    # Block deploy scripts if detected
    if signals.has_deploy:
        parts.append(_RULE_BLOCK_DEPLOY.format(
            deploy_globs=_glob_lines(signals.deploy_paths)
        ))

    # Require approval for auth changes if detected
    if signals.has_auth:
        # Deduplicate and limit to most specific paths
        auth_items = _deduplicate_auth_paths(signals.auth_paths)
        parts.append(_RULE_REQUIRE_AUTH.format(
            auth_globs=_glob_lines(auth_items)
        ))

    # Always include: require approval for dependency changes
    parts.append(_RULE_REQUIRE_DEPS)

    parts.append(_FOOTER)

    content = "\n".join(parts)

    # Write output
    if output_path is None:
        out_dir = root / ".github"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "AGENTOWNERS.yml"
    else:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

    out_file.write_text(content, encoding="utf-8")
    return str(out_file)


def _deduplicate_auth_paths(auth_paths: list) -> list:
    """
    Collapse file-level auth paths to directory-level where possible,
    and remove redundant sub-paths (e.g. if 'auth/' already covers 'auth/session.py').
    Returns at most 8 items to keep the YAML readable.
    """
    dirs = set()
    files = []

    for p in auth_paths:
        if p.endswith("/"):
            dirs.add(p)
        else:
            # Check if the parent dir is already captured
            parent = str(Path(p).parent).replace("\\", "/")
            if parent and parent != ".":
                parent_dir = parent + "/"
                # If parent is an auth dir we captured, skip the file
                if parent_dir in dirs or parent_dir.split("/")[0] + "/" in dirs:
                    continue
            files.append(p)

    result = sorted(dirs) + files
    return result[:8]


def summarise_signals(signals: PolicySignals) -> str:
    """Return a human-readable Rich-markup summary of detected signals."""
    lines = []
    if signals.has_workflows:
        lines.append(f"  [green]ok[/green] CI/CD workflows detected -> [bold]block[/bold] ({', '.join(signals.workflow_paths)})")
    if signals.has_secrets:
        lines.append(f"  [green]ok[/green] Secrets directories detected -> [bold]block[/bold] ({', '.join(signals.secrets_paths)})")
    if signals.has_infra:
        lines.append(f"  [green]ok[/green] Infrastructure code detected -> [bold]block[/bold] ({', '.join(signals.infra_paths)})")
    if signals.has_deploy:
        lines.append(f"  [green]ok[/green] Deployment scripts detected -> [bold]block[/bold] ({', '.join(signals.deploy_paths)})")
    if signals.has_auth:
        auth_sample = signals.auth_paths[:3]
        suffix = f" (+{len(signals.auth_paths) - 3} more)" if len(signals.auth_paths) > 3 else ""
        lines.append(f"  [green]ok[/green] Auth/session code detected -> [bold]require_approval[/bold] ({', '.join(auth_sample)}{suffix})")
    if signals.has_tests:
        lines.append("  [green]ok[/green] Test directories detected -> [bold]allow[/bold]")
    if signals.has_docs:
        lines.append("  [green]ok[/green] Docs directories detected -> [bold]allow[/bold]")
    if not lines:
        lines.append("  (no sensitive paths detected — policy uses safe defaults)")
    return "\n".join(lines)
