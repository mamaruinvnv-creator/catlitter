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
janitor   Scoop *computer* junk (temp/cache/trash) on a schedule, same model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import EXAMPLE_CONFIG, Config
from .engine import ScanResult, scan_project
from .ignore import IgnoreMatcher
from .janitor import (
    JanitorBag,
    default_bag_dir,
    discover_targets,
    empty_recycle_bin,
    human_size,
    install_schedule,
    render_schedule,
    scan_system,
    uninstall_schedule,
)
from .models import Severity
from .project import profile_project
from .reporters import render_html, render_json, render_text
from .scoop import GarbageBag, ScoopError, check_clean_git

BANNER = r"""
  _ _ _                            ___
 | (_) |_ ___ _ _    __ ___  ___  / __|___ ___  ___  _ _
 | | |  _/ -_) '_|  / _/ _ \/ _ \ \__ \/ _ / _ \/ _ \| '_|
 |_|_|\__\___|_|    \__\___/\___/ |___/\___\___/\___/|_|
        猫砂 CatLitter · 把冗余代码铲进垃圾袋，可记录、可复原、可丢弃
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
# janitor (system junk) commands
# ----------------------------------------------------------------------
RISKY_CATEGORIES = {"recycle-bin", "trash"}


def _janitor_targets(args):
    return discover_targets(
        extra_paths=getattr(args, "extra_path", []) or [],
        include_risky=getattr(args, "include_risky", False),
        only=getattr(args, "category", None),
        include_defaults=not getattr(args, "no_default", False),
    )


def _print_janitor_scan(scan) -> None:
    grouped = scan.by_category()
    if not grouped:
        print("没有发现符合条件的垃圾文件（默认只清理 7 天前的旧文件）。")
    label_of = {c: items[0].label for c, items in grouped.items()}
    print(f"{'类别':<16}{'说明':<26}{'文件数':>8}{'占用':>12}")
    print("-" * 64)
    for category in sorted(grouped):
        items = grouped[category]
        size = sum(i.size for i in items)
        print(f"{category:<16}{label_of[category]:<26}{len(items):>8}{human_size(size):>12}")
    print("-" * 64)
    print(f"{'合计':<16}{'':<26}{scan.total_files:>8}{human_size(scan.total_bytes):>12}")
    if scan.missing_targets:
        print(f"\n本机不存在的位置：{', '.join(scan.missing_targets)}")
    if scan.skipped:
        print(f"跳过 {len(scan.skipped)} 个文件（符号链接/占用/无权限等），加 --json 看明细。")


def cmd_janitor_scan(args) -> int:
    scan = scan_system(
        max_age_days=args.max_age_days,
        targets=_janitor_targets(args),
    )
    if args.json:
        print(json.dumps(scan.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(BANNER)
        print(f"系统垃圾袋位置: {args.bag_dir or default_bag_dir()}\n")
        _print_janitor_scan(scan)
    return 0


def cmd_janitor_scoop(args) -> int:
    bag = JanitorBag(Path(args.bag_dir) if args.bag_dir else None)
    scan = scan_system(
        max_age_days=args.max_age_days,
        targets=_janitor_targets(args),
    )
    risky = [f for f in scan.files if f.category in RISKY_CATEGORIES]
    normal = [f for f in scan.files if f.category not in RISKY_CATEGORIES]

    if not scan.files:
        print("没有符合条件的垃圾可清理。")
        return 0
    if not args.quiet:
        _print_janitor_scan(scan)

    mode = "直接删除（不可恢复）" if args.delete else "铲入系统垃圾袋（可恢复）"
    print(f"\n本次将处理 {scan.total_files} 个文件，共 {human_size(scan.total_bytes)}，模式：{mode}")
    if risky and not args.delete:
        print("提示：回收站/废纸篓属于高风险类别，仅在 --delete 模式下清空，本次自动跳过。")
    if args.dry_run:
        print("dry-run：仅演示，不改动任何文件。")
        return 0
    if not _confirm("确认执行？", args.yes):
        print("已取消。")
        return 2

    batch = None
    if normal:
        batch = bag.scoop(normal, delete=args.delete,
                          note="system janitor", risky_cleared=risky)
        ok = [i for i in batch.items if i.get("action") != "error"]
        err = [i for i in batch.items if i.get("action") == "error"]
        freed = sum(i.get("size", 0) for i in ok)
        print(f"\n已处理 {len(ok)} 个文件，释放 {human_size(freed)}"
              + (f"；{len(err)} 个文件因占用/权限跳过" if err else ""))
        if args.delete:
            print("文件已直接删除（清单记录在系统垃圾袋索引中）。")
        else:
            print(f"已封存在 {bag.dir}")
            print(f"后悔了执行：litter-scoop janitor restore {batch.batch_id}")
    if risky and args.delete:
        ok, msg = empty_recycle_bin()
        print(("回收站/废纸篓已清空。" if ok else f"回收站清空失败：{msg}"))
    return 0


def cmd_janitor_bags(args) -> int:
    bag = JanitorBag(Path(args.bag_dir) if args.bag_dir else None)
    batches = bag.list_batches()
    stats = bag.stats()
    if not batches:
        print(f"系统垃圾袋是空的（{bag.dir}）。")
        return 0
    print(f"系统垃圾袋位置: {bag.dir}")
    print(f"共 {stats['batches']} 个批次 / {stats['items']} 个文件 / 占用 {human_size(stats['bytes'])}\n")
    for entry in batches:
        print(f"  {entry['batch_id']}  {entry['created_at']}  "
              f"{entry.get('mode', 'bag'):<6} {entry['items']} 个文件 / "
              f"{human_size(entry.get('bytes', 0))}")
    return 0


def cmd_janitor_restore(args) -> int:
    bag = JanitorBag(Path(args.bag_dir) if args.bag_dir else None)
    if not _confirm(f"将把批次 {args.batch_id} 的垃圾移回原位置，确认？", args.yes):
        print("已取消。")
        return 2
    try:
        restored = bag.restore(args.batch_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 4
    print(f"已恢复 {len(restored)} 个文件到原位置。")
    return 0


def cmd_janitor_empty(args) -> int:
    bag = JanitorBag(Path(args.bag_dir) if args.bag_dir else None)
    stats = bag.stats()
    if stats["batches"] == 0:
        print("系统垃圾袋本来就是空的。")
        return 0
    target = args.batch_id or "全部批次"
    if not _confirm(f"即将永久销毁系统垃圾袋中的 {target}（不可恢复），确认？", args.yes):
        print("已取消。")
        return 2
    removed = bag.empty(args.batch_id)
    print(f"已永久清空 {removed} 个批次。")
    return 0


def cmd_janitor_schedule(args) -> int:
    if args.uninstall:
        ok = uninstall_schedule()
        print("已卸载定期清理任务。" if ok else "没有找到已安装的定期任务。")
        return 0
    line = render_schedule(freq=args.freq, at=args.at, day=args.day)
    if args.print_only or not args.install:
        print("定期清理任务命令（仅预览，未安装）：\n")
        print(line)
        print("\n加 --install 安装；安装后将按计划自动执行 "
              "`janitor scoop -y --delete`（直接删除超龄垃圾）。")
        return 0
    try:
        install_schedule(freq=args.freq, at=args.at, day=args.day)
    except OSError as exc:
        print(f"[错误] 安装失败：{exc}", file=sys.stderr)
        return 4
    print(f"已安装定期清理任务（{args.freq} {args.at}）：\n{line}")
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

    # ----- janitor: system junk cleanup -----
    jan = sub.add_parser("janitor", help="定期清理电脑垃圾（临时文件/缓存/回收站）")
    jsub = jan.add_subparsers(dest="janitor_command", required=True)

    def _jan_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--max-age-days", type=float, default=7,
                        help="只清理多少天前的旧文件，默认 7；0 表示不限")
        sp.add_argument("--category", nargs="+",
                        help="只处理指定类别（如 user-temp npm-cache）")
        sp.add_argument("--include-risky", action="store_true",
                        help="包含回收站/废纸篓等高风险类别")
        sp.add_argument("--extra-path", nargs="+", default=[],
                        help="追加自定义垃圾目录（白名单之外的额外路径）")
        sp.add_argument("--no-default", action="store_true",
                        help="不扫描系统默认位置，只扫 --extra-path/--category 指定目标")
        sp.add_argument("--bag-dir", default=None,
                        help="系统垃圾袋位置，默认 ~/.catlitter-janitor")

    p = jsub.add_parser("scan", help="只扫描系统垃圾，统计占用（只读）")
    _jan_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_janitor_scan)

    p = jsub.add_parser("scoop", help="清理系统垃圾（默认铲入可恢复垃圾袋）")
    _jan_common(p)
    p.add_argument("--delete", action="store_true", help="直接删除，不留备份")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-y", "--yes", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_janitor_scoop)

    p = jsub.add_parser("bags", help="列出系统垃圾袋批次")
    p.add_argument("--bag-dir", default=None)
    p.set_defaults(func=cmd_janitor_bags)

    p = jsub.add_parser("restore", help="把系统垃圾移回原位置")
    p.add_argument("batch_id")
    p.add_argument("--bag-dir", default=None)
    p.add_argument("-y", "--yes", action="store_true")
    p.set_defaults(func=cmd_janitor_restore)

    p = jsub.add_parser("empty", help="永久清空系统垃圾袋")
    p.add_argument("batch_id", nargs="?", default=None)
    p.add_argument("--bag-dir", default=None)
    p.add_argument("-y", "--yes", action="store_true")
    p.set_defaults(func=cmd_janitor_empty)

    p = jsub.add_parser("schedule", help="安装/预览/卸载定期清理任务")
    p.add_argument("--print", dest="print_only", action="store_true", help="只预览命令")
    p.add_argument("--install", action="store_true", help="安装到系统计划任务")
    p.add_argument("--uninstall", action="store_true", help="卸载定期任务")
    p.add_argument("--freq", choices=["daily", "weekly", "monthly"], default="weekly")
    p.add_argument("--at", default="10:00", help="执行时刻 HH:MM，默认 10:00")
    p.add_argument("--day", default="SUN", help="weekly 时的星期，默认 SUN")
    p.set_defaults(func=cmd_janitor_schedule)

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

