# AI ROM Toolkit

面向 AI 与开发者的 **GB / GBC / GBA 汉化、ROM 分析和 BUG 修复工具与指南**，主要运行环境为 Windows 10/11 x64。

提供带身份与前像保护的字节补丁工具、独立项目初始化、平台指南、翻译/验收模板、自制测试源码和可选的 mGBA 控制脚本。每款游戏仍需分析自己的编码、控制码、字体和消费路径。

## 直接交给 AI 初始化

复制这份完整提示词：**[AI 环境初始化提示词](prompts/00_BOOTSTRAP_ENVIRONMENT.txt)**。

它会指导 AI 下载本仓库、校验并安装 Python / Arm 工具链 / RGBDS / 官方 mGBA，运行环境检查和自制程序测试，然后给出真实能力与缺项报告。

也可以在仓库目录中运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Initialize_Environment.ps1
```

或双击 `Initialize_Environment.cmd`。脚本不修改系统 PATH、注册表或全局执行策略，不需要管理员权限。依赖安装到仓库自己的 `runtime/`，版本、下载地址与 SHA-256 见 [dependencies.lock.json](dependencies.lock.json)。

已有下载缓存时可使用 `-CacheDirectory "D:\ROM_AI_CACHE"`；重复运行会核对安装标记和入口文件，不覆盖不明来源的现有目录。无法下载、校验不符或自测失败会明确报错。

## 开始使用

初始化完成后，打开 `Open_AI_Shell.cmd`，或在 PowerShell 使用 `python.cmd`：

```powershell
.\python.cmd tools\romkit.py identity "D:\ROMs\game.gba"
.\python.cmd tools\romkit.py init "D:\ROMs\game.gba" --platform gba --project "workspace\projects\my_game"
.\python.cmd tools\verify_package.py
```

GB/GBC 将平台参数改为 `gb` / `gbc`。有普通存档时可给 `init` 增加 `--save "D:\Saves\game.sav"`。现有项目不能覆盖初始化。

后续按已授权范围使用：

- [初始化指定游戏项目](prompts/01_INITIALIZE.txt)
- [汉化任务提示词](prompts/02_LOCALIZE.txt)
- [BUG 修复提示词](prompts/03_FIX_BUG.txt)

## 指南

- [GB/GBC 与 GBA 平台差异](docs/PLATFORM_GUIDE.txt)
- [字库、文本扩容与验收](docs/LOCALIZATION_WORKFLOW.txt)：统一占用区、编码与缓存、控制码、指针、排版、取名与保存。
- [依赖来源与环境](docs/DOWNLOADS_AND_ENVIRONMENT.txt)
- [可选 mGBA 控制后端](docs/MGBA_AI_GUIDE.txt)
- [验证范围](docs/VALIDATION_SCOPE.txt)
- [模板目录](templates/)
- [格兰宝空间重叠案例](docs/cases/GURANBO_OVERLAP.txt)：特定输入的分析示例，独立于通用初始化提示词。

只检查受当前改动影响的项目，保留未受影响的通过证据。静态检查、模拟器观察、普通保存读回和真机验证分别报告；不默认要求完整通关。

## 基础环境与可选无头扩展

自动初始化提供官方 mGBA 图形版及其归档中实际携带的程序。**定制的暂停逐帧、认证 TCP、私有 GDB 入口不属于官方版的保证能力。**

`tools/windows_mgba/` 提供控制脚本源码，但依赖特定定制 mGBA 后端。本仓库暂不分发这些定制可执行文件及尚未整理的修改源码，也不会自动从旧私有包取来发布。基础初始化会将该扩展标记为缺少后端，不把它算作基础工具故障或扩展已通过。

只有在自行取得来源明确、许可证完整且匹配的后端后，才按 [构建与兼容性说明](tools/windows_mgba/BUILD_NOTES.md) 单独验证：

```powershell
.\python.cmd tools\check_environment.py --require-headless
.\python.cmd tools\self_test.py --with-headless
```

默认 `self_test.py` 仅检查工具链、自制 ROM 构建和补丁保护，不会声称已测模拟器或商业游戏。

## 源码与许可证

本仓库的原创代码、文档、提示词、模板与自制示例采用 [MIT](LICENSE)。第三方材料与外部程序继续适用各自许可证，见 [第三方说明](THIRD_PARTY_NOTICES.md)。

仓库不包含商业 ROM、BIOS、玩家 SAV、即时状态、令牌、运行会话或第三方程序包。`runtime/`、`workspace/`、`reports/` 和下载缓存都排除在 Git 之外。请仅处理自己有权使用的输入。

## 本地验证

基础源码测试不需要商业 ROM或第三方程序：

```powershell
.\python.cmd -m unittest discover -s tests -v
```

工具链测试请先完成环境初始化。此项目是辅助工具与工作规范，不是自动完成任意游戏汉化的程序。
