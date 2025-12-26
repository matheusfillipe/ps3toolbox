# Architecture

## Project Structure

```
ps3toolbox/
├── src/ps3toolbox/
│   ├── cli.py              # Command-line interface entry point
│   ├── core/               # Core cryptography and PS2 operations
│   │   ├── crypto.py       # AES encryption/decryption
│   │   ├── keys.py         # Key derivation and management
│   │   └── iso.py          # ISO utilities
│   ├── ps2/                # PS2-specific functionality
│   │   ├── encrypt.py      # ISO encryption to .BIN.ENC
│   │   ├── decrypt.py      # .BIN.ENC decryption to ISO
│   │   ├── header.py       # File header parsing/generation
│   │   └── limg.py         # LIMG header handling
│   ├── covers/             # Cover art management
│   │   ├── downloader.py   # Multi-source cover downloader
│   │   └── sync.py         # Cover sync orchestration
│   ├── games/              # Game file management
│   │   ├── scanner.py      # Game file discovery
│   │   ├── organizer.py    # Game organization
│   │   ├── metadata.py     # Serial extraction
│   │   └── database.py     # ROM database handling
│   └── utils/              # Shared utilities
│       ├── fs/             # Filesystem abstraction
│       │   └── provider.py # Local and FTP filesystem
│       ├── progress.py     # Progress reporting
│       ├── validation.py   # Input validation
│       └── disc_detect.py  # Multi-disc detection
├── tests/                  # Test suite
├── .github/workflows/      # GitHub Actions CI
└── pyproject.toml          # Project configuration
```

## Core Components

### PS2 Encryption Pipeline

1. ISO padding to 0x4000-byte boundary
2. LIMG header addition
3. AES-128-CBC segmented encryption
4. Metadata (SHA-1 hashes) generation
5. Interleaved meta/data output

See `src/ps3toolbox/ps2/encrypt.py` for implementation.

### Cover Art System

Multi-source fallback chain:
1. xlenore GitHub repos (serial-based)
2. LibRetro thumbnails (exact name match)
3. LibRetro thumbnails (fuzzy match)
4. Google Images web search

Supports local and FTP filesystems via abstraction layer.

### Filesystem Abstraction

`FilesystemProvider` interface with implementations:
- `LocalFilesystem`: Local file operations
- `FTPFilesystem`: PS3 FTP operations with Latin-1 encoding

## Development Workflow

### Linting

Pre-commit manages all linting tools (ruff, mypy):

```bash
# Run all pre-commit hooks
uv run pre-commit run --all-files

# Auto-install hooks to run on git commit
uv run pre-commit install
```

Configuration:
- Ruff: 120 character line length, single import per line
- Mypy: Basic type checking with relaxed rules
- See `.pre-commit-config.yaml` and `pyproject.toml` for details

### Testing

```bash
# Run tests
uv run pytest

# With coverage
uv run pytest --cov=src/ps3toolbox

# Specific test file
uv run pytest tests/test_crypto.py
```

Tests use pytest with:
- pytest-cov for coverage
- pytest-asyncio for async tests
- pytest-mock for mocking

### CI Pipeline

GitHub Actions runs on push/PR:
1. Ruff linting and formatting checks
2. Mypy type checking (continue on error)
3. Pytest test suite
4. Matrix testing on Python 3.10, 3.11, 3.12

## Key Technologies

- **Click**: CLI framework
- **Rich**: Terminal output formatting
- **aiohttp**: Async HTTP for cover downloads
- **cryptography**: AES encryption primitives
- **Pillow**: Image processing for covers
- **pytest**: Testing framework

## Design Principles

- Async/await for I/O-bound operations
- Filesystem abstraction for local/FTP transparency
- Multi-source fallback for reliability
- Parallel processing for batch operations
- Progress reporting for long-running tasks
