from pathlib import Path

from django.conf import settings


class StorageError(RuntimeError):
    pass


class StorageBackend:
    def put(self, *, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError

    def get(self, *, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, *, key: str) -> None:
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.LOCAL_STORAGE_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, *, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, *, key: str) -> bytes:
        path = self.root / key
        if not path.exists():
            raise StorageError(f"Arquivo não encontrado: {key}")
        return path.read_bytes()

    def delete(self, *, key: str) -> None:
        path = self.root / key
        if path.exists():
            path.unlink()


def get_storage() -> StorageBackend:
    backend = (settings.STORAGE_BACKEND or "local").lower()
    if backend == "local":
        return LocalStorage()
    raise StorageError(f"Storage backend não suportado ainda: {backend}")
