"""Interactive CLI interface for PS3 Toolbox."""

import asyncio
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from ps3toolbox.covers.sync import sync_covers_command
from ps3toolbox.ps2.decrypt import decrypt_ps2_iso, extract_metadata
from ps3toolbox.ps2.encrypt import encrypt_ps2_iso
from ps3toolbox.utils.disc_detect import detect_disc_number
from ps3toolbox.utils.progress import ConsoleProgress
from ps3toolbox.utils.validation import check_disk_space, validate_input_file, validate_output_path

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """PS3 Toolbox - Tools for PS3 homebrew operations."""
    pass


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path), required=False)
@click.option("--mode", type=click.Choice(["cex", "dex"]), default="cex", help="Console mode (cex=retail, dex=debug)")
@click.option("--content-id", type=str, default=None, help="Content ID (uses placeholder if omitted)")
@click.option("--disc-num", type=click.IntRange(1, 9), default=1, help="Disc number for multi-disc games (1-9)")
@click.option("--overwrite/--no-overwrite", default=False, help="Overwrite existing output file")
@click.option("--remove-source/--keep-source", default=False, help="Remove source ISO after successful encryption")
def encrypt(
    input_path: Path,
    output_path: Path | None,
    mode: str,
    content_id: str | None,
    disc_num: int,
    overwrite: bool,
    remove_source: bool,
) -> None:
    """Encrypt PS2 ISO to .BIN.ENC format."""
    if output_path is None:
        output_path = input_path.with_suffix(".bin.enc")

    try:
        validate_input_file(input_path, [".iso"])
        validate_output_path(output_path, overwrite)
        check_disk_space(output_path, input_path.stat().st_size * 2)

        progress = ConsoleProgress(f"Encrypting {input_path.name}")
        progress.start(input_path.stat().st_size)

        encrypt_ps2_iso(
            input_path,
            output_path,
            mode=mode,
            content_id=content_id,
            disc_num=disc_num,
            progress_callback=progress.update,
        )

        progress.finish()
        console.print(f"[green]✓[/green] Successfully encrypted to {output_path}")

        if remove_source:
            input_path.unlink()
            console.print(f"[yellow]🗑[/yellow] Removed source: {input_path}")

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise click.Abort()


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path))
@click.option("--mode", type=click.Choice(["cex", "dex"]), default="cex", help="Console mode (cex=retail, dex=debug)")
@click.option("--overwrite/--no-overwrite", default=False, help="Overwrite existing output file")
def decrypt(input_path: Path, output_path: Path, mode: str, overwrite: bool) -> None:
    """Decrypt .BIN.ENC to PS2 ISO format."""
    try:
        validate_input_file(input_path, [".enc", ".BIN.ENC"])
        validate_output_path(output_path, overwrite)

        metadata = extract_metadata(input_path)
        check_disk_space(output_path, metadata["iso_size"])

        progress = ConsoleProgress(f"Decrypting {input_path.name}")
        progress.start(metadata["iso_size"])

        decrypt_ps2_iso(input_path, output_path, mode=mode, progress_callback=progress.update)

        progress.finish()
        console.print(f"[green]✓[/green] Successfully decrypted to {output_path}")

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise click.Abort()


def _encrypt_single_iso(args):
    """Worker function for parallel encryption.

    Args:
        args: Tuple of (iso_file, output_file, mode, disc_num_override)

    Returns:
        Tuple of (iso_file, success, error_message, should_remove)
    """
    iso_file, output_file, mode, disc_num_override, remove_source = args

    try:
        if output_file.exists():
            return (iso_file, "skipped", None, False)

        detected_disc = disc_num_override if disc_num_override else detect_disc_number(iso_file.name)

        encrypt_ps2_iso(iso_file, output_file, mode=mode, disc_num=detected_disc, progress_callback=None)

        return (iso_file, "success", detected_disc, remove_source)

    except Exception as e:
        return (iso_file, "error", str(e), False)


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--recursive/--no-recursive", default=True, help="Process subdirectories recursively")
@click.option("--mode", type=click.Choice(["cex", "dex"]), default="cex", help="Console mode (cex=retail, dex=debug)")
@click.option(
    "--disc-num",
    type=click.IntRange(1, 9),
    default=None,
    help="Override disc number for ALL files (default: auto-detect from filename)",
)
@click.option("--overwrite/--no-overwrite", default=False, help="Overwrite existing encrypted files")
@click.option("--remove-source/--keep-source", default=False, help="Remove source ISOs after successful encryption")
@click.option("--pattern", type=str, default="*.iso", help="File pattern to match")
@click.option("--workers", type=int, default=None, help="Number of parallel workers (default: CPU count)")
def batch_encrypt(
    directory: Path,
    recursive: bool,
    mode: str,
    disc_num: int | None,
    overwrite: bool,
    remove_source: bool,
    pattern: str,
    workers: int | None,
) -> None:
    """Batch encrypt PS2 ISOs in directory with parallel processing.

    Automatically detects disc numbers from filenames:
    - "Game (Disc 1).iso" → disc 1
    - "Game [Disc 2].iso" → disc 2
    - "Game - CD3.iso" → disc 3

    Use --disc-num to override auto-detection for all files.
    Use --workers to control parallel processing (default: CPU count).
    """
    glob_pattern = f"**/{pattern}" if recursive else pattern
    iso_files = list(directory.glob(glob_pattern))

    if not iso_files:
        console.print(f"[yellow]No ISO files found matching pattern: {pattern}[/yellow]")
        return

    num_workers = workers or os.cpu_count()
    console.print(f"Found {len(iso_files)} ISO file(s), using {num_workers} workers")

    # Prepare work items
    work_items = []
    skipped_count = 0

    for iso_file in iso_files:
        output_file = iso_file.with_suffix(".bin.enc")

        if output_file.exists() and not overwrite:
            console.print(f"[yellow]⊘[/yellow] Skipping {iso_file.name} (output exists)")
            skipped_count += 1
            continue

        work_items.append((iso_file, output_file, mode, disc_num, remove_source))

    if not work_items:
        console.print(f"[yellow]All files already encrypted (use --overwrite to re-encrypt)[/yellow]")
        return

    console.print(f"Encrypting {len(work_items)} file(s)...\n")

    success_count = 0
    error_count = 0
    removed_count = 0

    # Process in parallel
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task("[cyan]Processing...", total=len(work_items))

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(_encrypt_single_iso, item): item for item in work_items}

            for future in as_completed(futures):
                iso_file, status, result, should_remove = future.result()

                if status == "success":
                    disc_info = f" [disc {result}]" if result > 1 else ""
                    console.print(f"[green]✓[/green] {iso_file.name}{disc_info}")
                    success_count += 1

                    if should_remove:
                        iso_file.unlink()
                        removed_count += 1

                elif status == "error":
                    console.print(f"[red]✗[/red] {iso_file.name}: {result}")
                    error_count += 1

                progress.advance(overall_task)

    console.print(f"\n[bold]Summary:[/bold] {success_count} succeeded, {error_count} failed")
    if skipped_count > 0:
        console.print(f"[yellow]⊘[/yellow] Skipped {skipped_count} file(s)")
    if removed_count > 0:
        console.print(f"[yellow]🗑[/yellow] Removed {removed_count} source file(s)")


