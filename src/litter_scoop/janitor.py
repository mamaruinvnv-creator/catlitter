"""System janitor — scoop *computer* junk with the same cat-litter safety model.

The code cleaner handles redundant source files; this module handles the junk
the operating system leaves behind: temp dirs, package-manager caches, thumbnail
caches and (opt-in, delete-only) the recycle bin / trash.

Safety model (identical philosophy to :mod:`litter_scoop.scoop`):

* **whitelist only** — we ever walk a fixed set of well-known junk locations;
* **age gate** — files younger than ``max_age_days`` are never touched, so files
  currently in use are left alone;
* **bag by default** — junk is *moved* into a global bag under the user's home
  directory (``~/.catlitter-janitor``) with a manifest, and can be restored
  byte-for-byte; only ``--delete`` removes it outright;
* **no symlink escape** — symlinks/junctions are never followed, and every file
  is verified to physically live inside its whitelisted root;
* **risky targets** (recycle bin / trash) are skipped unless explicitly
  requested and only work in delete mode.
"""

from __future__ import annotations

import dataclasses
import json
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .models import sha256_file

#: Environment variable overriding the global janitor bag location.
BAG_ENV = "CATLITTER_JANITOR_BAG"
DEFAULT_BAG_DIRNAME = ".catlitter-janitor"
SCHEDULE_TASK_NAME = "CatLitterJanitor"


# ----------------------------------------------------------------------
# data models
# ----------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class JanitorTarget:
    """One whitelisted junk location."""

    category: str
    label: str
    path: Path
    #: Recycle-bin/trash style targets: opt-in and delete-only.
    risky: bool = False
    #: When set, only filenames matching any suffix/name are considered.
    name_globs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WasteFile:
    category: str
    label: str
    path: Path
    size: int
    mtime: float

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "label": self.label,
            "path": str(self.path),
            "size": self.size,
            "mtime": self.mtime,
        }


@dataclass(slots=True)
class JanitorScan:
    files: list[WasteFile] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    missing_targets: list[str] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def total_files(self) -> int:
        return len(self.files)

    def by_category(self) -> dict[str, list[WasteFile]]:
        grouped: dict[str, list[WasteFile]] = {}
        for item in self.files:
            grouped.setdefault(item.category, []).append(item)
        return grouped

    def to_dict(self) -> dict:
        return {
            "total_files": self.total_files,
            "total_bytes": self.total_bytes,
            "files": [f.to_dict() for f in self.files],
            "skipped": [{"path": p, "reason": r} for p, r in self.skipped],
            "missing_targets": self.missing_targets,
        }


# ----------------------------------------------------------------------
# target discovery
# ----------------------------------------------------------------------
def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def discover_targets(
    *,
    extra_paths: Iterable[str | Path] = (),
    include_risky: bool = False,
    only: Iterable[str] | None = None,
    include_defaults: bool = True,
) -> list[JanitorTarget]:
    """Return the whitelisted junk locations that exist on this machine.

    ``include_defaults=False`` skips the platform whitelist and keeps only
    ``extra_paths`` (used to scope a run to explicitly named directories).
    """
    targets: list[JanitorTarget] = []
    home = Path.home()

    if include_defaults and sys.platform.startswith("win"):
        local_app = _env_path("LOCALAPPDATA") or (home / "AppData" / "Local")
        win_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        targets += [
            JanitorTarget("user-temp", "用户临时文件",
                          _env_path("TEMP") or (local_app / "Temp")),
            JanitorTarget("windows-temp", "Windows 临时目录",
                          win_dir / "Temp"),
            JanitorTarget("pip-cache", "pip 缓存", local_app / "pip" / "cache"),
            JanitorTarget("npm-cache", "npm 缓存", local_app / "npm-cache"),
            JanitorTarget("yarn-cache", "Yarn 缓存",
                          local_app / "Yarn" / "Cache"),
            JanitorTarget("thumbcache", "缩略图缓存",
                          local_app / "Microsoft" / "Windows" / "Explorer",
                          name_globs=("thumbcache_*.db", "iconcache_*.db")),
            JanitorTarget("recycle-bin", "回收站", Path(r"C:\$Recycle.Bin"),
                          risky=True),
        ]
    elif include_defaults and sys.platform == "darwin":
        targets += [
            JanitorTarget("user-cache", "用户缓存 ~/Library/Caches",
                          home / "Library" / "Caches"),
            JanitorTarget("npm-cache", "npm 缓存", home / ".npm" / "_cacache"),
            JanitorTarget("pip-cache", "pip 缓存",
                          home / "Library" / "Caches" / "pip"),
            JanitorTarget("trash", "废纸篓", home / ".Trash", risky=True),
        ]
    elif include_defaults:
        targets += [
            JanitorTarget("user-cache", "用户缓存 ~/.cache", home / ".cache"),
            JanitorTarget("npm-cache", "npm 缓存", home / ".npm" / "_cacache"),
            JanitorTarget("tmp-files", "系统临时目录 /tmp", Path("/tmp")),
            JanitorTarget("trash", "回收站",
                          home / ".local" / "share" / "Trash", risky=True),
        ]

    for idx, extra in enumerate(extra_paths):
        p = Path(extra).expanduser()
        targets.append(JanitorTarget(f"custom-{idx}", f"自定义路径 {p}", p))

    if not include_risky:
        targets = [t for t in targets if not t.risky]
    if only:
        wanted = set(only)
        targets = [t for t in targets if t.category in wanted]
    return targets


