# 猫砂 CatLitter · 冲 Star 宣传文案包

仓库地址：**https://github.com/mamaruinvnv-creator/catlitter**
配图：`assets/og-social.png`（横版主视觉）、`assets/promo-wide.png`（宽幅）
下面每个版本都可直接复制发布。

---

## 1. X / Twitter（英文，吃国际开发者流量）

> I keep getting scared by "dead code removers" that delete things I can't get back.
>
> So I built **CatLitter** 🐈 — it treats redundant code like cat litter:
> 1️⃣ scan → 2️⃣ scoop into a restorable garbage bag (byte-for-byte backup + manifest) → 3️⃣ throw it away ONLY when you're sure.
>
> Auto-detects Python/JS/TS projects, zero dependencies, MIT.
>
> ⭐ https://github.com/mamaruinvnv-creator/catlitter

**Hashtags**: #Python #JavaScript #TypeScript #Refactoring #DeveloperTools #CleanCode #OpenSource

---

## 2. V2EX（中文程序员社区，最对口，发「分享创造」节点）

**标题**：猫砂 CatLitter：一个"先装袋、可反悔、确认再删"的冗余代码清理工具

**正文**：

> 大家清理死代码时是不是也有这种纠结：工具说这段没用，删吧怕删错，不删吧又膈应。
>
> 我按"铲猫砂"的思路写了个开源小工具，取名「猫砂 CatLitter」：
>
> - `scan` 先扫描，只读不动；
> - `scoop` 把冗余代码"铲进垃圾袋"——**改动前会把文件完整原始副本封进 `.litter-box/`，附清单（原因/位置/哈希），随时 `restore` 字节级还原**；
> - 用几天没问题，再 `empty` 永久扔掉，这一步才不可逆。
>
> 能力上：
> 1. **自动适配项目**：读 pyproject/package.json/go.mod/Cargo.toml 等标志文件，按语言和框架自动选检测器；
> 2. Python 走标准库 AST（不是正则硬猜）：未用导入/顶层死函数/未用局部变量/不可达代码/重复定义/空壳函数；
> 3. JS/TS 带字符串和注释掩码：未用导入、未用函数、console/debugger 残留；
> 4. 全语言通用：空文件、字节级重复文件、.bak/.orig 备份残留、注释掉的代码块；
> 5. 装饰器注册、`__all__`、`__main__`、测试文件、re-export 全部自动豁免，尽量不误报；
> 6. 终端 / JSON / 可离线筛选的 HTML 报告三种输出；
> 7. **零运行时依赖**，Python 3.11+，Win/macOS/Linux 都能跑，MIT。
>
> 目前 22 个单测全绿（含"铲入→恢复 SHA256 一致"的往返测试），我用它扫自己的源码是零冗余。
>
> 仓库：https://github.com/mamaruinvnv-creator/catlitter
> Release 里有打包好的源码，欢迎试用、提 issue、帮点个 Star，谢谢各位铲屎官。

---

## 3. 即刻（短，适合配图）

> 写了个开源工具叫「猫砂 CatLitter」🐈
>
> 清理冗余代码最怕删错？它把流程做成铲猫砂：先扫 → 铲进可恢复的垃圾袋（原始文件封存+清单，随时字节级还原）→ 确认没问题再永久扔掉。
>
> 自动识别 Python/JS/TS 项目、零依赖、MIT，22 个测试全绿。
> GitHub 求个 Star：github.com/mamaruinvnv-creator/catlitter

---

## 4. 小红书（种草口吻 + 标签，配主视觉图）

**标题**：程序员铲屎官集合！我做了个铲"代码垃圾"的开源神器🐈

**正文**：

> 家人们谁懂啊，项目里的死代码就像猫砂盆里的💩：
> 不铲膈应，铲了又怕把还能用的东西一起扔了……
>
> 于是我做了「猫砂 CatLitter」，把清冗余代码变成三步铲屎流程👇
>
> 📍 scan 扫描：只读不动，列出所有"废物"和置信度
> 📍 scoop 铲屎：铲进垃圾袋封存，原始文件完整备份+贴标签，后悔了一键字节级还原
> 📍 empty 扔垃圾：确认几天没问题，再永久销毁
>
> ✅ 自动识别项目类型，Python 用 AST 精确分析，JS/TS 也支持
> ✅ 未用导入、死函数、不可达代码、重复文件、注释掉的旧代码全能抓
> ✅ 零依赖！一条命令安装，Win/Mac 都行
> ✅ 还能生成超清爽的可视化 HTML 报告
>
> 开源 MIT，求一个 Star 鼓励铲屎官继续更新⭐
> 🔗 github.com/mamaruinvnv-creator/catlitter
>
> #程序员 #开源项目 #代码 #Python #前端 #编程 #效率工具 #github

---

## 5. 掘金 / 知乎（技术长文导语，正文可展开 README）

**标题**：我为什么用"猫砂模型"重新设计冗余代码清理：可反悔，才敢自动化

**导语**：

> 现有死代码工具的问题不是检测不准，而是"检测即删除"的心理负担太重——一次误删的代价，足以让你再也不信任它。
>
> 这篇文章介绍我开源的「猫砂 CatLitter」：它把清理拆成**扫描、装袋、丢弃**三个心理负担完全不同的阶段，默认所有操作可逆，只有显式 `empty` 才真正销毁。文章会讲：① 猫砂模型的状态机设计；② Python AST 检测如何压低误报（装饰器/`__all__`/re-export 豁免）；③ 跨文件名字引用索引怎么做；④ "改动前封存原始副本 + 字节级恢复"的安全模型；⑤ 零依赖工程化（CLI/HTML 报告/22 个测试）。
>
> 源码：https://github.com/mamaruinvnv-creator/catlitter

---

## 6. 朋友圈 / 微信群（一句话版）

> 最近写了个开源小工具「猫砂 CatLitter」：像铲猫砂一样清理项目里的冗余代码，先铲进可恢复的垃圾袋、确认再删，支持 Python/JS/TS，零依赖。写代码的朋友帮忙点个 Star 呀⭐ github.com/mamaruinvnv-creator/catlitter

---

## 7. GitHub 自家流量优化清单（影响 Star 转化，已完成/待办）

- [x] 仓库一句话描述带核心关键词（dead code / redundant / restorable）
- [x] 10 个 search topics
- [x] README 双语 + 头图 + 徽章 + 顶部/底部 Star 号召
- [x] v0.1.0 Release + 源码资产
- [ ] Settings → General → Social preview 上传 `assets/og-social.png`（分享到 IM/Twitter 时有大图卡片）
- [ ] 提交到这些聚合站：**awesome-python（提 PR）、HelloGitHub、HelloGitHub 月刊投稿、Product Hunt、AlternativeTo、开源中国、掘金沸点、阮一峰科技爱好者周刊投稿（issue）**
- [ ] 后续每个版本在 Release 写清 changelog，保持绿色 CI 徽章
