"""Cover sync orchestrator - main entry point for cover operations."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from rich.console import Console
from rich.table import Table

from ps3toolbox.games import GameFile
from ps3toolbox.games import GameOrganizer
from ps3toolbox.games import GameScanner
from ps3toolbox.games import OrganizeAction
from ps3toolbox.games import RomDatabase
from ps3toolbox.games import SerialResolver
from ps3toolbox.utils.fs import FilesystemProvider
from ps3toolbox.utils.fs import FTPFilesystem
from ps3toolbox.utils.fs import create_filesystem

from .downloader import CoverDownloader


@dataclass
class SyncStats:
    """Statistics for cover sync operation."""

    scanned: int = 0
    already_has_cover: int = 0
    downloaded: int = 0
    failed: int = 0
    organized: int = 0
    skipped: int = 0


@dataclass
class SyncAction:
    """Represents a sync action to be performed."""

    game: GameFile
    action_type: str
    details: str
    cover_data: bytes | None = None
    cover_source: str | None = None
    organize_actions: list[OrganizeAction] = None


class CoverSync:
    """Orchestrate cover sync operations."""

    def __init__(
        self,
        fs: FilesystemProvider,
        resolver: SerialResolver,
        downloader: CoverDownloader,
        organizer: GameOrganizer,
        console: Console,
        dry_run: bool = False,
        full_output: bool = False,
    ):
        self.fs = fs
        self.resolver = resolver
        self.downloader = downloader
        self.organizer = organizer
        self.console = console
        self.dry_run = dry_run
        self.full_output = full_output
        self.scanner = GameScanner(fs)

    async def sync_covers(
        self,
        root_path: str,
        organize: bool = True,
        skip_existing: bool = True,
        platform_filter: str | None = None,
        limit: int | None = None,
    ) -> SyncStats:
        """
        Sync covers for all games in directory structure.

        Args:
            root_path: Root path with PS3 structure (PSXISO, PS2ISO, ROMS)
            organize: Whether to organize games into folders
            skip_existing: Skip games that already have covers
            platform_filter: Filter to specific platform (PS1, PS2, or ROMS)
            limit: Limit to first N games (for testing)

        Returns:
            Statistics for the operation
        """
        stats = SyncStats()
        actions: list[SyncAction] = []

        # Phase 1: Scan for games
        filter_msg = f" ({platform_filter} only)" if platform_filter else ""
        limit_msg = f" (limit: {limit})" if limit else ""
        self.console.print(f"\n[cyan]Scanning {root_path}{filter_msg}{limit_msg}...[/cyan]")

        # Collect all games first
        games_to_process = []
        async for game in self.scanner.scan_root(root_path):
            # Filter by platform if specified
            if platform_filter:
                # Map platform names
                if platform_filter == "PS1" and game.platform != "PSX":
                    continue
                elif platform_filter == "PS2" and game.platform != "PS2":
                    continue
                elif platform_filter == "ROMS" and game.platform in ("PSX", "PS2"):
                    continue

            stats.scanned += 1

            if game.has_cover and skip_existing:
                stats.already_has_cover += 1
                continue

            games_to_process.append(game)

            # Apply limit if specified
            if limit and len(games_to_process) >= limit:
                break

        # Resolve serials in parallel
        self.console.print(f"[dim]Resolving serials for {len(games_to_process)} games...[/dim]")
        serial_tasks = [self.resolver.resolve(game.name, game.platform, use_fuzzy=True) for game in games_to_process]
        serial_results = await asyncio.gather(*serial_tasks, return_exceptions=True)

        # In dry-run mode, search for covers in parallel
        cover_results = []
        if self.dry_run and games_to_process:
            self.console.print("[dim]Searching for covers (this may take a minute)...[/dim]")
            cover_tasks = []
            for game, serial_result in zip(games_to_process, serial_results, strict=False):
                if isinstance(serial_result, Exception):
                    serial = None
                else:
                    serial_tuple = cast(tuple[str, str] | None, serial_result)
                    serial = serial_tuple[0] if serial_tuple else None
                cover_tasks.append(self.downloader.download_cover(game.platform, serial, game.name))
            cover_results = await asyncio.gather(*cover_tasks, return_exceptions=True)

        # Build actions
        for i, game in enumerate(games_to_process):
            serial_result = serial_results[i]
            if isinstance(serial_result, Exception):
                serial = None
                method = "error"
            else:
                serial_tuple = cast(tuple[str, str] | None, serial_result)
                serial = serial_tuple[0] if serial_tuple else None
                method = serial_tuple[1] if serial_tuple else "none"

            # Get cover info
            cover_source = None
            cover_url = None
            if self.dry_run and cover_results:
                cover_result = cover_results[i]
                if not isinstance(cover_result, Exception) and cover_result:
                    cover_tuple = cast(tuple[bytes, str, str], cover_result)
                    cover_source = cover_tuple[1]  # Source name
                    cover_url = cover_tuple[2]  # URL

            # Plan action
            action = SyncAction(
                game=game,
                action_type="download" if not game.has_cover else "skip",
                details=f"Serial: {serial or 'NOT FOUND'} (method: {method})"
                + (f"\n  URL: {cover_url}" if cover_url else ""),
                cover_source=cover_url if cover_url else cover_source,
            )

            actions.append(action)

        # Phase 2: Show plan and confirm
        if self.dry_run:
            self._display_plan(actions, stats)
            return stats

        # Phase 3: Download covers in parallel
        if not actions:
            return stats

        self.console.print(f"\n[cyan]Downloading covers for {len(actions)} games...[/cyan]")

        download_tasks = []
        for action in actions:
            if action.action_type == "download":
                serial_result = await self.resolver.resolve(
                    action.game.name,
                    action.game.platform,
                    use_fuzzy=True,
                )
                serial = serial_result[0] if serial_result else None

                download_tasks.append(
                    (
                        action,
                        action.game.platform,
                        serial,
                        action.game.name,
                    )
                )

        # Download in batches
        batch_size = 10
        for i in range(0, len(download_tasks), batch_size):
            batch = download_tasks[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(download_tasks) + batch_size - 1) // batch_size

            self.console.print(f"[dim]  Batch {batch_num}/{total_batches}: downloading {len(batch)} covers...[/dim]")

            try:
                results = await self.downloader.download_batch(
                    [(platform, serial, name) for _, platform, serial, name in batch]
                )

                for (action, _, _, _), result in zip(batch, results, strict=False):
                    if result:
                        download_result = cast(tuple[bytes, str, str], result)
                        action.cover_data = download_result[0]  # bytes
                        action.cover_source = download_result[2]  # URL
                        stats.downloaded += 1
                        self.console.print(f"[dim]    ✓ {action.game.name}[/dim]")
                    else:
                        stats.failed += 1
                        self.console.print(f"[dim]    ✗ {action.game.name}[/dim]")
            except Exception as e:
                self.console.print(f"[red]  Batch {batch_num} failed: {e}[/red]")
                for _action, _, _, _ in batch:
                    stats.failed += 1

        # Phase 4: Organize and save covers
        if organize:
            self.console.print("\n[cyan]Organizing games...[/cyan]")

            for action in actions:
                if action.game.platform in ("PSX", "PS2"):
                    # Organize files into folders
                    if action.game.platform == "PSX":
                        org_actions = await self.organizer.organize_ps1_game(
                            [action.game.path],
                            action.game.name,
                            action.game.folder,
                        )
                    else:
                        org_actions = await self.organizer.organize_ps2_game(
                            action.game.path,
                            action.game.name,
                            action.game.folder,
                        )

                    if org_actions:
                        action.organize_actions = org_actions
                        stats.organized += 1

        # Phase 5: Save covers
        covers_to_save = [a for a in actions if a.cover_data]
        if covers_to_save:
            self.console.print(f"\n[cyan]Saving {len(covers_to_save)} covers...[/cyan]")

            saved = 0
            failed = 0
            for action in covers_to_save:
                try:
                    # Determine target path
                    target_folder = action.game.folder

                    # If organized, use new folder location
                    if action.organize_actions:
                        for org_action in action.organize_actions:
                            if org_action.action_type == "mkdir":
                                target_folder = org_action.dst
                                break

                    cover_filename = f"{action.game.name}.PNG"
                    cover_path = self.fs.join_path(target_folder, cover_filename)

                    # Save cover
                    self.console.print(f"[dim]  Attempting: {cover_path}[/dim]")
                    await self.fs.write_bytes(cover_path, action.cover_data)
                    saved += 1
                    self.console.print(f"[dim]  ✓ Saved {cover_filename}[/dim]")
                except Exception as e:
                    failed += 1
                    self.console.print(f"[red]  ✗ Failed to save {action.game.name}[/red]")
                    self.console.print(f"[red]     Path: {cover_path}[/red]")
                    self.console.print(f"[red]     Error: {e}[/red]")

            self.console.print(f"[green]Saved {saved} covers ({failed} failed)[/green]")

        # Final summary
        self._display_summary(stats)

        return stats

    def _display_plan(self, actions: list[SyncAction], stats: SyncStats):
        """Display dry-run plan in a formatted table."""
        table = Table(title="Cover Sync Plan (DRY RUN)", expand=True)
        table.add_column("Game", style="cyan", no_wrap=False, max_width=30)
        table.add_column("Platform", style="magenta", max_width=10)
        table.add_column("Action", style="yellow", max_width=10)
        table.add_column("Details", style="green", no_wrap=False)

        # Show all games if full_output is enabled, otherwise limit to 50
        display_limit = len(actions) if self.full_output else 50

        for action in actions[:display_limit]:
            table.add_row(
                action.game.name,
                action.game.platform,
                action.action_type,
                action.details,
            )

        if len(actions) > display_limit:
            table.add_row("...", "...", "...", f"+ {len(actions) - display_limit} more games")

        self.console.print(table)

        # Show URLs for found covers
        found_covers = [a for a in actions[:display_limit] if a.cover_source]
        if self.dry_run and found_covers:
            self.console.print(f"\n[green]✓ Found {len(found_covers)}/{len(actions)} covers[/green]")
            if len(found_covers) <= 20:  # Only show URLs for first 20
                self.console.print("\n[cyan]Cover URLs:[/cyan]")
                for action in found_covers:
                    self.console.print(f"  [dim]{action.game.name}:[/dim]")
                    self.console.print(f"    {action.cover_source}")
        elif self.dry_run and actions:
            self.console.print(f"\n[yellow]⚠ No covers found (0/{len(actions)})[/yellow]")

    def _display_summary(self, stats: SyncStats):
        """Display operation summary."""
        table = Table(title="Cover Sync Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        table.add_row("Games scanned", str(stats.scanned))
        table.add_row("Already have covers", str(stats.already_has_cover))
        table.add_row("Covers downloaded", str(stats.downloaded))
        table.add_row("Download failed", str(stats.failed))
        table.add_row("Games organized", str(stats.organized))

        self.console.print("\n")
        self.console.print(table)


async def sync_covers_command(
    path: str,
    database_path: Path | None,
    dry_run: bool,
    organize: bool,
    skip_existing: bool,
    platform_filter: str | None = None,
    full_output: bool = False,
    limit: int | None = None,
):
    """Main entry point for cover sync command."""
    console = Console()

    # Create filesystem provider
    fs = create_filesystem(path, dry_run=dry_run)

    # Load databases if provided
    resolver = SerialResolver()
    if database_path and database_path.exists():
        console.print(f"[cyan]Loading ROM databases from {database_path}...[/cyan]")

        for platform in ["PSX", "PS2"]:
            db_file = database_path / f"romi_{platform}.tsv"
            if db_file.exists():
                db = RomDatabase()
                db.load_from_tsv(db_file)
                resolver.add_database(platform, db)
                console.print(f"  Loaded {len(db.entries)} entries for {platform}")

    # Create components
    organizer = GameOrganizer(fs, dry_run=dry_run)

    async with CoverDownloader(max_concurrent=10) as downloader:
        # Connect to FTP if needed
        if isinstance(fs, FTPFilesystem):
            await fs.connect()

        try:
            sync = CoverSync(
                fs=fs,
                resolver=resolver,
                downloader=downloader,
                organizer=organizer,
                console=console,
                dry_run=dry_run,
                full_output=full_output,
            )

            await sync.sync_covers(
                root_path=path,
                organize=organize,
                skip_existing=skip_existing,
                platform_filter=platform_filter,
                limit=limit,
            )

        finally:
            if isinstance(fs, FTPFilesystem):
                await fs.disconnect()
