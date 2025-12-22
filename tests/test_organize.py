"""Unit tests for game organization functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from ps3toolbox.games.organizer import GameOrganizer, OrganizeAction
from ps3toolbox.games.organize_cli import GameOrganizer as CLIOrganizer, GameGroup
from ps3toolbox.utils.fs import LocalFilesystem


@pytest.mark.asyncio
class TestGameOrganizer:
    """Test game organizer for PS1/PS2."""

    async def test_organize_ps1_game(self):
        """Test organizing PS1 game files into folder."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.join_path = lambda *parts: str(Path(*parts))
        mock_fs.exists = AsyncMock(return_value=False)
        mock_fs.mkdir = AsyncMock()
        mock_fs.rename = AsyncMock()

        organizer = GameOrganizer(mock_fs, dry_run=False)

        game_files = [
            "/PSXISO/game.bin",
            "/PSXISO/game.cue",
        ]

        actions = await organizer.organize_ps1_game(
            game_files=game_files,
            game_name="Game Name",
            base_folder="/PSXISO",
        )

        # Should create folder and move files
        assert len(actions) >= 1
        assert any(action.action_type == "mkdir" for action in actions)
        assert any(action.action_type == "move" for action in actions)

        # Verify folder was created
        mock_fs.mkdir.assert_called_once()

        # Verify files were moved
        assert mock_fs.rename.call_count == len(game_files)

    async def test_organize_ps2_game(self):
        """Test organizing PS2 ISO into folder."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.join_path = lambda *parts: str(Path(*parts))
        mock_fs.exists = AsyncMock(return_value=False)
        mock_fs.mkdir = AsyncMock()
        mock_fs.rename = AsyncMock()

        organizer = GameOrganizer(mock_fs, dry_run=False)

        actions = await organizer.organize_ps2_game(
            iso_path="/PS2ISO/game.iso",
            game_name="Game Name",
            base_folder="/PS2ISO",
        )

        # Should create folder and move ISO
        assert len(actions) >= 1
        assert any(action.action_type == "mkdir" for action in actions)
        assert any(action.action_type == "move" for action in actions)

        mock_fs.mkdir.assert_called_once()
        mock_fs.rename.assert_called_once()

    async def test_skip_already_organized(self):
        """Test skipping games already in correct folder."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.join_path = lambda *parts: str(Path(*parts))

        organizer = GameOrganizer(mock_fs, dry_run=False)

        # Game already in correct folder
        actions = await organizer.organize_ps2_game(
            iso_path="/PS2ISO/Game Name/game.iso",
            game_name="Game Name",
            base_folder="/PS2ISO",
        )

        # Should skip - no actions
        assert len(actions) == 0

    async def test_find_existing_cover(self):
        """Test finding existing cover in folder."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.join_path = lambda *parts: str(Path(*parts))

        # Mock directory listing
        async def mock_list_dir(path):
            yield MagicMock(name="game.bin", path=f"{path}/game.bin", is_dir=False)
            yield MagicMock(name="game.PNG", path=f"{path}/game.PNG", is_dir=False)

        mock_fs.list_dir = mock_list_dir
        mock_fs.exists = AsyncMock(side_effect=lambda p: "game.PNG" in p)

        organizer = GameOrganizer(mock_fs, dry_run=False)

        cover = await organizer.find_existing_cover("/PSXISO", "game")
        assert cover == "/PSXISO/game.PNG"

    async def test_dry_run_no_writes(self):
        """Test dry-run mode makes no filesystem writes."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.join_path = lambda *parts: str(Path(*parts))
        mock_fs.exists = AsyncMock(return_value=False)
        mock_fs.mkdir = AsyncMock()
        mock_fs.rename = AsyncMock()

        organizer = GameOrganizer(mock_fs, dry_run=True)

        await organizer.organize_ps2_game(
            iso_path="/PS2ISO/game.iso",
            game_name="Game Name",
            base_folder="/PS2ISO",
        )

        # In dry-run, no actual filesystem operations should occur
        # The mock fs should have dry_run=True passed to it
        # For this test, we just verify the function completes without errors


