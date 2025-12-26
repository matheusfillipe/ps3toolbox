"""Filesystem abstraction for local and FTP operations."""

import asyncio
import io
from abc import ABC
from abc import abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from ftplib import FTP
from ftplib import all_errors
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import urlparse

import aiofiles


@dataclass
class FileInfo:
    """File information that works for both local and FTP."""

    path: str
    name: str
    size: int
    is_dir: bool


class FilesystemProvider(ABC):
    """Abstract filesystem provider."""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if path exists."""
        pass

    @abstractmethod
    async def is_dir(self, path: str) -> bool:
        """Check if path is directory."""
        pass

    @abstractmethod
    def list_dir(self, path: str) -> AsyncIterator[FileInfo]:
        """List directory contents."""
        pass

    @abstractmethod
    async def read_bytes(self, path: str, start: int = 0, length: int = -1) -> bytes:
        """Read file bytes (optionally from start position)."""
        pass

    @abstractmethod
    async def write_bytes(self, path: str, data: bytes) -> None:
        """Write bytes to file."""
        pass

    @abstractmethod
    async def copy_file(self, src: str, dst: str) -> None:
        """Copy file from src to dst."""
        pass

    @abstractmethod
    async def mkdir(self, path: str) -> None:
        """Create directory."""
        pass

    @abstractmethod
    async def rename(self, src: str, dst: str) -> None:
        """Rename/move file or directory."""
        pass

    @abstractmethod
    def join_path(self, *parts: str) -> str:
        """Join path components."""
        pass

    @abstractmethod
    def dirname(self, path: str) -> str:
        """Get directory name."""
        pass

    @abstractmethod
    def basename(self, path: str) -> str:
        """Get base name."""
        pass

    @abstractmethod
    def stem(self, path: str) -> str:
        """Get filename without extension."""
        pass


class LocalFilesystem(FilesystemProvider):
    """Local filesystem provider."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    async def exists(self, path: str) -> bool:
        return Path(path).exists()

    async def is_dir(self, path: str) -> bool:
        return Path(path).is_dir()

    async def list_dir(self, path: str) -> AsyncIterator[FileInfo]:
        p = Path(path)
        if not p.exists():
            return

        for item in p.iterdir():
            yield FileInfo(
                path=str(item),
                name=item.name,
                size=item.stat().st_size if item.is_file() else 0,
                is_dir=item.is_dir(),
            )

    async def read_bytes(self, path: str, start: int = 0, length: int = -1) -> bytes:
        async with aiofiles.open(path, "rb") as f:
            if start > 0:
                await f.seek(start)
            if length > 0:
                return await f.read(length)
            return await f.read()

    async def write_bytes(self, path: str, data: bytes) -> None:
        if self.dry_run:
            return

        async with aiofiles.open(path, "wb") as f:
            await f.write(data)

    async def copy_file(self, src: str, dst: str) -> None:
        if self.dry_run:
            return

        import shutil

        await asyncio.to_thread(shutil.copy2, src, dst)

    async def mkdir(self, path: str) -> None:
        if self.dry_run:
            return

        Path(path).mkdir(parents=True, exist_ok=True)

    async def rename(self, src: str, dst: str) -> None:
        if self.dry_run:
            return

        Path(src).rename(dst)

    def join_path(self, *parts: str) -> str:
        return str(Path(*parts))

    def dirname(self, path: str) -> str:
        return str(Path(path).parent)

    def basename(self, path: str) -> str:
        return Path(path).name

    def stem(self, path: str) -> str:
        return Path(path).stem