# ----------------------------------------------------------------------
# scanning
# ----------------------------------------------------------------------
def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def iter_target_files(
    target: JanitorTarget,
    *,
    cutoff: float | None,
    scan: JanitorScan,
) -> Iterable[WasteFile]:
    """Walk one target root, enforcing age gate and symlink-escape protection."""
    root = target.path
    if not root.exists():
        scan.missing_targets.append(target.category)
        return

    try:
        real_root = root.resolve(strict=True)
    except OSError as exc:
        scan.skipped.append((str(root), f"无法解析路径: {exc}"))
        return

    # os.walk with followlinks=False already refuses to descend into symlinked
    # directories; we additionally verify each file physically stays in-root.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Drop symlinked sub-directories explicitly (junction points on Windows).
        dirnames[:] = [
            d for d in dirnames
            if not (Path(dirpath, d).is_symlink())
        ]
        for name in filenames:
            fp = Path(dirpath, name)
            try:
                if target.name_globs and not any(
                    fp.match(pattern) for pattern in target.name_globs
                ):
                    continue
                if fp.is_symlink():
                    scan.skipped.append((str(fp), "符号链接，跳过"))
                    continue
                st = fp.stat()  # follows the link, but links were filtered above
                real = fp.resolve(strict=False)
                if not _is_within(real, real_root):
                    scan.skipped.append((str(fp), "解析后越出白名单根目录，跳过"))
                    continue
                if cutoff is not None and st.st_mtime >= cutoff:
                    continue  # too young — likely in active use
                # On POSIX /tmp only clean files owned by the current user.
                if target.category == "tmp-files" and hasattr(os, "getuid"):
                    if st.st_uid != os.getuid():
                        continue
                yield WasteFile(
                    category=target.category, label=target.label,
                    path=fp, size=st.st_size, mtime=st.st_mtime,
                )
            except (OSError, ValueError) as exc:
                scan.skipped.append((str(fp), f"读取失败: {exc}"))


def scan_system(
    *,
    max_age_days: float = 7,
    extra_paths: Iterable[str] = (),
    include_risky: bool = False,
    only: Iterable[str] | None = None,
    targets: list[JanitorTarget] | None = None,
) -> JanitorScan:
    """Scan whitelisted junk locations. Pure read-only."""
    scan = JanitorScan()
    cutoff = (
        (datetime.now() - timedelta(days=max_age_days)).timestamp()
        if max_age_days and max_age_days > 0 else None
    )
    if targets is None:
        targets = discover_targets(
            extra_paths=extra_paths, include_risky=include_risky, only=only
        )
    for target in targets:
        scan.files.extend(
            iter_target_files(target, cutoff=cutoff, scan=scan)
        )
    return scan


