# 示例

- `sample-report.html`：对 `tests/fixtures/sample_project`（一个故意写脏的 Python + JS 混合项目）运行
  `litter-scoop scan --report html` 生成的可视化报告，浏览器直接打开即可看到筛选交互。
- `../tests/fixtures/sample_project/`：故意包含各类冗余代码的演示项目，可用来快速体验完整流程：

```bash
litter-scoop -C ../tests/fixtures/sample_project adapt
litter-scoop -C ../tests/fixtures/sample_project scan
```
