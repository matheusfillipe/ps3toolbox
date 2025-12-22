"""Game organizer for PS1/PS2 folder structure management."""

from dataclasses import dataclass
from typing import Optional

from ps3toolbox.utils.fs import FilesystemProvider


@dataclass
class OrganizeAction:
    """Represents a file organization action."""
    action_type: str
    src: str
    dst: str
    reason: str


class GameOrganizer:
    """Organize PS1/PS2 games into proper folder structures."""

    def __init__(self, fs: FilesystemProvider, dry_run: bool = False):
        self.fs = fs
        self.dry_run = dry_run

    async def organize_ps1_game(
        self,
        game_files: list[str],
        game_name: str,
        base_folder: str,
    ) -> list[OrganizeAction]:
        """
        Organize PS1 game files into a dedicated folder.

        Structure:
            /PSXISO/Game Name/
                Game Name.bin
                Game Name.cue
                Game Name.PNG

        Args:
            game_files: List of file paths (.bin, .cue, etc.)
            game_name: Clean game name for folder
            base_folder: Base PSXISO folder path

        Returns:
            List of organization actions performed
        """
        actions = []

        # Check if files are already organized
        if len(game_files) == 0:
            return actions

        # Get current folder of first file
        current_folder = self.fs.dirname(game_files[0])
        target_folder = self.fs.join_path(base_folder, game_name)

        # If already in correct folder, skip
        if current_folder == target_folder:
            return actions

        # Create target folder
        if not await self.fs.exists(target_folder):
            actions.append(OrganizeAction(
                action_type='mkdir',
                src='',
                dst=target_folder,
                reason=f'Create folder for {game_name}',
            ))
            await self.fs.mkdir(target_folder)

        # Move all game files to target folder
        for file_path in game_files:
            filename = self.fs.basename(file_path)
            dst_path = self.fs.join_path(target_folder, filename)

            if file_path != dst_path:
                actions.append(OrganizeAction(
                    action_type='move',
                    src=file_path,
                    dst=dst_path,
                    reason=f'Organize {filename} into game folder',
                ))
                await self.fs.rename(file_path, dst_path)

        return actions

    async def organize_ps2_game(
        self,
        iso_path: str,
        game_name: str,
        base_folder: str,
    ) -> list[OrganizeAction]:
        """
        Organize PS2 game into a dedicated folder.

        Structure:
            /PS2ISO/Game Name/
                Game Name.iso
                Game Name.PNG

        Args:
            iso_path: Path to .iso file
            game_name: Clean game name for folder
            base_folder: Base PS2ISO folder path

        Returns:
            List of organization actions performed
        """
        actions = []

        # Get current folder
        current_folder = self.fs.dirname(iso_path)
        target_folder = self.fs.join_path(base_folder, game_name)

        # If already in correct folder, skip
        if current_folder == target_folder:
            return actions

        # Create target folder
        if not await self.fs.exists(target_folder):
            actions.append(OrganizeAction(
                action_type='mkdir',
                src='',
                dst=target_folder,
                reason=f'Create folder for {game_name}',
            ))
            await self.fs.mkdir(target_folder)

        # Move ISO to target folder
        filename = self.fs.basename(iso_path)
        dst_path = self.fs.join_path(target_folder, filename)

        if iso_path != dst_path:
            actions.append(OrganizeAction(
                action_type='move',
                src=iso_path,
                dst=dst_path,
                reason=f'Organize {filename} into game folder',
            ))
            await self.fs.rename(iso_path, dst_path)

        return actions

    async def find_existing_cover(
        self,
        folder: str,
        game_name: str,
    ) -> Optional[str]:
        """
        Find existing cover image in folder.

        Looks for:
        - Exact match: {game_name}.PNG, {game_name}.JPG
        - Any .PNG or .JPG file if only one exists
        - Folder.png if folder name matches game name

        Returns:
            Path to cover file or None
        """
        cover_exts = ['.PNG', '.png', '.JPG', '.jpg']

        # Check for exact match
        for ext in cover_exts:
            cover_path = self.fs.join_path(folder, game_name + ext)
            if await self.fs.exists(cover_path):
                return cover_path

        # Check for folder-named cover
        folder_name = self.fs.basename(folder)
        for ext in cover_exts:
            cover_path = self.fs.join_path(folder, folder_name + ext)
            if await self.fs.exists(cover_path):
                return cover_path

        # Check if only one image exists
        images = []
        async for item in self.fs.list_dir(folder):
            if item.is_dir:
                continue

            file_ext = self.fs.basename(item.path)[self.fs.basename(item.path).rfind('.'):]
            if file_ext in cover_exts:
                images.append(item.path)

        if len(images) == 1:
            return images[0]

        return None

    async def rename_cover_to_match_game(
        self,
        cover_path: str,
        game_name: str,
    ) -> Optional[OrganizeAction]:
        """
        Rename existing cover to match game name.

        Args:
            cover_path: Current cover path
            game_name: Target game name

        Returns:
            OrganizeAction if rename needed, None otherwise
        """
        folder = self.fs.dirname(cover_path)
        current_ext = cover_path[cover_path.rfind('.'):]

        # Target: uppercase extension for webMAN compatibility
        target_ext = '.PNG' if current_ext.lower() == '.png' else '.JPG'
        target_name = game_name + target_ext
        target_path = self.fs.join_path(folder, target_name)

        if cover_path == target_path:
            return None

        action = OrganizeAction(
            action_type='rename',
            src=cover_path,
            dst=target_path,
            reason=f'Rename cover to match game name',
        )

        await self.fs.rename(cover_path, target_path)
        return action
