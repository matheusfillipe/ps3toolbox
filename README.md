# PS3 Toolbox

Python toolkit for PS3 homebrew operations: PS2 Classics encryption/decryption and cover art management.

## Features

- PS2 ISO encryption to .BIN.ENC format for PS3 PS2 Classics
- PS2 ISO decryption from .BIN.ENC back to ISO
- Batch processing with parallel execution
- Cover art download and sync for PS1/PS2/ROM games via FTP or local filesystem
- Multi-source cover fallback (xlenore, LibRetro, Google Images)
- Progress reporting and error handling

## Installation

```bash
git clone https://github.com/yourusername/ps3toolbox.git
cd ps3toolbox
uv sync
```

## Usage

### PS2 ISO Encryption

```bash
# Single file
ps3toolbox encrypt game.iso

# Batch process directory
ps3toolbox batch-encrypt /path/to/isos/ --workers 4

# With options
ps3toolbox encrypt game.iso output.bin.enc --mode cex --disc-num 1
```

### PS2 ISO Decryption

```bash
ps3toolbox decrypt game.bin.enc game.iso
```

### Cover Art Management

```bash
# Sync covers via FTP
ps3toolbox covers sync ftp://192.168.0.16/dev_hdd0

# Sync covers locally
ps3toolbox covers sync /path/to/games

# Dry run to preview
ps3toolbox covers sync /path/to/games --dry-run --platform ps2

# Organize games into folders
ps3toolbox organize /path/to/PSXISO
```

### File Information

```bash
ps3toolbox info encrypted_game.bin.enc
```

## Development

### Setup

```bash
uv sync
uv run pre-commit install
```

### Linting and Type Checking

```bash
# Run pre-commit hooks
uv run pre-commit run --all-files

# Run ruff
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Run mypy
uv run mypy src/
```

### Testing

```bash
# Run all tests
uv run pytest

# With coverage
uv run pytest --cov

# Specific test
uv run pytest tests/test_crypto.py
```

## License

GPL-3.0-or-later

Based on open-source implementations:
- apollo-ps3 by bucanero
- PS2Classics by sdkmap

## Disclaimer

For educational and homebrew use only. Ensure you have rights to any content used with this tool.
