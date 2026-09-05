"""Standalone HTML report renderer (no external assets, openable offline)."""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime

from ..engine import ScanResult
from ..models import Severity
from .text import RULE_LABEL_CN

_SEV_CN = {Severity.HIGH: "高", Severity.MEDIUM: "中", Severity.LOW: "低"}


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def render_html(result: ScanResult) -> str:
    findings = result.findings
    profile = result.profile
    rule_counter = Counter(f.rule_id for f in findings)
    sev_counter = Counter(f.severity for f in findings)
    total = len(findings)
    max_rule = max(rule_counter.values(), default=1)

    lang_rows = "".join(
        f"<tr><td>{_esc(lang)}</td><td>{lines}</td></tr>"
        for lang, lines in sorted(profile.languages.items(), key=lambda kv: -kv[1])
    )
    rule_bars = "".join(
        f"""<div class="bar-row" data-rule="{_esc(rule)}">
              <span class="bar-label">{_esc(RULE_LABEL_CN.get(rule, rule))}</span>
              <span class="bar-track"><span class="bar-fill" style="width:{count / max_rule * 100:.1f}%"></span></span>
              <span class="bar-num">{count}</span>
            </div>"""
        for rule, count in rule_counter.most_common()
    )

    cards = []
    for sev in (Severity.HIGH, Severity.MEDIUM, Severity.LOW):
        n = sev_counter.get(sev, 0)
        cards.append(
            f"""<div class="card sev-{sev.value}">
                  <div class="card-num">{n}</div>
                  <div class="card-label">{_SEV_CN[sev]}置信度</div>
                </div>"""
        )

    rows_html = []
    for f in findings:
        loc = "整文件" if f.whole_file else f"{f.start_line}–{f.end_line}"
        snippet = html.escape(f.snippet or "")
        rows_html.append(
            f"""<tr class="finding" data-sev="{f.severity.value}" data-rule="{_esc(f.rule_id)}">
                  <td class="sev-cell"><span class="pill pill-{f.severity.value}">{_SEV_CN[f.severity]}</span></td>
                  <td class="path-cell">{_esc(f.path)}<div class="loc">{_esc(loc)}</div></td>
                  <td>{_esc(RULE_LABEL_CN.get(f.rule_id, f.rule_id))}<div class="rule-id">{_esc(f.rule_id)}</div></td>
                  <td>{_esc(f.message)}
                      {f'<pre class="snippet">{snippet}</pre>' if snippet else ''}
                  </td>
                  <td class="conf">{f.confidence:.0%}</td>
                </tr>"""
        )

    rule_options = "".join(
        f'<option value="{_esc(r)}">{_esc(RULE_LABEL_CN.get(r, r))}（{c}）</option>'
        for r, c in rule_counter.most_common()
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Litter Scoop 猫砂扫描报告</title>
<style>
  :root {{
    --bg:#f6f8f7; --card:#ffffff; --ink:#1f2d2b; --muted:#6b7d79;
    --teal:#0f8a7e; --teal-soft:#dff1ef;
    --amber:#c77c12; --amber-soft:#fbeed3;
    --red:#c0392b; --red-soft:#fbe1de;
    --line:#e3e9e7;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
         background:var(--bg); color:var(--ink); line-height:1.55; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:28px 22px 60px; }}
  header h1 {{ margin:0 0 4px; font-size:24px; }}
  header .sub {{ color:var(--muted); font-size:13px; }}
  .grid {{ display:grid; gap:14px; }}
  .overview {{ grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); margin:18px 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:16px 18px; }}
  .card-num {{ font-size:30px; font-weight:700; }}
  .card-label {{ color:var(--muted); font-size:13px; }}
  .sev-high .card-num {{ color:var(--red); }}
  .sev-medium .card-num {{ color:var(--amber); }}
  .sev-low .card-num {{ color:var(--teal); }}
  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
            padding:18px 20px; margin:14px 0; }}
  .panel h2 {{ margin:0 0 12px; font-size:16px; }}
  .meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px 22px; font-size:14px; }}
  .meta div b {{ color:var(--muted); font-weight:500; margin-right:8px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
  .lang-table td {{ padding:3px 10px 3px 0; }}
  .bar-row {{ display:grid; grid-template-columns:150px 1fr 46px; gap:10px;
              align-items:center; margin:7px 0; }}
  .bar-label {{ font-size:13px; color:var(--ink); }}
  .bar-track {{ background:#edf2f0; border-radius:6px; height:14px; overflow:hidden; }}
  .bar-fill {{ display:block; height:100%; background:linear-gradient(90deg,#17a395,#0f8a7e); }}
  .bar-num {{ text-align:right; font-variant-numeric:tabular-nums; color:var(--muted); }}
  .controls {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:12px; }}
  .controls button, .controls select {{ font:inherit; font-size:13px; padding:6px 12px;
       border:1px solid var(--line); border-radius:999px; background:#fff; cursor:pointer; }}
  .controls button.active {{ background:var(--teal); color:#fff; border-color:var(--teal); }}
  .findings {{ width:100%; }}
  .findings th {{ text-align:left; color:var(--muted); font-weight:600; font-size:12.5px;
       padding:8px 10px; border-bottom:2px solid var(--line); }}
  .findings td {{ padding:10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  .path-cell {{ font-family:Consolas,monospace; font-weight:600; white-space:nowrap; }}
  .loc {{ color:var(--muted); font-weight:400; font-size:12px; }}
  .rule-id {{ color:var(--muted); font-size:11.5px; font-family:Consolas,monospace; }}
  .pill {{ display:inline-block; min-width:22px; text-align:center; border-radius:6px;
       padding:2px 7px; font-size:12px; font-weight:700; }}
  .pill-high {{ background:var(--red-soft); color:var(--red); }}
  .pill-medium {{ background:var(--amber-soft); color:var(--amber); }}
  .pill-low {{ background:var(--teal-soft); color:var(--teal); }}
  .snippet {{ background:#f3f6f5; border-left:3px solid #b9d6d1; border-radius:6px;
       padding:8px 10px; margin:7px 0 0; font-family:Consolas,monospace; font-size:12.5px;
       white-space:pre-wrap; overflow-x:auto; }}
  .conf {{ font-variant-numeric:tabular-nums; color:var(--muted); }}
  .clean {{ text-align:center; padding:40px; color:var(--teal); font-size:18px; }}
  footer {{ color:var(--muted); font-size:12px; text-align:center; margin-top:26px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🧹 Litter Scoop 猫砂扫描报告</h1>
    <div class="sub">生成时间 {_esc(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))} · 项目根目录 {_esc(profile.root)}</div>
  </header>

  <div class="grid overview">
    <div class="card"><div class="card-num">{total}</div><div class="card-label">疑似冗余总数</div></div>
    {''.join(cards)}
    <div class="card"><div class="card-num">{result.files_scanned}</div><div class="card-label">已扫描文件</div></div>
  </div>

  <div class="panel">
    <h2>项目自动适配画像</h2>
    <div class="meta">
      <div><b>项目类型</b>{_esc(', '.join(profile.project_types) or '通用项目')}</div>
      <div><b>框架</b>{_esc(', '.join(profile.frameworks) or '未检测到')}</div>
      <div><b>主力语言</b>{_esc(profile.primary_language)}</div>
      <div><b>启用检测器</b>{_esc(', '.join(profile.adapters))}</div>
    </div>
    <details style="margin-top:10px"><summary style="cursor:pointer;color:var(--muted);font-size:13px">语言代码行数</summary>
      <table class="lang-table" style="margin-top:8px">{lang_rows}</table>
    </details>
  </div>

  <div class="panel">
    <h2>冗余类型分布</h2>
    {rule_bars or '<div class="clean">无冗余</div>'}
  </div>

  <div class="panel">
    <h2>冗余明细（{total}）</h2>
    <div class="controls">
      <button class="active" data-filter-sev="all">全部</button>
      <button data-filter-sev="high">仅高置信</button>
      <button data-filter-sev="medium">中及以上</button>
      <button data-filter-sev="low">仅低置信</button>
      <select id="ruleSelect"><option value="all">全部规则</option>{rule_options}</select>
    </div>
    {"<p class='clean'>猫砂盆很干净，没有需要铲除的冗余代码。</p>" if not findings else '''
    <table class="findings">
      <thead><tr><th>置信</th><th>位置</th><th>规则</th><th>说明 / 代码片段</th><th>得分</th></tr></thead>
      <tbody>
        ''' + ''.join(rows_html) + '''
      </tbody>
    </table>'''}
  </div>

  <footer>Litter Scoop · 把冗余代码像猫砂一样铲进垃圾袋，可装袋、可记录、可恢复、可丢弃。</footer>
</div>
<script>
(function() {{
  let sev = 'all';
  const ruleSel = document.getElementById('ruleSelect');
  const rows = Array.from(document.querySelectorAll('tr.finding'));
  function apply() {{
    const rule = ruleSel ? ruleSel.value : 'all';
    const order = {{high:2, medium:1, low:0}};
    rows.forEach(r => {{
      const s = r.dataset.sev, rl = r.dataset.rule;
      let okSev = sev === 'all' || (sev === 'medium' ? order[s] >= 1 : s === sev);
      let okRule = rule === 'all' || rl === rule;
      r.style.display = (okSev && okRule) ? '' : 'none';
    }});
  }}
  document.querySelectorAll('[data-filter-sev]').forEach(btn => btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-sev]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active'); sev = btn.dataset.filterSev; apply();
  }}));
  if (ruleSel) ruleSel.addEventListener('change', apply);
}})();
</script>
</body>
</html>
"""
