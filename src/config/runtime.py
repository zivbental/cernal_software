"""Create runtime storage before Django configures logging or opens SQLite."""

from pathlib import Path


def reject_symlink_path(path):
    """Managed storage must be literal paths, including every existing ancestor."""
    path = Path(path).expanduser().absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise RuntimeError(
                f"Managed path contains a symlink: {component}; use its literal path"
            )


def ensure_runtime_directories(var_dir, media_root, static_root):
    paths = [Path(var_dir), Path(static_root), Path(media_root)]
    paths += [Path(var_dir) / name for name in ("logs", "result-staging", "worker-status")]
    paths += [Path(media_root) / name for name in ("datasets", "artifacts")]
    # Check the entire set before creating any directory; include dangling database links.
    for path in [*paths, Path(var_dir) / "cernal.db", Path(var_dir) / "logs/cernal.log"]:
        reject_symlink_path(path)
    for path in paths:
        try:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            raise RuntimeError(f"Cannot prepare runtime directory {path}: {exc.strerror}") from exc
