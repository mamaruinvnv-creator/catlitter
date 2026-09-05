"""Command-line interface for Litter Scoop.

Commands
--------
adapt     Show the auto-detected project profile & selected adapters.
scan      Detect redundant code and print/export a report (read-only).
scoop     Scoop findings into the garbage bag (restorable), or --delete.
bags      List sealed garbage-bag batches.
restore   Restore a batch from the bag.
empty     Permanently empty the bag.
init      Write an example litterbox.toml and update .gitignore.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import EXAMPLE_CONFIG, Config
from .engine import ScanResult, scan_project
from .ignore import IgnoreMatcher
from .models import Severity
from .project import profile_project
from .reporters import render_html, render_json, render_text
from .scoop import GarbageBag, ScoopError, check_clean_git

BANNER = r"""
  _ _ _                            ___
 | (_) |_ ___ _ _    __ ___  ___  / __|___ ___  ___  _ _
 | | |  _/ -_) '_|  / _/ _ \/ _ \ \__ \/ _ / _ \/ _ \| '_|
 |_|_|\__\___|_|    \__\___/\___/ |___/\___\___/\___/|_|
            把冗余代码像猫砂一样铲进垃圾袋 · cat-litter cleanup
"""


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _resolve_path(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("非交互环境，请显式传入 --yes 确认该操作。", file=sys.stderr)
        return False
    answer = input(f"{prompt} 输入 y 继续：").strip().lower()
    return answer in ("y", "yes", "是")


def _filter_findings(result: ScanResult, args) -> list:
    findings = result.findings
    floor = Severity(args.min_severity).rank if getattr(args, "min_severity", None) else 0
    findings = [f for f in findings if f.severity.rank >= floor]
    if getattr(args, "rule", None):
        wanted = set(args.rule)
        findings = [f for f in findings if f.rule_id in wanted]
    return findings


# ----------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------
def cmd_adapt(args) -> int:
    root = _resolve_path(args.path)
    config = Config.load(root)
    matcher = IgnoreMatcher.load(root, config.exclude)
    _, profile = profile_project(root, matcher, config.disable_adapters)
    print(BANNER)
    print(f"项目根目录 : {root}")
    print(f"标志文件   : {', '.join(profile.marker_files) or '（无）'}")
    print(f"项目类型   : {', '.join(profile.project_types) or '未识别，按通用项目处理'}")
    print(f"检测框架   : {', '.join(profile.frameworks) or '（无）'}")
    print("语言构成（代码行数）:")
    for lang, lines in sorted(profile.languages.items(), key=lambda kv: -kv[1]):
        print(f"  - {lang:<12} {lines} 行")
    print(f"自动启用检测器: {', '.join(profile.adapters)}")
    print()
    print("说明：检测器会随项目构成自动增减；可在 litterbox.toml 的 [adapters] 中关闭。")
    return 0


def cmd_scan(args) -> int:
    root = _resolve_path(args.path)
    result = scan_project(root)
    result.findings = _filter_findings(result, args)

    fmt = args.report
    if fmt == "json":
        output = render_json(result)
    elif fmt == "html":
        output = render_html(result)
    else:
        output = render_text(result, color=not args.no_color)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output, encoding="utf-8")
        print(f"报告已写入 {out_path.resolve()}")
    else:
        print(output)
    for err in result.errors:
        print(f"[warn] {err}", file=sys.stderr)
    return 0 if not result.findings else 1 if args.fail_on else 0


def cmd_scoop(args) -> int:
    root = _resolve_path(args.path)
    config = Config.load(root)
    result = scan_project(root, config)
    findings = _filter_findings(result, args)
    result.findings = findings  # make the printed report match the action set

    if not args.quiet:
        print(render_text(result, color=not args.no_color, show_snippet=False))
    if not findings:
        print("没有可铲除的冗余项。")
        return 0

    mode = "直接删除（不可恢复）" if args.delete else "铲入垃圾袋（可 restore 恢复）"
    print(f"\n本次将处理 {len(findings)} 处冗余，模式：{mode}")
    if not args.dry_run and not _confirm("确认执行？", args.yes):
        print("已取消。")
        return 2

    if args.dry_run:
        print("dry-run：仅演示，不改动任何文件。")
        return 0

    if config.require_clean_git and not args.force:
        clean, message = check_clean_git(root)
        if not clean:
            print(f"[阻止] {message}", file=sys.stderr)
            return 3
        print(f"[安全检查] {message}")

    bag = GarbageBag(root, config)
    try:
        batch = bag.scoop(findings, delete=args.delete, note=args.note or "")
    except ScoopError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 4

    touched = sorted({i.original_path for i in batch.items})
    print(f"\n批次号 {batch.batch_id}：处理了 {len(batch.items)} 处，涉及 {len(touched)} 个文件")
    for path in touched:
        print(f"  - {path}")
    if args.delete:
        print("这些内容已直接删除（清单仍记录在垃圾袋目录中）。")
    else:
        print(f"原始版本已封存在 {bag.dir.relative_to(root) if bag.dir.is_relative_to(root) else bag.dir}")
        print(f"后悔了执行：litter-scoop restore {batch.batch_id}")
    return 0


def cmd_bags(args) -> int:
    root = _resolve_path(args.path)
    bag = GarbageBag(root)
    batches = bag.list_batches()
    stats = bag.stats()
    if not batches:
        print("垃圾袋是空的。")
        return 0
    print(f"垃圾袋位置: {bag.dir}")
    print(f"共 {stats['batches']} 个批次 / {stats['items']} 处冗余 / 占用 {stats['bytes']} 字节\n")
    for entry in batches:
        note = f"  # {entry['note']}" if entry.get("note") else ""
        print(f"  {entry['batch_id']}  {entry['created_at']}  {entry['items']} 处{note}")
    return 0


def cmd_restore(args) -> int:
    root = _resolve_path(args.path)
    bag = GarbageBag(root)
    if not _confirm(f"将用垃圾袋备份覆盖恢复批次 {args.batch_id} 涉及的文件，确认？", args.yes):
        print("已取消。")
        return 2
    try:
        restored = bag.restore(args.batch_id)
    except ScoopError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 4
    print(f"已恢复 {len(restored)} 个文件：")
    for path in restored:
        print(f"  + {path}")
    return 0


def cmd_empty(args) -> int:
    root = _resolve_path(args.path)
    bag = GarbageBag(root)
    stats = bag.stats()
    if stats["batches"] == 0:
        print("垃圾袋本来就是空的。")
        return 0
    target = args.batch_id or "全部批次"
    if not _confirm(f"即将永久销毁垃圾袋中的 {target}（不可恢复），确认？", args.yes):
        print("已取消。")
        return 2
    removed = bag.empty(args.batch_id)
    print(f"已永久清空 {removed} 个批次。")
    return 0


def cmd_init(args) -> int:
    root = _resolve_path(args.path)
    cfg_path = root / "litterbox.toml"
    if cfg_path.exists() and not args.force:
        print(f"{cfg_path} 已存在，加 --force 覆盖。")
    else:
        cfg_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
        print(f"已写入示例配置 {cfg_path}")
    gitignore = root / ".gitignore"
    line = ".litter-box/\n"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".litter-box" not in existing:
        with gitignore.open("a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(line)
        print(f"已把 .litter-box/ 加入 {gitignore}")
    return 0


# ----------------------------------------------------------------------
# parser
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS keeps sub-parser defaults from clobbering values already parsed
    # by the main parser (e.g. `litter-scoop -C proj scan`).
    common.add_argument("-C", "--path", default=argparse.SUPPRESS,
                        help="项目根目录，默认当前目录")
    common.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS,
                        help="关闭终端颜色")

    parser = argparse.ArgumentParser(
        prog="litter-scoop",
        parents=[common],
        description="猫砂模型：自动识别项目并检测/铲除冗余代码，可装袋、记录、恢复、丢弃。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("adapt", parents=[common], help="查看项目自动适配画像")
    p.set_defaults(func=cmd_adapt)

    p = sub.add_parser("scan", parents=[common], help="只扫描不改动，输出冗余报告")
    p.add_argument("--report", choices=["text", "json", "html"], default="text")
    p.add_argument("-o", "--output", help="报告输出文件")
    p.add_argument("--min-severity", choices=["low", "medium", "high"], default="low")
    p.add_argument("--rule", nargs="+", help="只看指定规则 id")
    p.add_argument("--fail-on", action="store_true", help="发现冗余时退出码为 1（CI 用）")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("scoop", parents=[common], help="把冗余铲入垃圾袋（默认可恢复）")
    p.add_argument("--delete", action="store_true", help="直接扔掉，不留备份")
    p.add_argument("--dry-run", action="store_true", help="只演示不落盘")
    p.add_argument("--force", action="store_true", help="跳过 git 工作区干净检查")
    p.add_argument("-y", "--yes", action="store_true", help="跳过交互确认")
    p.add_argument("--min-severity", choices=["low", "medium", "high"], default="low")
    p.add_argument("--rule", nargs="+", help="只铲除指定规则 id")
    p.add_argument("--note", default="", help="给本批次写备注")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_scoop)

    p = sub.add_parser("bags", parents=[common], help="列出垃圾袋批次")
    p.set_defaults(func=cmd_bags)

    p = sub.add_parser("restore", parents=[common], help="从垃圾袋恢复指定批次")
    p.add_argument("batch_id")
    p.add_argument("-y", "--yes", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("empty", parents=[common], help="永久清空垃圾袋")
    p.add_argument("batch_id", nargs="?", default=None)
    p.add_argument("-y", "--yes", action="store_true")
    p.set_defaults(func=cmd_empty)

    p = sub.add_parser("init", parents=[common], help="生成示例配置并更新 .gitignore")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Backfill defaults suppressed on the shared parent parser.
    if not hasattr(args, "path"):
        args.path = "."
    if not hasattr(args, "no_color"):
        args.no_color = False
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