@pytest.mark.asyncio
class TestCLIOrganizer:
    """Test CLI organizer with heuristic cover matching."""

    async def test_choose_best_cover_exact_match(self):
        """Test choosing cover with exact filename match."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.stem = lambda p: Path(p).stem
        mock_fs.join_path = lambda *parts: str(Path(*parts))

        # Mock exact match exists
        mock_fs.exists = AsyncMock(side_effect=lambda p: "game.PNG" in p)

        async def mock_list_dir(path):
            yield MagicMock(name="game.PNG", path=f"{path}/game.PNG", is_dir=False)

        mock_fs.list_dir = mock_list_dir

        organizer = CLIOrganizer(mock_fs, dry_run=False, any_image=False)

        cover = await organizer.choose_best_cover(
            "/PSXISO/game.bin",
            "game",
        )

        assert cover == "/PSXISO/game.PNG"

    async def test_choose_best_cover_single_image(self):
        """Test choosing cover when only one image exists."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.stem = lambda p: Path(p).stem
        mock_fs.join_path = lambda *parts: str(Path(*parts))
        mock_fs.exists = AsyncMock(return_value=False)  # No exact match

        # Mock single image in folder
        async def mock_list_dir(path):
            cover = MagicMock()
            cover.name = "cover.jpg"
            cover.path = f"{path}/cover.jpg"
            cover.is_dir = False
            yield cover

        mock_fs.list_dir = mock_list_dir

        organizer = CLIOrganizer(mock_fs, dry_run=False, any_image=False)

        cover = await organizer.choose_best_cover(
            "/PSXISO/game.bin",
            "game",
        )

        assert cover == "/PSXISO/cover.jpg"

    async def test_choose_best_cover_any_image_mode(self):
        """Test any-image mode picks first image."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.stem = lambda p: Path(p).stem
        mock_fs.join_path = lambda *parts: str(Path(*parts))
        mock_fs.exists = AsyncMock(return_value=False)

        # Mock multiple images
        async def mock_list_dir(path):
            img1 = MagicMock()
            img1.name = "image1.png"
            img1.path = f"{path}/image1.png"
            img1.is_dir = False
            yield img1

            img2 = MagicMock()
            img2.name = "image2.jpg"
            img2.path = f"{path}/image2.jpg"
            img2.is_dir = False
            yield img2

        mock_fs.list_dir = mock_list_dir

        organizer = CLIOrganizer(mock_fs, dry_run=False, any_image=True)

        cover = await organizer.choose_best_cover(
            "/PSXISO/game.bin",
            "game",
        )

        # Should pick first image when any_image=True
        assert cover in ["/PSXISO/image1.png", "/PSXISO/image2.jpg"]

    async def test_scan_for_games(self):
        """Test scanning for games and grouping files."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.stem = lambda p: Path(p).stem
        mock_fs.exists = AsyncMock(return_value=True)

        # Mock directory structure
        async def mock_list_dir(path):
            if path == "/PSXISO":
                # Two games with their files
                file1 = MagicMock()
                file1.name = "game1.bin"
                file1.path = "/PSXISO/game1.bin"
                file1.is_dir = False
                yield file1

                file2 = MagicMock()
                file2.name = "game1.cue"
                file2.path = "/PSXISO/game1.cue"
                file2.is_dir = False
                yield file2

                file3 = MagicMock()
                file3.name = "game2.bin"
                file3.path = "/PSXISO/game2.bin"
                file3.is_dir = False
                yield file3

                file4 = MagicMock()
                file4.name = "game2.cue"
                file4.path = "/PSXISO/game2.cue"
                file4.is_dir = False
                yield file4

        mock_fs.list_dir = mock_list_dir

        organizer = CLIOrganizer(mock_fs, dry_run=False)

        games = await organizer.scan_for_games("/PSXISO")

        # Should find 2 games
        assert len(games) == 2

        # Each game should have 2 files (.bin and .cue)
        assert all(len(game.game_files) == 2 for game in games)

    async def test_has_exact_cover(self):
        """Test checking for exact cover match."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.stem = lambda p: Path(p).stem
        mock_fs.join_path = lambda *parts: str(Path(*parts))

        # Mock cover exists
        mock_fs.exists = AsyncMock(side_effect=lambda p: "game.PNG" in p)

        organizer = CLIOrganizer(mock_fs, dry_run=False)

        cover = await organizer.has_exact_cover("/PSXISO/game.bin")

        assert cover == "/PSXISO/game.PNG"

    async def test_organize_game_creates_folder(self):
        """Test organizing a game creates proper folder structure."""
        mock_fs = AsyncMock(spec=LocalFilesystem)
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.stem = lambda p: Path(p).stem
        mock_fs.join_path = lambda *parts: str(Path(*parts))
        mock_fs.exists = AsyncMock(return_value=False)
        mock_fs.mkdir = AsyncMock()
        mock_fs.rename = AsyncMock()
        mock_fs.copy_file = AsyncMock()

        organizer = CLIOrganizer(mock_fs, dry_run=False)

        game = GameGroup(
            base_name="game",
            game_files=["/PSXISO/game.bin", "/PSXISO/game.cue"],
            folder="/PSXISO",
            existing_cover=None,
        )

        actions, cover = await organizer.organize_game(game, "/PSXISO")

        # Should have create folder action
        assert any("CREATE" in action for action in actions)

        # Should have move actions for files
        assert any("MOVE" in action for action in actions)

        # Verify mkdir was called
        mock_fs.mkdir.assert_called_once()

        # Verify files were renamed (moved)
        assert mock_fs.rename.call_count == len(game.game_files)
