"""Create runtime storage before Django configures logging or opens SQLite."""

from pathlib import Path


def ensure_runtime_directories(var_dir, media_root, static_root):
    paths = [Path(var_dir), Path(static_root), Path(media_root)]
    paths += [Path(var_dir) / name for name in ("logs", "result-staging", "worker-status")]
    paths += [Path(media_root) / name for name in ("datasets", "artifacts")]
    for path in paths:
        try:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            raise RuntimeError(f"Cannot prepare runtime directory {path}: {exc.strerror}") from exc
