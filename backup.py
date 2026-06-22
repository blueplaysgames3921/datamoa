"""
Backup Service — creates timestamped backups of all DataMoA data.
Backups go to ~/DataMoA Backups/ (visible, accessible by user).
User controls frequency. Backups include: config, keys, memory, audit, queue.
"""

import asyncio
import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# User-visible backup folder in their home directory
BACKUP_ROOT = Path.home() / "DataMoA Backups"


def get_backup_root() -> Path:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    return BACKUP_ROOT


def create_backup(data_dir: Path, label: str = "") -> dict:
    """
    Create a timestamped backup ZIP of all DataMoA data.
    Returns info about the created backup.
    """
    backup_root = get_backup_root()
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    tag = f"_{label}" if label else ""
    backup_name = f"datamoa_backup_{ts}{tag}.zip"
    backup_path = backup_root / backup_name

    included = []
    errors = []

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Files and dirs to back up
        targets = [
            data_dir / "config.json",
            data_dir / "keys.json",           # encrypted at rest (see core/config/settings.py)
            data_dir / ".keys.key",           # decryption key for keys.json — MUST travel with it,
                                               # or keys.json is unrecoverable after restore
            data_dir / "google_tokens.json",
            data_dir / "memory",
            data_dir / "audit",
            data_dir / "queue",
        ]

        for target in targets:
            if not target.exists():
                continue
            try:
                if target.is_file():
                    zf.write(target, target.name)
                    included.append(target.name)
                elif target.is_dir():
                    for child in target.rglob("*"):
                        if child.is_file():
                            arcname = str(child.relative_to(data_dir))
                            zf.write(child, arcname)
                            included.append(arcname)
            except Exception as e:
                errors.append(f"{target.name}: {str(e)}")

        # Write backup manifest
        manifest = {
            "created_at": datetime.now().isoformat(),
            "label": label,
            "data_dir": str(data_dir),
            "files_included": included,
            "errors": errors,
        }
        zf.writestr("_manifest.json", json.dumps(manifest, indent=2))

    size_mb = round(backup_path.stat().st_size / 1024 / 1024, 2)

    result = {
        "path": str(backup_path),
        "name": backup_name,
        "size_mb": size_mb,
        "created_at": datetime.now().isoformat(),
        "files_count": len(included),
        "errors": errors,
        "folder": str(backup_root),
    }

    logger.info(f"Backup created: {backup_name} ({size_mb}MB, {len(included)} files)")
    return result


def list_backups() -> list[dict]:
    """List all available backups sorted newest first."""
    backup_root = get_backup_root()
    backups = []

    for f in sorted(backup_root.glob("datamoa_backup_*.zip"), reverse=True):
        try:
            stat = f.stat()
            # Try to read manifest
            manifest = {}
            try:
                with zipfile.ZipFile(f) as zf:
                    if "_manifest.json" in zf.namelist():
                        manifest = json.loads(zf.read("_manifest.json"))
            except Exception:
                pass

            backups.append({
                "name": f.name,
                "path": str(f),
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": manifest.get("created_at", datetime.fromtimestamp(stat.st_mtime).isoformat()),
                "label": manifest.get("label", ""),
                "files_count": len(manifest.get("files_included", [])),
                "folder": str(backup_root),
            })
        except Exception:
            continue

    return backups


def delete_backup(backup_name: str) -> bool:
    """Delete a specific backup file."""
    backup_root = get_backup_root()
    target = backup_root / backup_name
    if target.exists() and target.parent == backup_root:
        target.unlink()
        return True
    return False


def restore_backup(backup_name: str, data_dir: Path) -> dict:
    """
    Restore a backup to the data directory.
    Returns success/error info.
    """
    backup_root = get_backup_root()
    backup_path = backup_root / backup_name

    if not backup_path.exists():
        return {"success": False, "error": f"Backup not found: {backup_name}"}

    # Create a safety backup of current state before restoring
    safety = create_backup(data_dir, label="pre_restore")

    try:
        with zipfile.ZipFile(backup_path) as zf:
            members = [m for m in zf.namelist() if m != "_manifest.json"]
            data_dir_resolved = data_dir.resolve()
            for member in members:
                # Zip-slip protection: a crafted/corrupted backup could contain
                # entries like "../../etc/cron.d/evil" or an absolute path,
                # which would resolve outside data_dir. Reject any member
                # whose resolved path escapes data_dir before writing it.
                target = (data_dir / member).resolve()
                if data_dir_resolved not in target.parents and target != data_dir_resolved:
                    raise ValueError(f"Refusing to restore unsafe path in backup: {member!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())

        return {
            "success": True,
            "restored_files": len(members),
            "safety_backup": safety["name"],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class BackupScheduler:
    """Background task that runs periodic backups."""

    def __init__(self, data_dir: Path, interval_hours: float = 24.0):
        self.data_dir = data_dir
        self.interval_hours = interval_hours
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def set_interval(self, hours: float):
        """Update interval and restart scheduler."""
        self.interval_hours = max(0.25, hours)  # minimum 15 minutes
        if self._running:
            self.stop()
            self.start()

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _run(self):
        """Run backup on schedule."""
        while self._running:
            try:
                interval_secs = self.interval_hours * 3600
                await asyncio.sleep(interval_secs)
                if self._running:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, create_backup, self.data_dir, "scheduled")
                    logger.info("Scheduled backup completed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduled backup failed: {e}")
                await asyncio.sleep(60)  # retry after 1 minute on error
