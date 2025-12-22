"""Multi-source cover downloader with fallback strategies."""

import asyncio
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

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


class CoverDownloader:
    """Multi-source cover downloader with parallel workers."""

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

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

    async def download_cover(
        self,
        platform: str,
        serial: Optional[str],
        game_name: str,
        resize: Optional[tuple[int, int]] = (240, 240),
    ) -> Optional[tuple[bytes, str]]:
        """
        Download cover from multiple sources with fallback.

        Args:
            platform: Platform code (PSX, PS2, NES, etc.)
            serial: Game serial number (optional)
            game_name: Clean game name for LibRetro matching
            resize: Optional resize dimensions (width, height)

        Returns:
            Tuple of (image_data, source_name) or None
        """
        await self.start()

        sources = COVER_SOURCES.get(platform, [])
        if not sources:
            return None

        async with self._semaphore:
            for source in sources:
                # Skip sources that require serial if we don't have one
                if source.requires_serial and not serial:
                    continue

                # Build URL
                if source.requires_serial:
                    url = source.url_template.format(serial=serial)
                else:
                    url = source.url_template.format(name=game_name)

                # Try to download
                result = await self._download_from_url(url, resize)
                if result:
                    return result, source.name

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
    ) -> list[Optional[tuple[bytes, str]]]:
        """
        Download multiple covers in parallel.

        Args:
            tasks: List of (platform, serial, game_name) tuples
            resize: Optional resize dimensions

        Returns:
            List of results (same order as tasks)
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
