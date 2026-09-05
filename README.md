# Litter Scoop · 猫砂模型冗余代码清理器

> **把废物像铲猫砂一样铲进垃圾袋：可以打包扔掉，也可以先记录、随时复原。**

`litter-scoop` 是一个零依赖的命令行工具与 Python 库：它会**自动识别你的项目类型**（Python / Node-TS-JS / Go / Rust / JVM / C 系 …），挑选最合适的冗余代码检测器，找出未使用的导入、死函数、不可达代码、注释掉的旧代码、空文件、重复文件、编辑器备份残留等"废物"，然后按 **猫砂模型（Cat-Litter Model）** 处理：

```
                        ┌─────────────────────────────┐
   你的项目  ── scan ──▶ │  冗余清单（什么、在哪、为什么） │
                        └──────────────┬──────────────┘
                                       │ scoop
                    ┌──────────────────┴──────────────────┐
                    ▼                                       ▼
          ┌──────────────────┐                   ┌──────────────────┐
          │  .litter-box 垃圾袋 │  restore 复原      │  --delete 直接扔掉 │
          │ 原始副本+清单 manifest│ ───────────────▶  │ 只留删除记录       │
          └──────────────────┘                   └──────────────────┘
                    │ empty
                    ▼
             永久销毁（仅此一步不可逆）
```

**核心安全承诺**：默认模式下，任何文件被修改前，其**完整原始副本**都会封存在 `.litter-box/` 垃圾袋中，`restore` 一条命令即可**字节级还原**；只有显式执行 `empty` 才会真正销毁。

---

## 为什么叫"猫砂模型"

传统清理工具只有"删 / 不删"两个选项，删错一次代价很大。猫砂模型把清理拆成三个心理负担完全不同的动作：

| 动作 | 命令 | 类比 | 可逆性 |
|---|---|---|---|
| **铲进垃圾袋** | `litter-scoop scoop` | 把猫砂铲进袋子但还没提出门 | 完全可逆 |
| **记录在案** | `.litter-box/manifests/*.json` | 在垃圾袋上贴标签：这是什么、为什么铲、原来长啥样 | — |
| **扔掉** | `litter-scoop scoop --delete` 或事后 `empty` | 扎口丢进楼下垃圾桶 | 不可逆 |

## 特性

- **项目自动适配**：根据 `pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml` / `pom.xml` 等标志文件与语言代码行数，自动决定启用哪些检测器，并识别 React/Vue/Next/Django/Flask/FastAPI 等框架。
- **多语言规则**：
  - Python：基于标准库 `ast` 的精确分析（不是正则猜的）；
  - JS/TS/JSX/TSX/Vue/Svelte：带字符串/注释掩码的词法分析，不会把字符串里的 `console.log` 当调试语句；
  - 全部语言：空文件、字节级重复文件、`.bak/.orig/~/.old/.swp` 备份残留、注释代码块。
- **保守优先**：装饰器注册的函数、`__all__` 导出、`__dunder__`、`if __name__ == "__main__"`、测试文件、`import *`、re-export 全部自动豁免，压低误报。
- **三档置信度**（high / medium / low），可只清理高置信项。
- **三种报告**：终端彩色文本、机器可读 JSON、可离线打开、带筛选的单文件 HTML。
- **零运行时依赖**，Python 3.11+ 即可，Windows / macOS / Linux 通吃。
- 自动尊重 `.gitignore` / `.litterignore`，默认要求 git 工作区干净才动手。

## 安装

```bash
# 方式一：克隆后以可编辑模式安装（推荐开发者）
git clone https://github.com/<your-name>/litter-scoop.git
cd litter-scoop
pip install -e .

# 方式二：直接用 pip（发布到 PyPI 后）
pip install litter-scoop

# 不安装也能跑
python -m litter_scoop --help
```

## 5 分钟上手

