import shutil
from pathlib import Path

import click


@click.command("install-skill")
@click.option(
    "--path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Path to project directory. Defaults to current directory.",
)
def install_skill(path: Path | None):
    """Install the codeyak Claude Code skill into a project."""
    project_dir = path or Path.cwd()
    target_dir = project_dir / ".claude" / "skills" / "codeyak"

    # Find the bundled skill template
    skill_source = Path(__file__).resolve().parent.parent.parent.parent / "prebuilt" / "skill"
    if not skill_source.exists():
        click.echo("Error: Could not find bundled skill template.", err=True)
        raise SystemExit(1)

    if target_dir.exists():
        click.echo(f"Skill already exists at {target_dir}")
        if not click.confirm("Overwrite?"):
            click.echo("Aborted.")
            return

        # Remove existing skill files but preserve data/
        data_dir = target_dir / "data"
        has_data = data_dir.exists()

        # Temporarily move data dir if it exists
        tmp_data = None
        if has_data:
            tmp_data = target_dir.parent / "_codeyak_data_backup"
            shutil.move(str(data_dir), str(tmp_data))

        shutil.rmtree(target_dir)

        # Copy fresh skill
        shutil.copytree(str(skill_source), str(target_dir))

        # Restore data
        if tmp_data and tmp_data.exists():
            # Remove the empty data dir from the fresh copy if present
            fresh_data = target_dir / "data"
            if fresh_data.exists():
                shutil.rmtree(fresh_data)
            shutil.move(str(tmp_data), str(data_dir))
    else:
        # Fresh install
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(skill_source), str(target_dir))

    # Ensure data directory exists
    data_dir = target_dir / "data"
    data_dir.mkdir(exist_ok=True)
    gitkeep = data_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

    click.echo(f"Codeyak skill installed to {target_dir}")
    click.echo()
    click.echo("Usage in Claude Code:")
    click.echo("  /codeyak              - Review local changes")
    click.echo("  /codeyak --trends     - View violation trends")
    click.echo("  /codeyak --exclude 'tests/'  - Exclude patterns")
    click.echo()
    click.echo("Tip: Add .claude/skills/codeyak/data/ to .gitignore for personal stats,")
    click.echo("or commit it for shared team stats.")
