# Changelog

## 0.2.0 – 2026-09-05

### Added
- 新增 `janitor` 子命令组：用同一套猫砂安全模型清理**电脑系统垃圾**
  - `janitor scan/scoop/bags/restore/empty`：扫描、装袋、查看、恢复、清空
  - 跨平台白名单：Windows 临时目录/缩略图缓存、pip/npm/yarn 缓存，
    macOS `~/Library/Caches`，Linux `~/.cache`、`/tmp`
  - 回收站/废纸篓作为高风险类别默认关闭，且仅允许 `--delete` 模式，
    Windows 走官方 `Clear-RecycleBin`
  - 四重安全：白名单制、默认只清 7 天前旧文件、默认装袋可恢复、
    不跟随符号链接并校验物理路径不越出白名单根
  - `janitor schedule`：一键安装/预览/卸载定期清理（schtasks / crontab）
  - `--extra-path` 追加自定义目录，`--no-default` 只扫指定目录
- 新增 15 个 janitor 单元测试（总计 37 个），含装袋→恢复字节一致性、
  年龄门槛、符号链接逃逸防护与计划任务命令渲染

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
