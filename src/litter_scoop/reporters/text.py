"""Terminal reporter with optional ANSI colours (Windows 10+ compatible)."""

from __future__ import annotations

import os
import sys
from collections import Counter

from ..engine import ScanResult
from ..models import Severity

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
}

_SEV_COLOR = {
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "blue",
}

SEVERITY_LABEL_CN = {
    Severity.HIGH: "高",
    Severity.MEDIUM: "中",
    Severity.LOW: "低",
}

RULE_LABEL_CN = {
    "unused-import": "未使用的导入",
    "unused-toplevel-symbol": "未使用的顶层函数/类",
    "unused-local": "未使用的局部变量",
    "unreachable-code": "不可达代码",
    "duplicate-definition": "重复定义",
    "empty-stub": "空壳函数",
    "commented-code": "注释掉的代码",
    "unused-debug-statement": "遗留调试语句",
    "unused-top-level-function": "未使用的函数",
    "empty-file": "空文件",
    "duplicate-file": "重复文件",
    "backup-file": "备份残留文件",
}


def enable_windows_ansi() -> None:
    if os.name == "nt":
        os.system("")  # turns on VT processing in conhost


def _c(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{_ANSI[color]}{text}{_ANSI['reset']}"


def render_text(result: ScanResult, *, color: bool | None = None,
                show_snippet: bool = True, stream=None) -> str:
    enable_windows_ansi()
    if color is None:
        color = bool(getattr(stream or sys.stdout, "isatty", lambda: False)())
    out: list[str] = []
    p = result.profile

    out.append(_c("== Litter Scoop 猫砂扫描报告 ==", "bold", color))
    out.append(f"项目根目录 : {p.root}")
    out.append(f"项目类型   : {', '.join(p.project_types) or '未识别（按通用项目处理）'}")
    if p.frameworks:
        out.append(f"识别框架   : {', '.join(p.frameworks)}")
    lang_line = ", ".join(f"{lang}={lines}行" for lang, lines in
                          sorted(p.languages.items(), key=lambda kv: -kv[1]))
    out.append(f"语言构成   : {lang_line or '无代码文件'}")
    out.append(f"启用检测器 : {', '.join(p.adapters)}")
    out.append(f"扫描文件数 : {result.files_scanned}（跳过二进制 {result.skipped_binary}）")
    out.append("")

    if not result.findings:
        out.append(_c("猫砂盆很干净，没有发现需要铲除的冗余代码。", "green", color))
        return "\n".join(out)

    rule_counter = Counter(f.rule_id for f in result.findings)
    sev_counter = Counter(f.severity for f in result.findings)

    out.append(_c("-- 按规则汇总 --", "bold", color))
    for rule_id, count in rule_counter.most_common():
        label = RULE_LABEL_CN.get(rule_id, rule_id)
        out.append(f"  {label:<16} {rule_id:<26} {count} 处")
    out.append("")
    sev_line = "严重度分布 : " + " / ".join(
        f"{SEVERITY_LABEL_CN[s]}={sev_counter.get(s, 0)}"
        for s in (Severity.HIGH, Severity.MEDIUM, Severity.LOW)
    )
    out.append(sev_line)
    out.append("")

    current_file = None
    for finding in result.findings:
        if finding.path != current_file:
            current_file = finding.path
            out.append(_c(f"▌ {current_file}", "cyan", color))
        sev_color = _SEV_COLOR[finding.severity]
        loc = "整文件" if finding.whole_file else f"{finding.start_line}-{finding.end_line}行"
        label = RULE_LABEL_CN.get(finding.rule_id, finding.rule_id)
        head = (
            f"  [{_c(SEVERITY_LABEL_CN[finding.severity], sev_color, color)}] "
            f"{loc:<8} {label} · {finding.message}"
        )
        out.append(head)
        if show_snippet and finding.snippet:
            for snip_line in finding.snippet.splitlines()[:6]:
                out.append(_c(f"      │ {snip_line}", "gray", color))
    out.append("")
    total = len(result.findings)
    out.append(_c(f"共发现 {total} 处疑似冗余代码。", "bold", color))
    out.append("下一步：litter-scoop scoop  # 铲入垃圾袋（可恢复）；"
               "加 --delete 直接扔掉；加 --report html 生成可视化报告")
    return "\n".join(out)
