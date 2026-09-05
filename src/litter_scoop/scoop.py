"""The cat-litter bag: scoop waste in, restore it, or empty the bag forever.

Safety model
------------
Before *any* source file is modified or deleted, its **pristine full copy** is
sealed inside the bag (``.litter-box/files/<batch_id>/...``) together with a
JSON manifest. Line-level removals never destroy information: restoring a bag
overwrites files byte-for-byte with their pre-scoop state. Only ``empty`` is
irreversible.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .config import Config
from .models import BagBatch, Finding, StashedItem, sha256_bytes, sha256_file


class ScoopError(RuntimeError):
    pass


def check_clean_git(root: Path) -> tuple[bool, str]:
    """Return (clean, message). Non-git directories count as clean."""
    if not (root / ".git").exists():
        return True, "非 git 仓库，跳过工作区检查"
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"无法执行 git status: {exc}"
    if proc.returncode != 0:
        return False, proc.stderr.strip()
    if proc.stdout.strip():
        return False, "git 工作区存在未提交改动，请先 commit/stash，或使用 --force 强制执行"
    return True, "git 工作区干净"


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent 1-based inclusive line ranges."""
    if not ranges:
        return []
    ordered = sorted(ranges)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def remove_line_ranges(source: str, ranges: list[tuple[int, int]]) -> str:
    """Remove 1-based inclusive line ranges, preserving newline style."""
    keepends = source.splitlines(keepends=True)
    # splitlines loses a trailing non-newlined line? It keeps it as last element.
    drop = set()
    for start, end in merge_ranges(ranges):
        for ln in range(start, end + 1):
            drop.add(ln - 1)
    kept = [line for idx, line in enumerate(keepends) if idx not in drop]
    return "".join(kept)


