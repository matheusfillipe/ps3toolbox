"""Multi-source cover downloader with fallback strategies."""

import asyncio
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Optional
from urllib.parse import quote

import aiohttp
from PIL import Image


@dataclass
class CoverSource:
    """Cover art source configuration."""
    name: str
    url_template: str
    requires_serial: bool


COVER_SOURCES = {
    'PSX': [
        CoverSource(
            name='xlenore-2d',
            url_template='https://raw.githubusercontent.com/xlenore/psx-covers/main/covers/default/{serial}.jpg',
            requires_serial=True,
        ),
        CoverSource(
            name='xlenore-3d',
            url_template='https://raw.githubusercontent.com/xlenore/psx-covers/main/covers/3d/{serial}.png',
            requires_serial=True,
        ),
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Sony_-_PlayStation/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
    'PS2': [
        CoverSource(
            name='xlenore-2d',
            url_template='https://raw.githubusercontent.com/xlenore/ps2-covers/main/covers/default/{serial}.jpg',
            requires_serial=True,
        ),
        CoverSource(
            name='xlenore-3d',
            url_template='https://raw.githubusercontent.com/xlenore/ps2-covers/main/covers/3d/{serial}.png',
            requires_serial=True,
        ),
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Sony_-_PlayStation_2/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
    'NES': [
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
    'SNES': [
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Nintendo_-_Super_Nintendo_Entertainment_System/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
    'GB': [
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Nintendo_-_Game_Boy/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
    'GBC': [
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Nintendo_-_Game_Boy_Color/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
    'GBA': [
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Nintendo_-_Game_Boy_Advance/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
    'Genesis': [
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Sega_-_Mega_Drive_-_Genesis/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
    'SMS': [
        CoverSource(
            name='libretro',
            url_template='https://raw.githubusercontent.com/libretro-thumbnails/Sega_-_Master_System_-_Mark_III/master/Named_Boxarts/{name}.png',
            requires_serial=False,
        ),
    ],
}


def clean_name_for_matching(name: str) -> str:
    """Clean game name for fuzzy matching."""
    # Remove numeric prefixes like "100. "
    name = re.sub(r'^\d+\.\s*', '', name)
    # Remove extra whitespace
    name = ' '.join(name.split())
    return name


def fuzzy_match_score(s1: str, s2: str) -> float:
    """Simple fuzzy match score (0.0 to 1.0)."""
    s1_lower = s1.lower()
    s2_lower = s2.lower()

    # Exact match
    if s1_lower == s2_lower:
        return 1.0

    # One contains the other
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8

    # Word-based matching
    words1 = set(s1_lower.split())
    words2 = set(s2_lower.split())

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)


class CoverDownloader:
    """Multi-source cover downloader with parallel workers and fuzzy matching."""

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._cover_cache: dict[str, list[str]] = {}  # platform -> list of available covers

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Start HTTP session."""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={'User-Agent': 'ps3toolbox/0.1.0'}
            )

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def _fetch_available_covers(self, platform: str) -> list[str]:
        """Fetch list of available covers from LibRetro GitHub for fuzzy matching."""
        if platform in self._cover_cache:
            return self._cover_cache[platform]

        sources = COVER_SOURCES.get(platform, [])
        libretro_source = next((s for s in sources if s.name == 'libretro'), None)

        if not libretro_source:
            return []

        # Extract GitHub repo path from URL
        # e.g., https://raw.githubusercontent.com/libretro-thumbnails/Nintendo_-_Super_Nintendo_Entertainment_System/master/Named_Boxarts/{name}.png
        # -> https://api.github.com/repos/libretro-thumbnails/Nintendo_-_Super_Nintendo_Entertainment_System/contents/Named_Boxarts
        parts = libretro_source.url_template.split('/')
        if len(parts) < 7:
            return []

        repo_owner = parts[3]
        repo_name = parts[4]
        branch = parts[5]
        folder_path = '/'.join(parts[6:-1])  # Remove {name}.png part

        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{folder_path}?ref={branch}"

        # Retry with backoff for rate limiting
        for attempt in range(3):
            try:
                async with self.session.get(api_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        files = await resp.json()
                        # Extract filenames without extension
                        cover_names = [f['name'].rsplit('.', 1)[0] for f in files if f['type'] == 'file' and f['name'].endswith('.png')]
                        self._cover_cache[platform] = cover_names
                        return cover_names
                    elif resp.status == 403:  # Rate limited
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                            continue
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue

        return []

    async def _search_web_for_cover(self, game_name: str, platform: str) -> list[str]:
        """Search for game cover images using Google Images."""
        try:
            # Map platform codes to better search terms
            platform_search_names = {
                'Atari2600': 'Atari 2600',
                'Atari5200': 'Atari 5200',
                'Atari7800': 'Atari 7800',
                'NES': 'Nintendo NES',
                'SNES': 'Super Nintendo SNES',
                'GB': 'Game Boy',
                'GBC': 'Game Boy Color',
                'GBA': 'Game Boy Advance',
                'Genesis': 'Sega Genesis',
                'SMS': 'Sega Master System',
                'PSX': 'PlayStation 1 PS1',
                'PS2': 'PlayStation 2',
            }
            search_platform = platform_search_names.get(platform, platform)

            search_query = f"{game_name} {search_platform} game cover box art"

            # Use Google Images search with simple scraping
            async with self.session.get(
                'https://www.google.com/search',
                params={
                    'q': search_query,
                    'tbm': 'isch',  # Image search
                    'safe': 'off',
                },
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return []

                html = await resp.text()

                # Extract image URLs from the HTML
                # Google Images embeds URLs in various formats
                urls = []

                # Pattern 1: Direct image URLs in img tags
                img_pattern = r'<img[^>]+src="([^"]+)"[^>]*>'
                for match in re.finditer(img_pattern, html):
                    url = match.group(1)
                    if url.startswith('http') and not 'google' in url:
                        urls.append(url)

                # Pattern 2: URLs in JSON data
                json_pattern = r'"ou":"([^"]+)"'
                for match in re.finditer(json_pattern, html):
                    url = match.group(1)
                    if url.startswith('http'):
                        urls.append(url)

                # Return first 5 unique URLs
                seen = set()
                unique_urls = []
                for url in urls:
                    if url not in seen and len(unique_urls) < 5:
                        seen.add(url)
                        unique_urls.append(url)

                return unique_urls

        except Exception:
            return []

    async def download_cover(
        self,
        platform: str,
        serial: Optional[str],
        game_name: str,
        resize: Optional[tuple[int, int]] = (240, 240),
    ) -> Optional[tuple[bytes, str, str]]:
        """
        Download cover from multiple sources with fallback and fuzzy matching.

        Args:
            platform: Platform code (PSX, PS2, NES, etc.)
            serial: Game serial number (optional)
            game_name: Game name (will be cleaned and fuzzy matched)
            resize: Optional resize dimensions (width, height)

        Returns:
            Tuple of (image_data, source_name, url) or None
        """
        await self.start()

        sources = COVER_SOURCES.get(platform, [])

        # Clean the game name
        clean_name = clean_name_for_matching(game_name)

        async with self._semaphore:
            # Try platform-specific sources if available
            for source in sources:
                # Skip sources that require serial if we don't have one
                if source.requires_serial and not serial:
                    continue

                # Build URL
                if source.requires_serial:
                    url = source.url_template.format(serial=serial)
                    lookup_name = None
                else:
                    # Try exact match first
                    url = source.url_template.format(name=quote(clean_name))
                    lookup_name = clean_name

                # Try to download with exact name
                result = await self._download_from_url(url, resize)
                if result:
                    return result, source.name, url

                # If LibRetro and exact match failed, try fuzzy matching
                if source.name == 'libretro' and lookup_name:
                    available_covers = await self._fetch_available_covers(platform)
                    if available_covers:
                        # Find best match
                        best_match = None
                        best_score = 0.6  # Minimum threshold

                        for cover_name in available_covers:
                            score = fuzzy_match_score(clean_name, cover_name)
                            if score > best_score:
                                best_score = score
                                best_match = cover_name

                        if best_match:
                            fuzzy_url = source.url_template.format(name=quote(best_match))
                            result = await self._download_from_url(fuzzy_url, resize)
                            if result:
                                return result, f"{source.name} (fuzzy: {best_score:.0%})", fuzzy_url

            # Final fallback: web image search
            web_urls = await self._search_web_for_cover(clean_name, platform)
            for url in web_urls:
                result = await self._download_from_url(url, resize)
                if result:
                    return result, "web-search", url

        return None

    async def _download_from_url(
        self,
        url: str,
        resize: Optional[tuple[int, int]] = None,
    ) -> Optional[bytes]:
        """Download and optionally resize image from URL."""
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.read()

                    # Resize if requested
                    if resize:
                        data = await self._resize_image(data, resize)

                    return data
        except Exception:
            pass

        return None

    async def _resize_image(self, data: bytes, size: tuple[int, int]) -> bytes:
        """Resize image to target size while maintaining aspect ratio."""
        def _resize():
            img = Image.open(BytesIO(data))

            # Convert to RGB if needed (for PNG with transparency)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background

            # Resize maintaining aspect ratio
            img.thumbnail(size, Image.Resampling.LANCZOS)

            # Convert to target format (PNG)
            output = BytesIO()
            img.save(output, format='PNG', optimize=True)
            return output.getvalue()

        return await asyncio.to_thread(_resize)

    async def download_batch(
        self,
        tasks: list[tuple[str, Optional[str], str]],
        resize: Optional[tuple[int, int]] = (240, 240),
    ) -> list[Optional[tuple[bytes, str, str]]]:
        """
        Download multiple covers in parallel.

        Args:
            tasks: List of (platform, serial, game_name) tuples
            resize: Optional resize dimensions

        Returns:
            List of results (same order as tasks) - each result is (bytes, source_name, url)
        """
        await self.start()

        async def _download_task(platform: str, serial: Optional[str], game_name: str):
            return await self.download_cover(platform, serial, game_name, resize)

        results = await asyncio.gather(
            *[_download_task(platform, serial, name) for platform, serial, name in tasks],
            return_exceptions=True,
        )

        # Convert exceptions to None
        return [r if not isinstance(r, Exception) else None for r in results]
