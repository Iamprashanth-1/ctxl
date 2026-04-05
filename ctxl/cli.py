"""
ctxl — Context Engineering CLI for AI agents.

Commands:
    ctxl map     — Generate a compressed codebase skeleton (zero AI, pure parsing)
    ctxl init    — Generate .github/copilot-instructions.md for focused AI context
    ctxl checkpoint — Save/view session state for safe /clear workflows
"""

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich import print as rprint

from ctxl import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="ctxl")
def main():
    """ctxl — Context Engineering CLI for AI agents.

    Reduce token waste and prevent hallucination by giving AI agents
    precisely the context they need. Zero AI models used — pure parsing.
    """
    pass


# ─── ctxl map ──────────────────────────────────────────────────────────────────

@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("-o", "--output", default=None, help="Write output to a file instead of stdout.")
@click.option("-e", "--ext", multiple=True, help="Filter by file extension (e.g., -e .py -e .js). Defaults to all supported.")
@click.option("--clipboard", is_flag=True, help="Copy the output to clipboard.")
def map(path, output, ext, clipboard):
    """Generate a compressed codebase skeleton.

    Parses source files using Tree-sitter and extracts only structural
    information — function signatures, class definitions, and imports.
    No AI models, no API calls, no tokens burned.

    \b
    Examples:
        ctxl map                    # Map current directory
        ctxl map ./src              # Map a specific directory
        ctxl map -e .py -e .java   # Only Python and Java files
        ctxl map -o codebase.md    # Save to file
        ctxl map --clipboard       # Copy to clipboard for pasting into AI chat
    """
    from ctxl.mapper import map_directory, map_file, format_map_output
    from pathlib import Path as P

    target = P(path).resolve()

    with console.status("[bold cyan]Parsing codebase with Tree-sitter...", spinner="dots"):
        if target.is_file():
            skeleton = map_file(str(target))
            if skeleton is None:
                console.print(f"[red]✗[/red] Unsupported file type: {target.suffix}")
                raise SystemExit(1)
            result = f"## {target.name}\n```\n{skeleton}\n```"
            file_count = 1
        else:
            extensions = list(ext) if ext else None
            skeletons = map_directory(str(target), extensions)
            if not skeletons:
                console.print("[yellow]⚠[/yellow] No supported source files found.")
                raise SystemExit(0)
            result = format_map_output(skeletons)
            file_count = len(skeletons)

    if output:
        out_path = P(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")
        console.print(f"[green]✓[/green] Codebase map written to [bold]{output}[/bold] ({file_count} files)")
    elif clipboard:
        try:
            import pyperclip
            pyperclip.copy(result)
            console.print(f"[green]✓[/green] Codebase map copied to clipboard ({file_count} files)")
        except ImportError:
            console.print("[yellow]⚠[/yellow] Install `pyperclip` for clipboard support. Printing to stdout instead.\n")
            console.print(result)
    else:
        console.print(result)

    # Show token savings estimate
    _show_savings(path, result, file_count)


def _show_savings(path: str, result: str, file_count: int):
    """Show estimated token savings."""
    from pathlib import Path as P
    import os

    target = P(path).resolve()
    raw_chars = 0

    if target.is_file():
        try:
            raw_chars = target.stat().st_size
        except OSError:
            pass
    else:
        from ctxl.mapper import LANGUAGE_MAP, IGNORE_PATTERNS, IGNORE_EXTENSIONS
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_PATTERNS and not d.startswith(".")]
            for fname in filenames:
                fpath = P(dirpath) / fname
                if fpath.suffix.lower() in LANGUAGE_MAP and fpath.suffix.lower() not in IGNORE_EXTENSIONS:
                    try:
                        raw_chars += fpath.stat().st_size
                    except OSError:
                        pass

    if raw_chars > 0:
        compressed_chars = len(result)
        # Rough token estimate: ~4 chars per token
        raw_tokens = raw_chars // 4
        compressed_tokens = compressed_chars // 4
        ratio = round((1 - compressed_tokens / raw_tokens) * 100) if raw_tokens > 0 else 0
        console.print(
            Panel(
                f"[dim]Raw source:[/dim] ~{raw_tokens:,} tokens\n"
                f"[dim]Skeleton:[/dim]   ~{compressed_tokens:,} tokens\n"
                f"[bold green]Savings:[/bold green]    ~{ratio}% token reduction",
                title="[bold]Token Savings Estimate[/bold]",
                border_style="green",
                width=45,
            )
        )


# ─── ctxl init ─────────────────────────────────────────────────────────────────

