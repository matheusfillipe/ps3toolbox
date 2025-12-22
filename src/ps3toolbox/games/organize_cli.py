"""PS1/PS2 game organizer - merge .bin/.cue files into folders with covers."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ps3toolbox.utils.fs import LocalFilesystem


@dataclass
class GameGroup:
    """Group of files belonging to one game."""
    base_name: str
    game_files: list[str]
    folder: str
    existing_cover: Optional[str] = None
    chosen_cover: Optional[str] = None


@dataclass
class OrganizeStats:
    """Statistics for organize operation."""
    games_found: int = 0
    already_organized: int = 0
    folders_created: int = 0
    files_moved: int = 0
    covers_copied: int = 0
    covers_renamed: int = 0


GAME_EXTS = {'.iso', '.bin', '.img', '.pbp', '.cue', '.ccd', '.sub'}
COVER_EXTS = {'.jpg', '.png', '.PNG', '.JPG'}
DEFAULT_COVER_EXTS = ['.PNG', '.JPG', '.png', '.jpg']


class GameOrganizer:
    """Organize PS1/PS2 games into folders with covers."""

    def __init__(self, fs: LocalFilesystem, dry_run: bool = False, any_image: bool = False):
        self.fs = fs
        self.dry_run = dry_run
        self.any_image = any_image

    async def find_images_in_folder(self, folder: str) -> list[str]:
        """Find all image files in folder."""
        images = []
        async for item in self.fs.list_dir(folder):
            if item.is_dir:
                continue

            ext = Path(item.name).suffix
            if ext in COVER_EXTS:
                images.append(item.path)

        return sorted(images)

    async def has_exact_cover(self, game_path: str) -> Optional[str]:
        """Check if game has exact matching cover."""
        stem = self.fs.stem(game_path)
        folder = self.fs.dirname(game_path)

        for ext in DEFAULT_COVER_EXTS:
            cover_path = self.fs.join_path(folder, stem + ext)
            if await self.fs.exists(cover_path):
                return cover_path

        return None

    async def choose_best_cover(
        self,
        game_path: str,
        base_name: str,
    ) -> Optional[str]:
        """
        Choose best cover image for game using heuristics.

        Strategy (from fix_psx_covers.py):
        1. Exact match with different extension
        2. Same folder named as parent folder
        3. Parent folder named as parent folder
        4. If exactly one image exists in folder
        5. If exactly one image exists in parent folder
        """
        folder = self.fs.dirname(game_path)
        parent = self.fs.dirname(folder)
        parent_basename = self.fs.basename(folder)

        images_here = await self.find_images_in_folder(folder)

        # ANY IMAGE MODE
        if self.any_image and images_here:
            return images_here[0]

        # 1. Exact match with different extension
        for ext in DEFAULT_COVER_EXTS:
            cover_path = self.fs.join_path(folder, base_name + ext)
            if await self.fs.exists(cover_path):
                return cover_path

        # 2. Same folder named as parent folder
        for ext in DEFAULT_COVER_EXTS:
            cover_path = self.fs.join_path(folder, parent_basename + ext)
            if await self.fs.exists(cover_path):
                return cover_path

        # 3. Parent folder named as parent folder
        if await self.fs.exists(parent):
            for ext in DEFAULT_COVER_EXTS:
                cover_path = self.fs.join_path(parent, parent_basename + ext)
                if await self.fs.exists(cover_path):
                    return cover_path

        # 4. If exactly one image exists in folder
        if len(images_here) == 1:
            return images_here[0]

        # 5. Parent folder single image
        if await self.fs.exists(parent):
            images_parent = await self.find_images_in_folder(parent)
            if len(images_parent) == 1:
                return images_parent[0]

        return None

    async def scan_for_games(self, root_path: str) -> list[GameGroup]:
        """
        Scan directory recursively for games and group related files.

        Groups files by stem (filename without extension).
        """
        # Collect all game files
        all_files = []

        async def _scan_recursive(path: str):
            if not await self.fs.exists(path):
                return

            async for item in self.fs.list_dir(path):
                if item.is_dir:
                    await _scan_recursive(item.path)
                else:
                    ext = Path(item.name).suffix.lower()
                    if ext in GAME_EXTS:
                        all_files.append(item.path)

        await _scan_recursive(root_path)

        # Group files by base name and folder
        grouped = defaultdict(lambda: defaultdict(list))

        for file_path in all_files:
            folder = self.fs.dirname(file_path)
            stem = self.fs.stem(file_path)
            grouped[folder][stem].append(file_path)

        # Create GameGroup objects
        game_groups = []

        for folder, stems in grouped.items():
            for stem, files in stems.items():
                # Check for existing exact cover
                existing_cover = None
                for file_path in files:
                    cover = await self.has_exact_cover(file_path)
                    if cover:
                        existing_cover = cover
                        break

                game_groups.append(GameGroup(
                    base_name=stem,
                    game_files=sorted(files),
                    folder=folder,
                    existing_cover=existing_cover,
                ))

        return game_groups

    async def organize_game(
        self,
        game: GameGroup,
        base_path: str,
    ) -> tuple[list[str], Optional[str]]:
        """
        Organize a single game into its own folder.

        Returns:
            (list of actions performed, cover path if copied)
        """
        actions = []

        # Determine target folder name
        # Use base_name, but clean it up
        target_folder_name = game.base_name
        target_folder = self.fs.join_path(base_path, target_folder_name)

        # Check if already organized
        if game.folder == target_folder:
            # Already in correct folder
            return actions, game.existing_cover

        # Create target folder
        if not await self.fs.exists(target_folder):
            actions.append(f"CREATE {target_folder}")
            await self.fs.mkdir(target_folder)

        # Move game files
        for file_path in game.game_files:
            filename = self.fs.basename(file_path)
            dst = self.fs.join_path(target_folder, filename)

            if file_path != dst:
                actions.append(f"MOVE {file_path} → {dst}")
                await self.fs.rename(file_path, dst)

        # Handle cover
        cover_copied = None

        if game.existing_cover:
            # Move existing cover
            cover_filename = self.fs.basename(game.existing_cover)
            cover_dst = self.fs.join_path(target_folder, cover_filename)

            if game.existing_cover != cover_dst:
                actions.append(f"MOVE COVER {game.existing_cover} → {cover_dst}")
                await self.fs.rename(game.existing_cover, cover_dst)
                cover_copied = cover_dst
        else:
            # Try to find a cover to copy
            # Use first game file as reference
            chosen_cover = await self.choose_best_cover(
                game.game_files[0],
                game.base_name,
            )

            if chosen_cover:
                # Copy cover to target folder
                cover_ext = Path(chosen_cover).suffix
                # Prefer uppercase extension
                if cover_ext.lower() == '.png':
                    cover_ext = '.PNG'
                elif cover_ext.lower() == '.jpg':
                    cover_ext = '.JPG'

                cover_dst = self.fs.join_path(target_folder, game.base_name + cover_ext)

                actions.append(f"COPY COVER {chosen_cover} → {cover_dst}")
                await self.fs.copy_file(chosen_cover, cover_dst)
                cover_copied = cover_dst

        return actions, cover_copied

    async def organize_all(
        self,
        root_path: str,
    ) -> OrganizeStats:
        """
        Organize all games in directory.

        Args:
            root_path: Root directory to scan

        Returns:
            Statistics for the operation
        """
        stats = OrganizeStats()

        # Scan for games
        games = await self.scan_for_games(root_path)
        stats.games_found = len(games)

        if not games:
            return stats

        # Process each game
        for game in games:
            target_folder = self.fs.join_path(root_path, game.base_name)

            # Check if already organized
            if game.folder == target_folder:
                stats.already_organized += 1
                continue

            # Organize this game
            actions, cover_copied = await self.organize_game(game, root_path)

            # Update stats
            for action in actions:
                if action.startswith('CREATE'):
                    stats.folders_created += 1
                elif action.startswith('MOVE') and 'COVER' not in action:
                    stats.files_moved += 1
                elif action.startswith('MOVE COVER'):
                    stats.covers_renamed += 1
                elif action.startswith('COPY COVER'):
                    stats.covers_copied += 1

        return stats


async def organize_games_command(
    path: str,
    dry_run: bool,
    any_image: bool,
):
    """Main entry point for organize command."""
    console = Console()

    # Validate path
    if not Path(path).exists():
        console.print(f"[red]✗[/red] Path does not exist: {path}")
        return

    if not Path(path).is_dir():
        console.print(f"[red]✗[/red] Path is not a directory: {path}")
        return

    # Create filesystem
    fs = LocalFilesystem(dry_run=dry_run)
    organizer = GameOrganizer(fs, dry_run=dry_run, any_image=any_image)

    console.print(f"\n[cyan]Scanning {path}...[/cyan]")
    console.print(f"  Dry run: {dry_run}")
    console.print(f"  Any image mode: {any_image}")

    # Scan for games
    games = await organizer.scan_for_games(path)

    if not games:
        console.print("\n[yellow]No games found[/yellow]")
        return

    console.print(f"\n[green]Found {len(games)} games[/green]")

    # Display preview in dry-run mode
    if dry_run:
        table = Table(title="Games to Organize (DRY RUN)")
        table.add_column("Game", style="cyan")
        table.add_column("Files", style="yellow")
        table.add_column("Current Folder", style="magenta")
        table.add_column("Has Cover", style="green")

        for game in games[:50]:  # Limit to 50 for display
            table.add_row(
                game.base_name,
                str(len(game.game_files)),
                game.folder,
                "✓" if game.existing_cover else "✗",
            )

        if len(games) > 50:
            table.add_row("...", "...", "...", f"+ {len(games) - 50} more")

        console.print("\n")
        console.print(table)

        # Show sample actions
        console.print("\n[cyan]Sample actions (first game):[/cyan]")
        if games:
            sample_game = games[0]
            target = fs.join_path(path, sample_game.base_name)

            if sample_game.folder != target:
                console.print(f"  CREATE FOLDER: {target}")
                for game_file in sample_game.game_files:
                    filename = fs.basename(game_file)
                    dst = fs.join_path(target, filename)
                    console.print(f"  MOVE: {game_file}")
                    console.print(f"    → {dst}")

                if sample_game.existing_cover:
                    cover_dst = fs.join_path(target, fs.basename(sample_game.existing_cover))
                    console.print(f"  MOVE COVER: {sample_game.existing_cover}")
                    console.print(f"    → {cover_dst}")
                else:
                    chosen = await organizer.choose_best_cover(
                        sample_game.game_files[0],
                        sample_game.base_name,
                    )
                    if chosen:
                        cover_ext = '.PNG' if chosen.endswith(('.png', '.PNG')) else '.JPG'
                        cover_dst = fs.join_path(target, sample_game.base_name + cover_ext)
                        console.print(f"  COPY COVER: {chosen}")
                        console.print(f"    → {cover_dst}")

        console.print("\n[yellow]Run without --dry-run to apply changes[/yellow]")
        return

    # Actually organize
    console.print("\n[cyan]Organizing games...[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing games...", total=len(games))

        stats = OrganizeStats()
        stats.games_found = len(games)

        for game in games:
            target_folder = fs.join_path(path, game.base_name)

            if game.folder == target_folder:
                stats.already_organized += 1
                progress.advance(task)
                continue

            actions, cover_copied = await organizer.organize_game(game, path)

            for action in actions:
                if action.startswith('CREATE'):
                    stats.folders_created += 1
                elif action.startswith('MOVE') and 'COVER' not in action:
                    stats.files_moved += 1
                elif action.startswith('MOVE COVER'):
                    stats.covers_renamed += 1
                elif action.startswith('COPY COVER'):
                    stats.covers_copied += 1

            progress.advance(task)

    # Display summary
    summary = Table(title="Organization Summary")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Count", style="green", justify="right")

    summary.add_row("Games found", str(stats.games_found))
    summary.add_row("Already organized", str(stats.already_organized))
    summary.add_row("Folders created", str(stats.folders_created))
    summary.add_row("Files moved", str(stats.files_moved))
    summary.add_row("Covers copied", str(stats.covers_copied))
    summary.add_row("Covers renamed", str(stats.covers_renamed))

    console.print("\n")
    console.print(summary)
    console.print("\n[green]✓[/green] Organization complete!")