```bash
# 0. 看看它怎么识别你的项目（只读）
litter-scoop adapt

# 1. 只扫描、不动文件
litter-scoop scan
litter-scoop scan --report html -o litter-report.html   # 可视化报告
litter-scoop scan --min-severity medium                 # 只看中等置信以上
litter-scoop scan --rule unused-import unreachable-code # 只看指定规则

# 2. 铲进垃圾袋（可恢复）。先加 --dry-run 预览最稳妥
litter-scoop scoop --dry-run
litter-scoop scoop -y                  # -y 跳过确认
litter-scoop scoop --min-severity high -y

# 3. 看看垃圾袋里有什么
litter-scoop bags

# 4. 后悔了？字节级恢复
litter-scoop restore <批次号> -y

# 5. 跑几天确认没问题，再永久清空垃圾袋
litter-scoop empty -y

# 或者：我心已决，直接扔掉（只留删除清单，不可恢复）
litter-scoop scoop --delete -y
```

## 检测规则一览

| 规则 id | 适用 | 说明 | 默认置信度 |
|---|---|---|---|
| `unused-import` | Python / JS·TS | 导入后从未使用 | 中 |
| `unused-toplevel-symbol` | Python | 顶层函数/类全项目无引用 | 中 |
| `unused-local` | Python | 赋值后从未读取的局部变量 | 中 |
| `unreachable-code` | Python | return/raise/break/continue 之后的语句 | 高 |
| `duplicate-definition` | Python | 同名函数/类被重复定义覆盖 | 高 |
| `empty-stub` | Python | 只剩 docstring + `pass`/`...` 的空壳 | 低 |
| `unused-top-level-function` | JS·TS | 未导出且从未调用的函数 | 低 |
| `unused-debug-statement` | JS·TS | 遗留的 `console.*` / `debugger` | 低 |
| `commented-code` | 全部 | 连续 ≥3 行被注释掉的疑似代码 | 低 |
| `empty-file` | 全部 | 只有空白的文件 | 高 |
| `duplicate-file` | 全部 | 与另一文件字节完全相同 | 高 |
| `backup-file` | 全部 | `.bak/.orig/.old/~/.swp/.tmp` 残留 | 中 |

## 配置（可选）

在项目根目录放一份 `litterbox.toml`（可由 `litter-scoop init` 生成，模板见 [`litterbox.example.toml`](litterbox.example.toml)）：

```toml
[litterbox]
bag_dir = ".litter-box"
min_severity = "low"
require_clean_git = true
detect_commented_code = true
exclude = ["docs/**", "migrations/**"]

[rules]
"empty-stub" = false        # 关掉某条规则

[adapters]
"web" = false               # 关掉整个 JS/TS 检测器
```

## 垃圾袋目录结构

```
.litter-box/
├── index.json                       # 批次索引
├── manifests/
│   └── 20260905-152950-1a20.json    # 每批一张"垃圾袋标签"：原因/原路径/哈希
└── files/
    └── 20260905-152950-1a20/        # 镜像原项目路径的完整原始副本
        └── src/app.py
```

## 作为 Python 库使用

```python
from pathlib import Path
from litter_scoop import scan_project, GarbageBag
from litter_scoop.config import Config

root = Path("./my-project")
result = scan_project(root)
print(result.profile.summary())
for f in result.findings:
    print(f.path, f.start_line, f.rule_id, f.message)

cfg = Config()
cfg.require_clean_git = False
bag = GarbageBag(root, cfg)
batch = bag.scoop([f for f in result.findings if f.severity.value != "low"])
print(batch.batch_id)
# bag.restore(batch.batch_id)
```

## 开发

```bash
pip install -e ".[dev]"
pytest                      # 22 个测试（含铲入→恢复字节一致性往返测试）
python -m litter_scoop -C tests/fixtures/sample_project scan
```

项目布局：

```
src/litter_scoop/
├── cli.py              # 命令行入口
├── engine.py           # 扫描引擎：调度适配器、跨文件名字索引
├── project.py          # 项目指纹 & 适配器自动选择
├── ignore.py           # .gitignore 子集实现
├── config.py           # litterbox.toml
├── models.py           # Finding / ProjectProfile / BagBatch
├── scoop.py            # 猫砂模型：装袋/恢复/清空
├── adapters/           # python / web / generic 三个检测器
└── reporters/          # text / json / html 三种报告
```

## 路线图

- [ ] 增量模式：只扫描 git 变更文件
- [ ] autofix 安全规则（仅 `unused-import` 直接重写）
- [ ] SARIF 输出，接入 GitHub Code Scanning
- [ ] Go / Java / Rust 的 AST 级适配器（当前为通用词法规则）

## License

MIT，见 [LICENSE](LICENSE)。