@cli.command()
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
def info(file_path: Path) -> None:
    """Show information about encrypted PS2 Classic."""
    try:
        metadata = extract_metadata(file_path)

        table = Table(title=f"PS2 Classic Info: {file_path.name}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Magic", metadata["magic"])
        table.add_row("Version", f"{metadata['version_major']}.{metadata['version_minor']}")
        table.add_row("Content ID", metadata["content_id"])
        table.add_row("Segment Size", f"0x{metadata['segment_size']:X}")
        table.add_row("ISO Size", f"{metadata['iso_size']:,} bytes")
        table.add_row("ISO Size (MB)", f"{metadata['iso_size'] / 1024 / 1024:.2f} MB")

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise click.Abort()


@cli.group()
def covers() -> None:
    """Cover art management for webMAN-MOD."""
    pass


@covers.command()
@click.argument("path", type=str)
@click.option(
    "--database",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to ROM database directory (myrient TSV files)",
)
@click.option("--dry-run", is_flag=True, default=False, help="Preview actions without making changes")
@click.option("--organize/--no-organize", default=True, help="Organize PS1/PS2 games into folders")
@click.option("--skip-existing/--force-all", default=True, help="Skip games that already have covers")
@click.option(
    "--platform",
    type=click.Choice(["PS1", "PS2", "ROMS"], case_sensitive=False),
    default=None,
    help="Filter by platform (PS1, PS2, or ROMS)",
)
@click.option("--full-output", is_flag=True, default=False, help="Show all games in dry-run (not just first 50)")
@click.option("--limit", type=int, default=None, help="Limit to first N games (useful for testing)")
def sync(
    path: str,
    database: Path | None,
    dry_run: bool,
    organize: bool,
    skip_existing: bool,
    platform: str | None,
    full_output: bool,
    limit: int | None,
) -> None:
    """
    Sync cover art for PS1/PS2/ROM games.

    PATH can be a local directory or FTP URL:
      /path/to/games
      ftp://user:pass@192.168.0.16/dev_hdd0

    Expected structure:
      PATH/PSXISO/  - PS1 games
      PATH/PS2ISO/  - PS2 games
      PATH/ROMS/    - Retro ROMs (organized by emulator)
    """

    try:
        asyncio.run(
            sync_covers_command(
                path=path,
                database_path=database,
                dry_run=dry_run,
                organize=organize,
                skip_existing=skip_existing,
                platform_filter=platform.upper() if platform else None,
                full_output=full_output,
                limit=limit,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
    except Exception as e:
        import traceback
        console.print(f"[red]✗[/red] Error: {e}")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise click.Abort()


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, default=False, help="Preview actions without making changes")
@click.option("--any-image", is_flag=True, default=False, help="Use any image found in folder (skip heuristics)")
def organize(path: Path, dry_run: bool, any_image: bool) -> None:
    """
    Organize PS1/PS2 games into folders with covers.

    Recursively scans PATH for game files (.bin, .cue, .iso) and organizes
    them into individual game folders. Automatically finds and copies cover
    images using intelligent heuristics.

    Similar to fix_psx_covers.py but with folder organization.

    Examples:
      # Preview organization (safe, no changes)
      ps3toolbox organize /path/to/PSXISO --dry-run

      # Actually organize games
      ps3toolbox organize /path/to/PSXISO

      # Use any image found (skip smart matching)
      ps3toolbox organize /path/to/PSXISO --any-image
    """
    from ps3toolbox.games.organize_cli import organize_games_command

    try:
        asyncio.run(
            organize_games_command(
                path=str(path),
                dry_run=dry_run,
                any_image=any_image,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise click.Abort()


if __name__ == "__main__":
    cli()