class GarbageBag:
    def __init__(self, root: Path, config: Config | None = None) -> None:
        self.root = root.resolve()
        self.config = config or Config.load(self.root)
        self.dir = self.root / self.config.bag_dir
        self.files_dir = self.dir / "files"
        self.manifest_dir = self.dir / "manifests"
        self.index_path = self.dir / "index.json"

    # ------------------------------------------------------------------
    def ensure_dirs(self) -> None:
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)

    def _new_batch_id(self) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{secrets.token_hex(2)}"

    # ------------------------------------------------------------------
    def scoop(
        self,
        findings: list[Finding],
        *,
        delete: bool = False,
        note: str = "",
    ) -> BagBatch:
        """Move findings into the bag (or delete them outright).

        Findings touching the same file are coalesced into one edit.
        """
        if not findings:
            raise ScoopError("没有可铲除的冗余项")

        self.ensure_dirs()
        batch_id = self._new_batch_id()
        batch = BagBatch(
            batch_id=batch_id,
            created_at=datetime.now().isoformat(timespec="seconds"),
            root=str(self.root),
            note=note,
        )

        # Group findings by file.
        per_file: dict[str, list[Finding]] = {}
        for finding in findings:
            per_file.setdefault(finding.path, []).append(finding)

        for rel, file_findings in sorted(per_file.items()):
            src = self.root / rel
            if not src.exists():
                continue
            original_bytes = src.read_bytes()
            original_hash = sha256_bytes(original_bytes)
            stored_rel = Path(batch_id) / Path(rel)
            stored = self.files_dir / stored_rel
            stored.parent.mkdir(parents=True, exist_ok=True)

            whole_file = any(f.whole_file for f in file_findings)
            if whole_file:
                primary = next(f for f in file_findings if f.whole_file)
                if delete:
                    # "扔掉": no backup kept, manifest is the only record.
                    src.unlink()
                    stored_path = ""
                    action = "delete-file"
                else:
                    # "装袋": seal a pristine copy, then remove from source.
                    shutil.copy2(src, stored)
                    src.unlink()
                    stored_path = Path("files") / stored_rel
                    action = "bag-file"
                batch.items.append(
                    StashedItem(
                        finding=primary, original_path=rel,
                        stored_path=stored_path,
                        original_sha256=original_hash, action=action,
                    )
                )
                continue

            ranges = [(f.start_line, max(f.end_line, f.start_line))
                      for f in file_findings if f.start_line > 0]
            ranges = merge_ranges(ranges)
            source_text = original_bytes.decode("utf-8", errors="replace")
            new_text = remove_line_ranges(source_text, ranges)

            if delete:
                src.write_text(new_text, encoding="utf-8", newline="")
                stored_path = ""
                action = "delete-lines"
            else:
                shutil.copy2(src, stored)  # seal pristine copy
                src.write_text(new_text, encoding="utf-8", newline="")
                stored_path = Path("files") / stored_rel
                action = "line-edit"

            # Record one item per finding (all share the same stored backup).
            for finding in file_findings:
                batch.items.append(
                    StashedItem(
                        finding=finding, original_path=rel,
                        stored_path=stored_path,
                        original_sha256=original_hash, action=action,
                    )
                )

        self._write_manifest(batch)
        self._rebuild_index()
        return batch

    # ------------------------------------------------------------------
    def _write_manifest(self, batch: BagBatch) -> None:
        target = self.manifest_dir / f"{batch.batch_id}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(batch.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, target)

    def _rebuild_index(self) -> None:
        entries = []
        for manifest in sorted(self.manifest_dir.glob("*.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            entries.append({
                "batch_id": data["batch_id"],
                "created_at": data["created_at"],
                "items": len(data.get("items", [])),
                "note": data.get("note", ""),
            })
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.index_path)

    def list_batches(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def load_batch(self, batch_id: str) -> BagBatch:
        target = self.manifest_dir / f"{batch_id}.json"
        if not target.exists():
            # Allow prefix match (timestamp without random suffix).
            matches = list(self.manifest_dir.glob(f"{batch_id}*.json"))
            if len(matches) == 1:
                target = matches[0]
            elif not matches:
                raise ScoopError(f"垃圾袋中找不到批次 {batch_id}")
            else:
                raise ScoopError(f"批次前缀 {batch_id} 匹配到多个结果，请写全")
        return BagBatch.from_dict(json.loads(target.read_text(encoding="utf-8")))

    # ------------------------------------------------------------------
    def restore(self, batch_id: str) -> list[str]:
        """Restore every file touched by a batch to its pre-scoop state."""
        batch = self.load_batch(batch_id)
        irreversible = {i.original_path for i in batch.items
                        if i.action.startswith("delete-") or not i.stored_path}
        if irreversible:
            raise ScoopError(
                "该批次使用了 --delete（直接扔掉）模式，没有备份，无法恢复："
                + ", ".join(sorted(irreversible))
            )
        restored: list[str] = []
        seen_files: set[str] = set()
        for item in batch.items:
            if item.original_path in seen_files:
                continue
            seen_files.add(item.original_path)
            backup = self.dir / item.stored_path
            if not backup.exists():
                raise ScoopError(f"备份丢失，无法恢复 {item.original_path}")
            target = self.root / item.original_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
            # Verify byte identity.
            if sha256_file(target) != item.original_sha256:
                raise ScoopError(f"恢复后校验失败 {item.original_path}")
            restored.append(item.original_path)
        # A restored batch is consumed: remove its files & manifest.
        shutil.rmtree(self.files_dir / batch.batch_id, ignore_errors=True)
        (self.manifest_dir / f"{batch.batch_id}.json").unlink(missing_ok=True)
        self._rebuild_index()
        return restored

    def empty(self, batch_id: str | None = None) -> int:
        """Permanently delete bag contents. Returns number of batches removed."""
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
        items = sum(b["items"] for b in batches)
        size = 0
        if self.dir.exists():
            for dirpath, _, filenames in os.walk(self.dir):
                for name in filenames:
                    try:
                        size += (Path(dirpath) / name).stat().st_size
                    except OSError:
                        pass
        return {"batches": len(batches), "items": items, "bytes": size}