@main.command()
@click.argument("task", type=str)
@click.option("-d", "--directory", default=".", type=click.Path(exists=True), help="Project root directory.")
@click.option("-f", "--focus", multiple=True, help="Files to focus on (can specify multiple: -f file1.py -f file2.py).")
@click.option("--no-map", is_flag=True, help="Skip codebase map generation.")
@click.option("-o", "--output", default=None, help="Custom output path (default: .github/copilot-instructions.md).")
def init(task, directory, focus, no_map, output):
    """Generate a task-focused .github/copilot-instructions.md

    GitHub Copilot natively reads this file for workspace-level instructions.
    This command generates an optimized version tailored to your current task,
    optionally embedding the codebase skeleton so Copilot understands your
    project structure without reading every file.

    \b
    Examples:
        ctxl init "Fix the data pipeline ETL bug"
        ctxl init "Add user authentication" -f auth.py -f models.py
        ctxl init "Refactor tests" --no-map
    """
    from ctxl.init import generate_instructions

    focus_files = list(focus) if focus else None

    with console.status("[bold cyan]Generating Copilot instructions...", spinner="dots"):
        result_path = generate_instructions(
            project_root=directory,
            task=task,
            focus_files=focus_files,
            include_map=not no_map,
            output_path=output,
        )

    console.print(f"[green]✓[/green] Instructions written to [bold]{result_path}[/bold]")
    console.print("[dim]Copilot will automatically read this file for context.[/dim]")


# ─── ctxl checkpoint ───────────────────────────────────────────────────────────

@main.group(name="checkpoint")
def checkpoint_group():
    """Save and restore session state for safe /clear workflows."""
    pass


@checkpoint_group.command(name="save")
@click.option("-d", "--directory", default=".", type=click.Path(exists=True), help="Project root directory.")
@click.option("-t", "--task", required=True, help="High-level task description.")
@click.option("--done", multiple=True, help="Completed step (can specify multiple).")
@click.option("--state", required=True, help="Brief description of current state.")
@click.option("--next", "next_steps", multiple=True, help="Planned next step (can specify multiple).")
@click.option("--file", "files", multiple=True, help="File that was modified.")
@click.option("--learned", multiple=True, help="Key discovery or insight.")
@click.option("--error", "errors", multiple=True, help="Error that was resolved.")
def checkpoint_save(directory, task, done, state, next_steps, files, learned, errors):
    """Save a session checkpoint.

    Captures what you've done, what you know, and what's next — in a compressed
    format. After saving, you can safely run /clear in Copilot Chat and paste
    the checkpoint content to restore context.

    \b
    Example:
        ctxl checkpoint save \\
            -t "Fix ETL pipeline" \\
            --done "Found the bug in clean_data()" \\
            --done "Updated the schema validation" \\
            --state "Pipeline runs but output has wrong column order" \\
            --next "Fix column ordering in transform()" \\
            --file "data_pipeline.py" \\
            --learned "The users table has columns: id, name, email, created_at"
    """
    from ctxl.checkpoint import create_checkpoint

    result_path = create_checkpoint(
        project_root=directory,
        task=task,
        completed_steps=list(done),
        current_state=state,
        next_steps=list(next_steps),
        files_modified=list(files) if files else None,
        key_discoveries=list(learned) if learned else None,
        errors_resolved=list(errors) if errors else None,
    )

    console.print(f"[green]✓[/green] Checkpoint saved to [bold]{result_path}[/bold]")
    console.print("[dim]You can now safely run /clear in Copilot Chat.[/dim]")
    console.print("[dim]Paste the checkpoint content into your next message to restore context.[/dim]")


@checkpoint_group.command(name="list")
@click.option("-d", "--directory", default=".", type=click.Path(exists=True), help="Project root directory.")
def checkpoint_list(directory):
    """List all saved checkpoints."""
    from ctxl.checkpoint import list_checkpoints
    from rich.table import Table

    checkpoints = list_checkpoints(directory)

    if not checkpoints:
        console.print("[yellow]⚠[/yellow] No checkpoints found.")
        return

    table = Table(title="Session Checkpoints", border_style="cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Created", style="green")
    table.add_column("Filename")
    table.add_column("Size", justify="right")

    for i, cp in enumerate(checkpoints, 1):
        size_str = f"{cp['size_bytes']:,} B"
        table.add_row(str(i), cp["created"], cp["filename"], size_str)

    console.print(table)


@checkpoint_group.command(name="show")
@click.option("-d", "--directory", default=".", type=click.Path(exists=True), help="Project root directory.")
def checkpoint_show(directory):
    """Show the latest checkpoint content."""
    from ctxl.checkpoint import get_latest_checkpoint

    content = get_latest_checkpoint(directory)
    if content is None:
        console.print("[yellow]⚠[/yellow] No checkpoints found. Run `ctxl checkpoint save` first.")
        return

    console.print(Panel(content, title="[bold]Latest Checkpoint[/bold]", border_style="cyan"))


if __name__ == "__main__":
    main()
