"""Cover sync orchestrator - main entry point for cover operations."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, TaskID
from rich.table import Table

from .downloader import CoverDownloader
from ps3toolbox.utils.fs import FilesystemProvider, FTPFilesystem, create_filesystem
from ps3toolbox.games import GameOrganizer, OrganizeAction, GameScanner, GameFile, RomDatabase, SerialResolver


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
    cover_data: Optional[bytes] = None
    cover_source: Optional[str] = None
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
    ):
        self.fs = fs
        self.resolver = resolver
        self.downloader = downloader
        self.organizer = organizer
        self.console = console
        self.dry_run = dry_run
        self.scanner = GameScanner(fs)

    async def sync_covers(
        self,
        root_path: str,
        organize: bool = True,
        skip_existing: bool = True,
    ) -> SyncStats:
        """
        Sync covers for all games in directory structure.

        Args:
            root_path: Root path with PS3 structure (PSXISO, PS2ISO, ROMS)
            organize: Whether to organize games into folders
            skip_existing: Skip games that already have covers

        Returns:
            Statistics for the operation
        """
        stats = SyncStats()
        actions: list[SyncAction] = []

        # Phase 1: Scan for games
        self.console.print(f"\n[cyan]Scanning {root_path}...[/cyan]")

        async for game in self.scanner.scan_root(root_path):
            stats.scanned += 1

            if game.has_cover and skip_existing:
                stats.already_has_cover += 1
                continue

            # Resolve serial
            serial_result = await self.resolver.resolve(
                game.name,
                game.platform,
                use_fuzzy=True,
            )

            serial = serial_result[0] if serial_result else None
            method = serial_result[1] if serial_result else 'none'

            # Plan action
            action = SyncAction(
                game=game,
                action_type='download' if not game.has_cover else 'skip',
                details=f"Serial: {serial or 'NOT FOUND'} (method: {method})",
            )

            actions.append(action)

        # Phase 2: Show plan and confirm
        if self.dry_run:
            self._display_plan(actions, stats)
            return stats

        # Phase 3: Download covers in parallel
        self.console.print(f"\n[cyan]Downloading covers...[/cyan]")

        download_tasks = []
        for action in actions:
            if action.action_type == 'download':
                serial_result = await self.resolver.resolve(
                    action.game.name,
                    action.game.platform,
                    use_fuzzy=True,
                )
                serial = serial_result[0] if serial_result else None

                download_tasks.append((
                    action,
                    action.game.platform,
                    serial,
                    action.game.name,
                ))

        # Download in batches
        batch_size = 10
        for i in range(0, len(download_tasks), batch_size):
            batch = download_tasks[i:i + batch_size]

            results = await self.downloader.download_batch([
                (platform, serial, name)
                for _, platform, serial, name in batch
            ])

            for (action, _, _, _), result in zip(batch, results):
                if result:
                    action.cover_data, action.cover_source = result
                    stats.downloaded += 1
                else:
                    stats.failed += 1

        # Phase 4: Organize and save covers
        if organize:
            self.console.print(f"\n[cyan]Organizing games...[/cyan]")

            for action in actions:
                if action.game.platform in ('PSX', 'PS2'):
                    # Organize files into folders
                    if action.game.platform == 'PSX':
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
        self.console.print(f"\n[cyan]Saving covers...[/cyan]")

        for action in actions:
            if action.cover_data:
                # Determine target path
                target_folder = action.game.folder

                # If organized, use new folder location
                if action.organize_actions:
                    for org_action in action.organize_actions:
                        if org_action.action_type == 'mkdir':
                            target_folder = org_action.dst
                            break

                cover_filename = f"{action.game.name}.PNG"
                cover_path = self.fs.join_path(target_folder, cover_filename)

                # Save cover
                await self.fs.write_bytes(cover_path, action.cover_data)

        # Final summary
        self._display_summary(stats)

        return stats

    def _display_plan(self, actions: list[SyncAction], stats: SyncStats):
        """Display dry-run plan in a formatted table."""
        table = Table(title="Cover Sync Plan (DRY RUN)")
        table.add_column("Game", style="cyan")
        table.add_column("Platform", style="magenta")
        table.add_column("Action", style="yellow")
        table.add_column("Details", style="green")

        for action in actions[:50]:  # Limit display to first 50
            table.add_row(
                action.game.name,
                action.game.platform,
                action.action_type,
                action.details,
            )

        if len(actions) > 50:
            table.add_row("...", "...", "...", f"+ {len(actions) - 50} more games")

        self.console.print(table)

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
    database_path: Optional[Path],
    dry_run: bool,
    organize: bool,
    skip_existing: bool,
):
    """Main entry point for cover sync command."""
    console = Console()

    # Create filesystem provider
    fs = create_filesystem(path, dry_run=dry_run)

    # Load databases if provided
    resolver = SerialResolver()
    if database_path and database_path.exists():
        console.print(f"[cyan]Loading ROM databases from {database_path}...[/cyan]")

        for platform in ['PSX', 'PS2']:
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
            )

            await sync.sync_covers(
                root_path=path,
                organize=organize,
                skip_existing=skip_existing,
            )

        finally:
            if isinstance(fs, FTPFilesystem):
                await fs.disconnect()
