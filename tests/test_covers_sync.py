"""Unit tests for cover sync functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from ps3toolbox.covers.downloader import CoverDownloader
from ps3toolbox.games.metadata import SerialResolver, RomDatabase, extract_serial_from_filename, clean_game_name
from ps3toolbox.games.scanner import GameScanner, GameFile
from ps3toolbox.utils.fs import LocalFilesystem


class TestSerialExtraction:
    """Test serial number extraction from filenames."""

    def test_extract_serial_parentheses(self):
        """Test extracting serial from (SLUS-12345) format."""
        assert extract_serial_from_filename("Gran Turismo 4 (SLUS-21001).iso") == "SLUS-21001"
        assert extract_serial_from_filename("Final Fantasy VII (SCUS-94163).bin") == "SCUS-94163"

    def test_extract_serial_brackets(self):
        """Test extracting serial from [SLUS_123.45] format."""
        assert extract_serial_from_filename("Game [SLUS_123.45].bin") == "SLUS-12345"
        assert extract_serial_from_filename("Game [SCES_001.23].iso") == "SCES-00123"

    def test_extract_serial_underscore_format(self):
        """Test normalizing underscore format to dash format."""
        assert extract_serial_from_filename("Game (SLUS_21001).iso") == "SLUS-21001"

    def test_no_serial_found(self):
        """Test when no serial is found in filename."""
        assert extract_serial_from_filename("Crash Bandicoot (USA).bin") is None
        assert extract_serial_from_filename("game.iso") is None

    def test_clean_game_name(self):
        """Test cleaning game names from filenames."""
        assert clean_game_name("Final Fantasy VII (USA) (Disc 1).bin") == "final fantasy vii"
        assert clean_game_name("Gran Turismo 4 (SLUS-21001).iso") == "gran turismo 4"
        assert clean_game_name("Crash Bandicoot (USA).bin") == "crash bandicoot"


class TestRomDatabase:
    """Test ROM database fuzzy matching."""

    @pytest.fixture
    def sample_db(self, tmp_path):
        """Create sample database for testing."""
        db_file = tmp_path / "test.tsv"
        db_file.write_text(
            "PSX\tUSA\tCrash Bandicoot (USA)\tcrash.zip\t1000000\n"
            "PSX\tUSA\tFinal Fantasy VII (USA) (SLUS-00700)\tfinal.zip\t2000000\n"
            "PSX\tEurope\tCrash Bandicoot (Europe)\tcrash_eu.zip\t1000000\n"
        )

        db = RomDatabase()
        db.load_from_tsv(db_file)
        return db

    def test_load_database(self, sample_db):
        """Test loading database from TSV."""
        assert len(sample_db.entries) == 3

    def test_fuzzy_match_exact(self, sample_db):
        """Test fuzzy matching with exact name."""
        result = sample_db.find_serial("Crash Bandicoot", region="USA", threshold=75.0)
        assert result is None  # No serial in this entry

    def test_fuzzy_match_with_serial(self, sample_db):
        """Test fuzzy matching when entry has serial."""
        result = sample_db.find_serial("Final Fantasy VII", region="USA", threshold=75.0)
        assert result is not None
        serial, confidence = result
        assert serial == "SLUS-00700"
        assert confidence > 75.0

    def test_fuzzy_match_region_filter(self, sample_db):
        """Test fuzzy matching with region filtering."""
        result = sample_db.find_serial("Crash Bandicoot", region="Europe", threshold=75.0)
        assert result is None  # Europe version has no serial


@pytest.mark.asyncio
class TestCoverDownloader:
    """Test cover downloader with multi-source fallback."""

    async def test_download_cover_success(self):
        """Test successful cover download."""
        downloader = CoverDownloader(max_concurrent=2)

        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"fake_image_data")

        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_response

            await downloader.start()
            result = await downloader.download_cover(
                platform="PS2",
                serial="SLUS-21001",
                game_name="Gran Turismo 4",
                resize=None,
            )
            await downloader.close()

            assert result is not None
            data, source = result
            assert data == b"fake_image_data"
            assert source in ["xlenore-2d", "xlenore-3d", "libretro"]

    async def test_download_cover_fallback(self):
        """Test fallback to next source when first fails."""
        downloader = CoverDownloader(max_concurrent=2)

        call_count = 0

        def mock_get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = AsyncMock()

            # First call fails, second succeeds
            if call_count == 1:
                mock_response.status = 404
            else:
                mock_response.status = 200
                mock_response.read = AsyncMock(return_value=b"fallback_image")

            # Create async context manager
            async_cm = AsyncMock()
            async_cm.__aenter__.return_value = mock_response
            async_cm.__aexit__.return_value = None
            return async_cm

        with patch('aiohttp.ClientSession.get', side_effect=mock_get_side_effect):
            await downloader.start()
            result = await downloader.download_cover(
                platform="PS2",
                serial="SLUS-21001",
                game_name="Gran Turismo 4",
                resize=None,
            )
            await downloader.close()

            assert result is not None
            assert call_count >= 2  # At least one fallback occurred

    async def test_download_no_serial_uses_libretro(self):
        """Test that LibRetro is used when no serial available."""
        downloader = CoverDownloader(max_concurrent=2)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"libretro_image")

        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_response

            await downloader.start()
            result = await downloader.download_cover(
                platform="NES",
                serial=None,
                game_name="Super Mario Bros",
                resize=None,
            )
            await downloader.close()

            assert result is not None
            data, source = result
            assert source == "libretro"


@pytest.mark.asyncio
class TestGameScanner:
    """Test game scanner for PS1/PS2/ROM detection."""

    async def test_scan_ps2_games(self):
        """Test scanning PS2 ISO files."""
        # Mock filesystem
        mock_fs = AsyncMock(spec=LocalFilesystem)

        # Mock directory structure
        async def mock_list_dir_impl(path):
            if path == "/games":
                # Root has PS2ISO folder
                folder = MagicMock()
                folder.name = "PS2ISO"
                folder.path = "/games/PS2ISO"
                folder.is_dir = True
                yield folder
            elif path == "/games/PS2ISO":
                # PS2ISO has one game
                file = MagicMock()
                file.name = "game.iso"
                file.path = "/games/PS2ISO/game.iso"
                file.is_dir = False
                yield file

        # Make list_dir return the async generator
        mock_fs.list_dir = mock_list_dir_impl
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.stem = lambda p: Path(p).stem
        mock_fs.exists = AsyncMock(return_value=False)

        scanner = GameScanner(mock_fs)
        games = []

        async for game in scanner.scan_root("/games"):
            games.append(game)

        assert len(games) == 1
        assert games[0].platform == "PS2"
        assert games[0].name == "game"

    async def test_scan_with_existing_cover(self):
        """Test detecting existing covers."""
        mock_fs = AsyncMock(spec=LocalFilesystem)

        async def mock_list_dir_impl(path):
            if path == "/games":
                folder = MagicMock()
                folder.name = "PSXISO"
                folder.path = "/games/PSXISO"
                folder.is_dir = True
                yield folder
            elif path == "/games/PSXISO":
                game_file = MagicMock()
                game_file.name = "game.bin"
                game_file.path = "/games/PSXISO/game.bin"
                game_file.is_dir = False
                yield game_file

                cover_file = MagicMock()
                cover_file.name = "game.PNG"
                cover_file.path = "/games/PSXISO/game.PNG"
                cover_file.is_dir = False
                yield cover_file

        mock_fs.list_dir = mock_list_dir_impl
        mock_fs.dirname = lambda p: str(Path(p).parent)
        mock_fs.basename = lambda p: Path(p).name
        mock_fs.stem = lambda p: Path(p).stem
        mock_fs.exists = AsyncMock(return_value=False)

        scanner = GameScanner(mock_fs)
        games = []

        async for game in scanner.scan_root("/games"):
            games.append(game)

        assert len(games) == 1
        assert games[0].has_cover is True
        assert games[0].cover_path == "/games/PSXISO/game.PNG"


@pytest.mark.asyncio
class TestSerialResolver:
    """Test serial resolution with multiple strategies."""

    async def test_resolve_from_filename(self):
        """Test resolving serial directly from filename."""
        resolver = SerialResolver()

        result = await resolver.resolve(
            "Gran Turismo 4 (SLUS-21001).iso",
            platform="PS2",
            use_fuzzy=False,
        )

        assert result is not None
        serial, method = result
        assert serial == "SLUS-21001"
        assert method == "filename"

    async def test_resolve_with_fuzzy_matching(self, tmp_path):
        """Test resolving serial via fuzzy matching."""
        # Create mock database
        db_file = tmp_path / "PS2.tsv"
        db_file.write_text(
            "PS2\tUSA\tGran Turismo 4 (SLUS-21001)\tgt4.zip\t5000000000\n"
        )

        db = RomDatabase()
        db.load_from_tsv(db_file)

        resolver = SerialResolver()
        resolver.add_database("PS2", db)

        result = await resolver.resolve(
            "Gran Turismo 4 (USA).iso",
            platform="PS2",
            use_fuzzy=True,
        )

        assert result is not None
        serial, method = result
        assert serial == "SLUS-21001"
        assert method in ["fuzzy_exact", "fuzzy_region", "fuzzy"]

    async def test_resolve_no_match(self):
        """Test when no serial can be resolved."""
        resolver = SerialResolver()

        result = await resolver.resolve(
            "Unknown Game.iso",
            platform="PS2",
            use_fuzzy=False,
        )

        assert result is None