# ----------------------------------------------------------------------
# bagging (global, project-independent)
# ----------------------------------------------------------------------
def default_bag_dir() -> Path:
    override = os.environ.get(BAG_ENV)
    return Path(override).expanduser() if override else (Path.home() / DEFAULT_BAG_DIRNAME)


def _flatten_absolute(path: Path) -> Path:
    """Turn an absolute junk path into a safe in-bag relative path.

    Windows: ``C:\\\\Users\\\\me\\\\Temp\\\\a.tmp`` -> ``drive-c/Users/me/Temp/a.tmp``
    POSIX:   ``/tmp/a.tmp``                        -> ``tmp/a.tmp``

    The drive letter is rewritten to a plain ``drive-x`` segment on purpose:
    a path containing ``C:`` is treated as drive-rooted by :mod:`pathlib`,
    which would break ``bag_dir / stored_rel`` joins.
    """
    parts = list(path.parts)
    if not parts:
        return Path("_")
    if sys.platform.startswith("win"):
        # On Windows parts[0] is the anchor, e.g. "C:\\" (not just "C:").
        rest = [p for p in parts if p != path.anchor]
        drive = path.drive.rstrip(":").lower()
        if drive:
            return Path(f"drive-{drive}", *rest)
        return Path(*rest) if rest else Path("_")
    # POSIX absolute: parts[0] == "/"
    return Path(*[p for p in parts if p not in ("/", "\\")])


