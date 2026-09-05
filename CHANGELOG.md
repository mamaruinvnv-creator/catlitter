# Changelog

## 0.1.0 – 2026-09-05

首个公开版本。

### Added
- 项目自动适配：标志文件识别 + 语言行数画像 + 框架检测，自动选择检测器
- Python AST 检测器：unused-import / unused-toplevel-symbol / unused-local /
  unreachable-code / duplicate-definition / empty-stub / commented-code
- JS·TS 词法检测器（带字符串与注释掩码）：unused-import /
  unused-top-level-function / unused-debug-statement / commented-code
- 通用检测器：empty-file / duplicate-file / backup-file / commented-code
- 猫砂模型工作流：scan / scoop / bags / restore / empty / init / adapt
- 行级与整文件级冗余统一处理，铲入前封存完整原始副本，恢复保证字节一致
- text / json / html 三种报告
- litterbox.toml 配置、.gitignore / .litterignore 支持
- 22 个单元测试，覆盖规则命中、误报豁免与装袋-恢复往返
