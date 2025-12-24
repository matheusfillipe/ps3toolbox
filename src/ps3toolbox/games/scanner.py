"""Game scanner for PS1/PS2/ROM files with platform detection."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from ps3toolbox.utils.fs import FilesystemProvider


@dataclass
class GameFile:
    """Represents a game file with metadata."""

    path: str
    name: str
    platform: str
    folder: str
    extensions: list[str]
    has_cover: bool
    cover_path: str | None


PLATFORM_FOLDERS = {
    "PS1": ["PSXISO", "PSX", "PS1"],
    "PS2": ["PS2ISO", "PS2"],
    "ROMS": ["ROMS"],
}

ROM_PLATFORMS = {
    "nes": "NES",
    "snes": "SNES",
    "gb": "GB",
    "gbc": "GBC",
    "gba": "GBA",
    "genesis": "Genesis",
    "gen": "Genesis",
    "megadrive": "Genesis",
    "sms": "SMS",
    "n64": "N64",
    "atari2600": "Atari2600",
    "atari5200": "Atari5200",
    "atari7800": "Atari7800",
    "lynx": "Lynx",
    "mame": "MAME",
    "mameplus": "MAME",
}

PS1_EXTENSIONS = {".bin", ".cue", ".img", ".pbp"}
PS2_EXTENSIONS = {".iso"}
ROM_EXTENSIONS = {
    ".nes",
    ".smc",
    ".sfc",
    ".gb",
    ".gbc",
    ".gba",
    ".gen",
    ".md",
    ".bin",
    ".sms",
    ".z64",
    ".n64",
    ".v64",
    ".a26",
    ".a52",
    ".a78",
    ".lnx",
    ".zip",
}

COVER_EXTENSIONS = {".png", ".jpg", ".PNG", ".JPG"}


class GameScanner:
    """Scan filesystem for games and their covers."""

    def __init__(self, fs: FilesystemProvider):
        self.fs = fs

    async def scan_root(self, root_path: str) -> AsyncIterator[GameFile]:
        """
        Scan root directory for platform folders and games.

        Expected structure:
            /root/PSXISO/   - PS1 games
            /root/PS2ISO/   - PS2 games
            /root/ROMS/     - Retro ROMs (organized by emulator)
        """
        # Check for platform folders
        platform_paths = {}

        async for item in self.fs.list_dir(root_path):
            if not item.is_dir:
                continue

            folder_name_upper = item.name.upper()

            # Check if it's a known platform folder
            for platform, folder_names in PLATFORM_FOLDERS.items():
                if folder_name_upper in folder_names:
                    platform_paths[platform] = item.path
                    break


        # Scan each platform
        if "PS1" in platform_paths:
            async for game in self._scan_ps1(platform_paths["PS1"]):
                yield game

        if "PS2" in platform_paths:
            async for game in self._scan_ps2(platform_paths["PS2"]):
                yield game

        if "ROMS" in platform_paths:
            async for game in self._scan_roms(platform_paths["ROMS"]):
                yield game

    async def _scan_ps1(self, ps1_path: str) -> AsyncIterator[GameFile]:
        """
        Scan PS1 directory for games.

        Games can be:
        - Single folder with .bin/.cue files
        - Nested in game-specific folders
        """
        async for game in self._scan_disc_games(ps1_path, "PSX", PS1_EXTENSIONS):
            yield game

    async def _scan_ps2(self, ps2_path: str) -> AsyncIterator[GameFile]:
        """Scan PS2 directory for .iso files."""
        async for game in self._scan_disc_games(ps2_path, "PS2", PS2_EXTENSIONS):
            yield game

    async def _scan_disc_games(
        self, base_path: str, platform: str, valid_extensions: set[str]
    ) -> AsyncIterator[GameFile]:
        """Scan directory for disc-based games (PS1/PS2)."""
        async for game_folder in self._find_game_folders(base_path):
            # Group files by game
            game_files = {}

            async for item in self.fs.list_dir(game_folder):
                if item.is_dir:
                    continue

                file_ext = self.fs.basename(item.path)[self.fs.basename(item.path).rfind(".") :].lower()

                # Game file
                if file_ext in valid_extensions:
                    stem = self.fs.stem(item.path)
                    if stem not in game_files:
                        game_files[stem] = {
                            "files": [],
                            "cover": None,
                        }
                    game_files[stem]["files"].append(item.path)

                # Cover file
                elif file_ext in COVER_EXTENSIONS:
                    stem = self.fs.stem(item.path)
                    if stem in game_files:
                        game_files[stem]["cover"] = item.path
                    else:
                        # Cover without exact match - try to find corresponding game
                        for game_stem in game_files:
                            if stem.startswith(game_stem) or game_stem.startswith(stem):
                                game_files[game_stem]["cover"] = item.path
                                break

            # Yield game entries
            for stem, data in game_files.items():
                if not data["files"]:
                    continue

                # Get all extensions for this game
                extensions = [self.fs.basename(f)[self.fs.basename(f).rfind(".") :].lower() for f in data["files"]]

                # Use first file as primary
                primary_file = data["files"][0]

                yield GameFile(
                    path=primary_file,
                    name=stem,
                    platform=platform,
                    folder=game_folder,
                    extensions=extensions,
                    has_cover=data["cover"] is not None,
                    cover_path=data["cover"],
                )

    async def _find_game_folders(self, base_path: str) -> AsyncIterator[str]:
        """
        Find all folders that contain game files.

        Searches recursively to handle:
        - Games directly in base_path
        - Games in subfolders (organized by letter, etc.)
        """
        # Check current folder
        has_game_files = False

        async for item in self.fs.list_dir(base_path):
            if item.is_dir:
                # Recursively check subfolders
                async for subfolder in self._find_game_folders(item.path):
                    yield subfolder
            else:
                # Check if this is a game file
                file_ext = self.fs.basename(item.path)[self.fs.basename(item.path).rfind(".") :].lower()
                if file_ext in PS1_EXTENSIONS or file_ext in PS2_EXTENSIONS:
                    has_game_files = True

        if has_game_files:
            yield base_path

    async def _scan_roms(self, roms_path: str) -> AsyncIterator[GameFile]:
        """
        Scan ROMS directory for retro games.

        Expected structure:
            /ROMS/nes/game.nes
            /ROMS/snes/game.sfc
            /ROMS/gb/game.gb
        """
        async for item in self.fs.list_dir(roms_path):
            if not item.is_dir:
                continue

            # Folder name indicates platform
            platform_folder = item.name.lower()
            platform = ROM_PLATFORMS.get(platform_folder)

            if not platform:
                continue

            # Scan ROM files in this platform folder
            async for rom in self._scan_rom_platform(item.path, platform):
                yield rom

    async def _scan_rom_platform(self, platform_path: str, platform: str) -> AsyncIterator[GameFile]:
        """Scan a specific ROM platform folder."""
        async for item in self.fs.list_dir(platform_path):
            if item.is_dir:
                # Recursively scan subfolders
                async for rom in self._scan_rom_platform(item.path, platform):
                    yield rom
                continue

            file_ext = self.fs.basename(item.path)[self.fs.basename(item.path).rfind(".") :].lower()

            if file_ext not in ROM_EXTENSIONS:
                continue

            stem = self.fs.stem(item.path)
            folder = self.fs.dirname(item.path)

            # Check for cover
            cover_path = None
            for cover_ext in COVER_EXTENSIONS:
                potential_cover = self.fs.join_path(folder, stem + cover_ext)
                if await self.fs.exists(potential_cover):
                    cover_path = potential_cover
                    break

            yield GameFile(
                path=item.path,
                name=stem,
                platform=platform,
                folder=folder,
                extensions=[file_ext],
                has_cover=cover_path is not None,
                cover_path=cover_path,
            )
