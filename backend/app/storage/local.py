"""Filesystem storage. The default, and the only one a fresh clone needs.

Not suitable for the deployed API: render.yaml declares no ``disk:``, so the
filesystem is ephemeral there. That is a known, documented state — see
docs/adr/0021-pdf-blob-storage.md.
"""

from pathlib import Path

from fastapi.concurrency import run_in_threadpool

from app.storage import StorageObjectNotFound


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser()

    def _resolve(self, key: str) -> Path:
        """Map a key to a path, refusing anything that escapes the root.

        Keys are server-generated from a UUID and a hex digest, so this should
        be unreachable — which is exactly why it is cheap to assert. The day
        something starts deriving a key from a filename, this is the line that
        decides whether that becomes a path traversal.
        """
        root = self._root.resolve()
        path = (root / key).resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        return path

    async def put(self, key: str, data: bytes, media_type: str) -> None:
        # media_type is unused here: a filesystem has nowhere to record it, and
        # the row already carries it. It stays in the signature because S3 does.
        path = self._resolve(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write beside, then rename: a crash mid-write must not leave a
            # truncated object under a key the digest says is complete.
            tmp = path.with_name(f"{path.name}.tmp")
            tmp.write_bytes(data)
            tmp.replace(path)

        await run_in_threadpool(_write)

    async def get(self, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return await run_in_threadpool(path.read_bytes)
        except FileNotFoundError as exc:
            raise StorageObjectNotFound(key) from exc

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        # Idempotent: deleting an object that is already gone is the caller
        # getting what they asked for, not an error.
        await run_in_threadpool(lambda: path.unlink(missing_ok=True))

    async def signed_url(self, key: str, expires_in: int) -> str | None:
        """None — there is no URL a browser could fetch. Stream it instead."""
        return None