@dataclass(slots=True)
class JanitorBatch:
    batch_id: str
    created_at: str
    mode: str                       # "bag" | "delete"
    items: list[dict] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class JanitorBag:
    """Global garbage bag for system junk (defaults to ``~/.catlitter-janitor``)."""

    def __init__(self, bag_dir: Path | None = None) -> None:
        self.dir = (bag_dir or default_bag_dir()).resolve()
        self.files_dir = self.dir / "files"
        self.manifest_dir = self.dir / "manifests"
        self.index_path = self.dir / "index.json"

    def ensure_dirs(self) -> None:
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _new_batch_id() -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{secrets.token_hex(2)}"

    # ------------------------------------------------------------------
    def scoop(
        self,
        files: list[WasteFile],
        *,
        delete: bool = False,
        note: str = "",
        risky_cleared: list[WasteFile] | None = None,
    ) -> JanitorBatch:
        """Move junk into the bag (restorable) or delete it outright."""
        if not files:
            raise ValueError("没有可清理的垃圾文件")
        self.ensure_dirs()
        batch = JanitorBatch(
            batch_id=self._new_batch_id(),
            created_at=datetime.now().isoformat(timespec="seconds"),
            mode="delete" if delete else "bag",
            note=note,
        )
        cleared_risky = {id(w) for w in (risky_cleared or [])}

        for waste in files:
            src = waste.path
            if not src.exists():
                continue
            record = {
                "category": waste.category,
                "label": waste.label,
                "original_path": str(src),
                "stored_path": "",
                "sha256": "",
                "size": waste.size,
            }
            try:
                if waste.category in ("recycle-bin", "trash"):
                    if id(waste) not in cleared_risky and not delete:
                        continue  # risky targets are delete-only; silently skip here
                    src.unlink()
                    record["action"] = "delete-file"
                elif delete:
                    src.unlink()
                    record["action"] = "delete-file"
                else:
                    digest = sha256_file(src)
                    stored_rel = Path(batch.batch_id) / _flatten_absolute(src.resolve())
                    stored = self.files_dir / stored_rel
                    stored.parent.mkdir(parents=True, exist_ok=True)
                    if stored.exists():  # never overwrite an existing backup
                        stored = stored.with_name(
                            stored.stem + f"-{secrets.token_hex(2)}" + stored.suffix
                        )
                    shutil.move(str(src), str(stored))
                    record["stored_path"] = str(Path("files") / stored_rel)
                    record["sha256"] = digest
                    record["action"] = "bag-file"
            except OSError as exc:
                record["action"] = "error"
                record["error"] = str(exc)
            batch.items.append(record)

        self._write_manifest(batch)
        self._rebuild_index()
        return batch

    # ------------------------------------------------------------------
    def _write_manifest(self, batch: JanitorBatch) -> None:
        target = self.manifest_dir / f"{batch.batch_id}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(batch.to_dict(), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, target)

    def _rebuild_index(self) -> None:
        entries = []
        if self.manifest_dir.exists():
            for manifest in sorted(self.manifest_dir.glob("*.json")):
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                entries.append({
                    "batch_id": data["batch_id"],
                    "created_at": data["created_at"],
                    "mode": data.get("mode", "bag"),
                    "items": len(data.get("items", [])),
                    "bytes": sum(i.get("size", 0) for i in data.get("items", [])),
                    "note": data.get("note", ""),
                })
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, self.index_path)

    def list_batches(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def load_batch(self, batch_id: str) -> JanitorBatch:
        target = self.manifest_dir / f"{batch_id}.json"
        if not target.exists():
            matches = list(self.manifest_dir.glob(f"{batch_id}*.json"))
            if len(matches) == 1:
                target = matches[0]
            elif not matches:
                raise FileNotFoundError(f"垃圾袋中找不到批次 {batch_id}")
            else:
                raise ValueError(f"批次前缀 {batch_id} 匹配到多个结果，请写全")
        data = json.loads(target.read_text(encoding="utf-8"))
        return JanitorBatch(
            batch_id=data["batch_id"], created_at=data["created_at"],
            mode=data.get("mode", "bag"), items=data.get("items", []),
            note=data.get("note", ""),
        )

    # ------------------------------------------------------------------
    def restore(self, batch_id: str) -> list[str]:
        """Move every bagged file back to its original location."""
        batch = self.load_batch(batch_id)
        if batch.mode == "delete":
            raise ValueError("该批次为直接删除模式，没有备份，无法恢复")
        restored: list[str] = []
        for item in batch.items:
            if item.get("action") != "bag-file":
                continue
            original = Path(item["original_path"])
            backup = self.dir / item["stored_path"]
            if not backup.exists():
                raise FileNotFoundError(f"备份丢失，无法恢复 {original}")
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(backup), str(original))
            if item.get("sha256") and sha256_file(original) != item["sha256"]:
                raise ValueError(f"恢复后校验失败 {original}")
            restored.append(str(original))
        shutil.rmtree(self.files_dir / batch.batch_id, ignore_errors=True)
        (self.manifest_dir / f"{batch.batch_id}.json").unlink(missing_ok=True)
        self._rebuild_index()
        return restored

    def empty(self, batch_id: str | None = None) -> int:
        """Permanently destroy bag contents. Returns batches removed."""
        if batch_id:
            batch = self.load_batch(batch_id)
            shutil.rmtree(self.files_dir / batch.batch_id, ignore_errors=True)
            (self.manifest_dir / f"{batch.batch_id}.json").unlink(missing_ok=True)
            self._rebuild_index()
            return 1
        if not self.dir.exists():
            return 0
        count = len(list(self.manifest_dir.glob("*.json")))
        shutil.rmtree(self.dir)
        return count

    def stats(self) -> dict:
        batches = self.list_batches()
        items = sum(b.get("items", 0) for b in batches)
        size = 0
        if self.dir.exists():
            for dirpath, _, filenames in os.walk(self.dir):
                for name in filenames:
                    try:
                        size += (Path(dirpath) / name).stat().st_size
                    except OSError:
                        pass
        return {"batches": len(batches), "items": items, "bytes": size}


