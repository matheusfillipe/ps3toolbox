"""Serial number resolver with fuzzy matching against ROM databases."""

import csv
import re
from pathlib import Path
from typing import Optional

from thefuzz import fuzz


SERIAL_PATTERNS = {
    'parentheses': re.compile(r'\(([A-Z]{4}[-_]\d{3}[.\d]{2,3})\)'),
    'brackets': re.compile(r'\[([A-Z]{4}[-_]\d{3}[.\d]{2,3})\]'),
    'standalone': re.compile(r'\b([A-Z]{4}[-_]\d{3}[.\d]{2,3})\b'),
}

REGION_PATTERNS = {
    'USA': re.compile(r'\((?:USA|US)\)', re.IGNORECASE),
    'Europe': re.compile(r'\((?:Europe|EUR|PAL)\)', re.IGNORECASE),
    'Japan': re.compile(r'\((?:Japan|JPN)\)', re.IGNORECASE),
    'World': re.compile(r'\(World\)', re.IGNORECASE),
    'Asia': re.compile(r'\((?:Asia|ASA)\)', re.IGNORECASE),
}


def normalize_serial(serial: str) -> str:
    """Normalize serial to standard format: SLUS-12345."""
    serial = serial.upper()
    serial = serial.replace('_', '-')
    serial = serial.replace('.', '')
    return serial


def extract_serial_from_filename(filename: str) -> Optional[str]:
    """
    Extract serial from filename using various patterns.

    Examples:
        "Gran Turismo 4 (SLUS-21001).iso" → "SLUS-21001"
        "Final Fantasy VII [SLUS_007.00].bin" → "SLUS-00700"
        "Crash Bandicoot (USA).bin" → None
    """
    for pattern_name, pattern in SERIAL_PATTERNS.items():
        match = pattern.search(filename)
        if match:
            return normalize_serial(match.group(1))

    return None


def extract_region_from_filename(filename: str) -> Optional[str]:
    """
    Extract region from filename.

    Examples:
        "Digimon World 3 (USA).bin" → "USA"
        "Final Fantasy VII (Europe).bin" → "Europe"
    """
    for region, pattern in REGION_PATTERNS.items():
        if pattern.search(filename):
            return region

    return None


def clean_game_name(filename: str) -> str:
    """
    Clean game name from filename by removing metadata.

    Examples:
        "Final Fantasy VII (USA) (Disc 1).bin" → "final fantasy vii"
        "Gran Turismo 4 (SLUS-21001).iso" → "gran turismo 4"
    """
    name = Path(filename).stem

    # Remove serial patterns
    for pattern in SERIAL_PATTERNS.values():
        name = pattern.sub('', name)

    # Remove region patterns
    name = re.sub(r'\([^)]*\)', '', name)
    name = re.sub(r'\[[^\]]*\]', '', name)

    # Remove disc info
    name = re.sub(r'\bDisc\s+\d+\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\bCD\s+\d+\b', '', name, flags=re.IGNORECASE)

    # Clean whitespace
    name = re.sub(r'\s+', ' ', name).strip().lower()

    return name


class RomDatabase:
    """ROM database for fuzzy matching game names to serials."""

    def __init__(self):
        self.entries: list[dict] = []

    def load_from_tsv(self, tsv_path: Path):
        """Load database from TSV file (myrient format)."""
        with open(tsv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(
                f,
                delimiter='\t',
                fieldnames=['platform', 'region', 'name', 'url', 'size']
            )

            for row in reader:
                # Extract serial from name if present
                serial = extract_serial_from_filename(row['name'])
                clean_name = clean_game_name(row['name'])

                self.entries.append({
                    'name': row['name'],
                    'clean_name': clean_name,
                    'region': row['region'],
                    'serial': serial,
                    'platform': row['platform'],
                })

    def find_serial(
        self,
        game_name: str,
        region: Optional[str] = None,
        threshold: float = 75.0
    ) -> Optional[tuple[str, float]]:
        """
        Find serial by fuzzy matching game name.

        Args:
            game_name: Game name to match
            region: Optional region to filter (USA, Europe, Japan, etc.)
            threshold: Minimum match score (0-100)

        Returns:
            Tuple of (serial, confidence_score) or None
        """
        clean_name = clean_game_name(game_name)

        # Filter by region if provided
        candidates = self.entries
        if region:
            candidates = [e for e in candidates if e['region'] == region]

        best_match = None
        best_score = 0.0

        for entry in candidates:
            if not entry['serial']:
                continue

            # Use fuzzy matching
            score = fuzz.ratio(clean_name, entry['clean_name'])

            # Boost for exact substring matches
            if clean_name in entry['clean_name'] or entry['clean_name'] in clean_name:
                score += 10

            if score > best_score:
                best_score = score
                best_match = entry

        if best_score >= threshold and best_match:
            return best_match['serial'], best_score

        return None


class SerialResolver:
    """Resolve game serials using multiple strategies."""

    def __init__(self, databases: Optional[dict[str, RomDatabase]] = None):
        self.databases = databases or {}

    def add_database(self, platform: str, database: RomDatabase):
        """Add ROM database for a platform."""
        self.databases[platform] = database

    async def resolve(
        self,
        filename: str,
        platform: str,
        use_fuzzy: bool = True
    ) -> Optional[tuple[str, str]]:
        """
        Resolve serial for a game file.

        Args:
            filename: Game filename
            platform: Platform (PSX, PS2, etc.)
            use_fuzzy: Whether to use fuzzy matching

        Returns:
            Tuple of (serial, method) or None
            method: 'filename' | 'fuzzy_exact' | 'fuzzy_region' | 'fuzzy'
        """
        # Strategy 1: Extract from filename
        serial = extract_serial_from_filename(filename)
        if serial:
            return serial, 'filename'

        if not use_fuzzy or platform not in self.databases:
            return None

        db = self.databases[platform]
        game_name = clean_game_name(filename)
        region = extract_region_from_filename(filename)

        # Strategy 2: Fuzzy match with region filter
        if region:
            result = db.find_serial(game_name, region=region, threshold=85.0)
            if result:
                return result[0], 'fuzzy_exact'

        # Strategy 3: Fuzzy match any region (high threshold)
        result = db.find_serial(game_name, region=None, threshold=85.0)
        if result:
            return result[0], 'fuzzy_region'

        # Strategy 4: Fuzzy match any region (lower threshold)
        result = db.find_serial(game_name, region=None, threshold=75.0)
        if result:
            return result[0], 'fuzzy'

        return None
