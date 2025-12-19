"""Interactive CLI interface for PS3 Toolbox."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from ps3toolbox.ps2.encrypt import encrypt_ps2_iso
from ps3toolbox.ps2.decrypt import decrypt_ps2_iso, extract_metadata
from ps3toolbox.utils.progress import ConsoleProgress
from ps3toolbox.utils.validation import validate_input_file, validate_output_path, check_disk_space

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """PS3 Toolbox - Tools for PS3 homebrew operations."""
    pass


@cli.command()
@click.argument('input_path', type=click.Path(exists=True, path_type=Path))
@click.argument('output_path', type=click.Path(path_type=Path))
@click.option('--mode', type=click.Choice(['cex', 'dex']), default='cex',
              help='Console mode (cex=retail, dex=debug)')
@click.option('--content-id', type=str, default=None,
              help='Content ID (uses placeholder if omitted)')
@click.option('--overwrite/--no-overwrite', default=False,
              help='Overwrite existing output file')
@click.option('--remove-source/--keep-source', default=False,
              help='Remove source ISO after successful encryption')
def encrypt(
    input_path: Path,
    output_path: Path,
    mode: str,
    content_id: str | None,
    overwrite: bool,
    remove_source: bool
) -> None:
    """Encrypt PS2 ISO to .BIN.ENC format."""
    try:
        validate_input_file(input_path, ['.iso'])
        validate_output_path(output_path, overwrite)
        check_disk_space(output_path, input_path.stat().st_size * 2)

        progress = ConsoleProgress(f"Encrypting {input_path.name}")
        progress.start(input_path.stat().st_size)

        encrypt_ps2_iso(
            input_path,
            output_path,
            mode=mode,
            content_id=content_id,
            progress_callback=progress.update
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
@click.argument('input_path', type=click.Path(exists=True, path_type=Path))
@click.argument('output_path', type=click.Path(path_type=Path))
@click.option('--mode', type=click.Choice(['cex', 'dex']), default='cex',
              help='Console mode (cex=retail, dex=debug)')
@click.option('--overwrite/--no-overwrite', default=False,
              help='Overwrite existing output file')
def decrypt(
    input_path: Path,
    output_path: Path,
    mode: str,
    overwrite: bool
) -> None:
    """Decrypt .BIN.ENC to PS2 ISO format."""
    try:
        validate_input_file(input_path, ['.enc', '.BIN.ENC'])
        validate_output_path(output_path, overwrite)

        metadata = extract_metadata(input_path)
        check_disk_space(output_path, metadata['iso_size'])

        progress = ConsoleProgress(f"Decrypting {input_path.name}")
        progress.start(metadata['iso_size'])

        decrypt_ps2_iso(
            input_path,
            output_path,
            mode=mode,
            progress_callback=progress.update
        )

        progress.finish()
        console.print(f"[green]✓[/green] Successfully decrypted to {output_path}")

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise click.Abort()


@cli.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--recursive/--no-recursive', default=True,
              help='Process subdirectories recursively')
@click.option('--mode', type=click.Choice(['cex', 'dex']), default='cex',
              help='Console mode (cex=retail, dex=debug)')
@click.option('--overwrite/--no-overwrite', default=False,
              help='Overwrite existing encrypted files')
@click.option('--remove-source/--keep-source', default=False,
              help='Remove source ISOs after successful encryption')
@click.option('--pattern', type=str, default='*.iso',
              help='File pattern to match')
def batch_encrypt(
    directory: Path,
    recursive: bool,
    mode: str,
    overwrite: bool,
    remove_source: bool,
    pattern: str
) -> None:
    """Batch encrypt PS2 ISOs in directory."""
    glob_pattern = f"**/{pattern}" if recursive else pattern
    iso_files = list(directory.glob(glob_pattern))

    if not iso_files:
        console.print(f"[yellow]No ISO files found matching pattern: {pattern}[/yellow]")
        return

    console.print(f"Found {len(iso_files)} ISO file(s)")

    success_count = 0
    error_count = 0
    removed_count = 0

    for iso_file in iso_files:
        output_file = iso_file.with_suffix('.bin.enc')

        try:
            if output_file.exists() and not overwrite:
                console.print(f"[yellow]⊘[/yellow] Skipping {iso_file.name} (output exists)")
                continue

            progress = ConsoleProgress(f"Encrypting {iso_file.name}")
            progress.start(iso_file.stat().st_size)

            encrypt_ps2_iso(
                iso_file,
                output_file,
                mode=mode,
                progress_callback=progress.update
            )

            progress.finish()
            console.print(f"[green]✓[/green] {iso_file.name}")
            success_count += 1

            if remove_source:
                iso_file.unlink()
                removed_count += 1

        except Exception as e:
            console.print(f"[red]✗[/red] {iso_file.name}: {e}")
            error_count += 1

    console.print(f"\n[bold]Summary:[/bold] {success_count} succeeded, {error_count} failed")
    if removed_count > 0:
        console.print(f"[yellow]🗑[/yellow] Removed {removed_count} source file(s)")


@cli.command()
@click.argument('file_path', type=click.Path(exists=True, path_type=Path))
def info(file_path: Path) -> None:
    """Show information about encrypted PS2 Classic."""
    try:
        metadata = extract_metadata(file_path)

        table = Table(title=f"PS2 Classic Info: {file_path.name}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Magic", metadata['magic'])
        table.add_row("Version", f"{metadata['version_major']}.{metadata['version_minor']}")
        table.add_row("Content ID", metadata['content_id'])
        table.add_row("Segment Size", f"0x{metadata['segment_size']:X}")
        table.add_row("ISO Size", f"{metadata['iso_size']:,} bytes")
        table.add_row("ISO Size (MB)", f"{metadata['iso_size'] / 1024 / 1024:.2f} MB")

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        raise click.Abort()


if __name__ == '__main__':
    cli()