class FTPFilesystem(FilesystemProvider):
    """FTP filesystem provider with safety for dry-run mode.

    Uses standard ftplib for maximum compatibility with PS3/older servers.
    """

    def __init__(self, host: str, port: int = 21, user: str = "", password: str = "", dry_run: bool = False):
        self.host = host
        self.port = port
        self.user = user or "anonymous"
        self.password = password or "anonymous@"
        self.dry_run = dry_run
        self._client: FTP | None = None

    def _normalize_path(self, path: str) -> str:
        """Strip FTP URL prefix if present, return just the path part."""
        if path.startswith("ftp://"):
            parsed = urlparse(path)
            return parsed.path or "/"
        return path

    async def connect(self):
        """Connect to FTP server."""
        if self._client:
            try:
                await asyncio.to_thread(self._client.voidcmd, "NOOP")
            except Exception:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None

        if self._client is None:

            def _connect():
                ftp = FTP()
                ftp.encoding = "latin-1"  # PS3 FTP servers use Latin-1 encoding
                ftp.connect(self.host, self.port, timeout=30)
                ftp.login(self.user, self.password)
                # Set to binary mode for file transfers
                ftp.voidcmd("TYPE I")
                return ftp

            self._client = await asyncio.to_thread(_connect)

    async def disconnect(self):
        """Disconnect from FTP server."""
        if self._client:

            def _disconnect():
                try:
                    self._client.quit()
                except all_errors:
                    pass  # Ignore errors during disconnect

            await asyncio.to_thread(_disconnect)
            self._client = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def exists(self, path: str) -> bool:
        await self.connect()
        path = self._normalize_path(path)

        def _exists():
            try:
                self._client.size(path)
                return True
            except Exception:
                try:
                    self._client.cwd(path)
                    return True
                except Exception:
                    return False

        return await asyncio.to_thread(_exists)

    async def is_dir(self, path: str) -> bool:
        await self.connect()
        path = self._normalize_path(path)

        def _is_dir():
            try:
                current = self._client.pwd()
                self._client.cwd(path)
                self._client.cwd(current)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_is_dir)

    async def list_dir(self, path: str) -> AsyncIterator[FileInfo]:
        await self.connect()
        path = self._normalize_path(path)

        def _list_dir():
            items = []
            # Try MLSD first (modern listing)
            try:
                for name, facts in self._client.mlsd(path):
                    if name in (".", ".."):
                        continue

                    full_path = str(PurePosixPath(path) / name)
                    items.append(
                        FileInfo(
                            path=full_path,
                            name=name,
                            size=int(facts.get("size", 0)),
                            is_dir=facts.get("type") == "dir",
                        )
                    )
                return items
            except Exception:
                # MLSD not supported, fall back to NLST
                pass

            # Fall back to NLST + SIZE for older servers
            listings = self._client.nlst(path)

            for listing in listings:
                if listing in (".", ".."):
                    continue

                # NLST might return full paths or just names
                # If it's a full path, extract the basename
                if "/" in listing:
                    full_path = listing
                    name = PurePosixPath(listing).name
                else:
                    name = listing
                    full_path = str(PurePosixPath(path) / name)

                try:
                    size = self._client.size(full_path)
                    is_dir = False
                except Exception:
                    # SIZE failed, assume it's a directory
                    size = 0
                    is_dir = True

                items.append(
                    FileInfo(
                        path=full_path,
                        name=name,
                        size=size or 0,
                        is_dir=is_dir,
                    )
                )

            return items

        items = await asyncio.to_thread(_list_dir)
        for item in items:
            yield item

    async def read_bytes(self, path: str, start: int = 0, length: int = -1) -> bytes:
        await self.connect()
        path = self._normalize_path(path)

        def _read():
            buffer = io.BytesIO()
            if start > 0:
                self._client.sendcmd(f"REST {start}")

            self._client.retrbinary(f"RETR {path}", buffer.write)
            data = buffer.getvalue()

            if length > 0:
                return data[:length]
            return data

        return await asyncio.to_thread(_read)

    async def write_bytes(self, path: str, data: bytes) -> None:
        if self.dry_run:
            return

        await self.connect()
        path = self._normalize_path(path)

        def _write():
            buffer = io.BytesIO(data)

            # Some servers (like PS3 dev_ntfs0) require CWD before STOR
            # Split path into directory and filename
            p = PurePosixPath(path)
            directory = str(p.parent)
            filename = p.name

            try:
                current_pwd = self._client.pwd()
            except Exception:
                current_pwd = "/"

            try:
                # Try to change to the target directory
                self._client.cwd(directory)
                self._client.storbinary(f"STOR {filename}", buffer)
            except all_errors:
                # If CWD failed, try full path as fallback
                buffer.seek(0)
                self._client.storbinary(f"STOR {path}", buffer)
            finally:
                try:
                    self._client.cwd(current_pwd)
                except all_errors:
                    pass

        await asyncio.to_thread(_write)

    async def copy_file(self, src: str, dst: str) -> None:
        """Copy file within FTP server (read then write)."""
        if self.dry_run:
            return

        data = await self.read_bytes(src)
        await self.write_bytes(dst, data)

    async def mkdir(self, path: str) -> None:
        if self.dry_run:
            return

        await self.connect()
        path = self._normalize_path(path)

        def _mkdir():
            try:
                self._client.mkd(path)
            except all_errors:
                # Try CWD approach if full path fails
                try:
                    p = PurePosixPath(path)
                    directory = str(p.parent)
                    name = p.name

                    try:
                        current_pwd = self._client.pwd()
                    except all_errors:
                        current_pwd = "/"

                    self._client.cwd(directory)
                    self._client.mkd(name)
                    self._client.cwd(current_pwd)
                except all_errors:
                    pass  # Ignore if already exists or really fails

        await asyncio.to_thread(_mkdir)

    async def rename(self, src: str, dst: str) -> None:
        if self.dry_run:
            return

        await self.connect()
        src = self._normalize_path(src)
        dst = self._normalize_path(dst)

        def _rename():
            self._client.rename(src, dst)

        await asyncio.to_thread(_rename)

    def join_path(self, *parts: str) -> str:
        return str(PurePosixPath(*parts))

    def dirname(self, path: str) -> str:
        return str(PurePosixPath(path).parent)

    def basename(self, path: str) -> str:
        return PurePosixPath(path).name

    def stem(self, path: str) -> str:
        return PurePosixPath(path).stem


def create_filesystem(path: str, dry_run: bool = False) -> FilesystemProvider:
    """Create appropriate filesystem provider based on path."""
    if path.startswith("ftp://"):
        parsed = urlparse(path)
        return FTPFilesystem(
            host=parsed.hostname or "localhost",
            port=parsed.port or 21,
            user=parsed.username or "",
            password=parsed.password or "",
            dry_run=dry_run,
        )
    else:
        return LocalFilesystem(dry_run=dry_run)