# ----------------------------------------------------------------------
# recycle bin / trash special handling (delete-only, risky)
# ----------------------------------------------------------------------
def empty_recycle_bin() -> tuple[bool, str]:
    """Empty the OS recycle bin / trash using the native, official mechanism."""
    try:
        if sys.platform.startswith("win"):
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                capture_output=True, text=True, timeout=120,
            )
            return proc.returncode == 0, proc.stderr.strip()
        if sys.platform == "darwin":
            trash = Path.home() / ".Trash"
            if trash.exists():
                for child in trash.iterdir():
                    if child.is_symlink():
                        child.unlink()
                    elif child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
            return True, ""
        # Linux: prefer gio, fall back to removing the Trash folder contents.
        try:
            proc = subprocess.run(["gio", "trash", "--empty"],
                                  capture_output=True, text=True, timeout=60)
            if proc.returncode == 0:
                return True, ""
        except FileNotFoundError:
            pass
        trash = Path.home() / ".local" / "share" / "Trash"
        for sub in ("files", "info"):
            shutil.rmtree(trash / sub, ignore_errors=True)
            (trash / sub).mkdir(parents=True, exist_ok=True)
        return True, ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


# ----------------------------------------------------------------------
# scheduled cleanup
# ----------------------------------------------------------------------
def _runner_command() -> str:
    """Command the scheduler runs: `python -m litter_scoop janitor ...`."""
    return f'"{sys.executable}" -m litter_scoop janitor scoop -y --delete'


def render_schedule(
    *,
    freq: str = "weekly",
    at: str = "10:00",
    day: str = "SUN",
) -> str:
    """Return the native scheduler command/cron line, without installing it."""
    runner = _runner_command()
    if sys.platform.startswith("win"):
        hour, minute = at.split(":")
        sc = {"daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY"}[freq]
        parts = [
            "schtasks", "/Create", "/F", "/TN", f'"{SCHEDULE_TASK_NAME}"',
            "/SC", sc, "/ST", f"{int(hour):02d}:{minute}",
        ]
        if freq == "weekly":
            parts += ["/D", day.upper()[:3]]
        log = str(default_bag_dir() / "janitor.log")
        parts += ["/TR", f'"cmd /c {runner} >> \\"{log}\\" 2>&1"']
        return " ".join(parts)
    # cron: minute hour dom month dow
    hour, minute = at.split(":")
    dow = {"SUN": "0", "MON": "1", "TUE": "2", "WED": "3",
           "THU": "4", "FRI": "5", "SAT": "6"}.get(day.upper()[:3], "0")
    if freq == "daily":
        time_field = f"{int(minute)} {int(hour)} * * *"
    elif freq == "monthly":
        time_field = f"{int(minute)} {int(hour)} 1 * *"
    else:
        time_field = f"{int(minute)} {int(hour)} * * {dow}"
    return f"{time_field} {runner} # {SCHEDULE_TASK_NAME}"


def install_schedule(*, freq: str = "weekly", at: str = "10:00",
                     day: str = "SUN") -> str:
    """Register the scheduled task. Returns the rendered command/cron line."""
    line = render_schedule(freq=freq, at=at, day=day)
    if sys.platform.startswith("win"):
        proc = subprocess.run(line, shell=True, capture_output=True,
                              text=True, timeout=60)
        if proc.returncode != 0:
            raise OSError(proc.stderr.strip() or proc.stdout.strip() or "schtasks 失败")
        return line
    # POSIX: append the marker line to the user crontab (idempotent).
    proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = proc.stdout if proc.returncode == 0 else ""
    kept = [ln for ln in existing.splitlines() if SCHEDULE_TASK_NAME not in ln]
    kept.append(line)
    new_cron = "\n".join(kept) + "\n"
    install = subprocess.run(["crontab", "-"], input=new_cron,
                             capture_output=True, text=True)
    if install.returncode != 0:
        raise OSError(install.stderr.strip() or "crontab 安装失败")
    return line


def uninstall_schedule() -> bool:
    """Remove the scheduled task."""
    if sys.platform.startswith("win"):
        proc = subprocess.run(
            ["schtasks", "/Delete", "/TN", SCHEDULE_TASK_NAME, "/F"],
            capture_output=True, text=True, timeout=60,
        )
        return proc.returncode == 0
    proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if proc.returncode != 0:
        return False
    kept = "\n".join(ln for ln in proc.stdout.splitlines()
                     if SCHEDULE_TASK_NAME not in ln)
    subprocess.run(["crontab", "-"], input=kept + "\n",
                   capture_output=True, text=True)
    return True


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024 or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return f"{num:.1f} TB"
