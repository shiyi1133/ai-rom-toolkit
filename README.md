# AI ROM Toolkit

面向 AI 与开发者的 **GB / GBC / GBA 汉化、游戏改版、ROM 分析和 BUG 修复工具与指南**。支持 Windows 10/11 x64 和 Linux x86_64 环境初始化。

提供有身份与前像保护的字节补丁、独立项目初始化、平台指南、改版/汉化/验收模板、自制测试源码和可选 mGBA 控制脚本。游戏自身的编码、代码/数据结构、功能语义与存档仍须逐项分析。

## 直接交给 AI

| 任务 | 完整提示词 |
|---|---|
| Windows 工具环境初始化 | [00_BOOTSTRAP_ENVIRONMENT.txt](prompts/00_BOOTSTRAP_ENVIRONMENT.txt) |
| Linux 工具环境初始化 | [00_BOOTSTRAP_ENVIRONMENT_LINUX.txt](prompts/00_BOOTSTRAP_ENVIRONMENT_LINUX.txt) |
| 指定游戏项目初始化 | [01_INITIALIZE.txt](prompts/01_INITIALIZE.txt) |
| 汉化 | [02_LOCALIZE.txt](prompts/02_LOCALIZE.txt) |
| BUG 修复 | [03_FIX_BUG.txt](prompts/03_FIX_BUG.txt) |
| 游戏改版：功能实现与交付 | [04_MOD_GAME.txt](prompts/04_MOD_GAME.txt) |
| 未知机制/金手指只读调查 | [05_INVESTIGATE_MECHANIC.txt](prompts/05_INVESTIGATE_MECHANIC.txt) |
| 已有改版移植或补丁组合 | [06_PORT_OR_COMBINE_MODS.txt](prompts/06_PORT_OR_COMBINE_MODS.txt) |
| 字体选择、缺字检查与接入 | [07_FONT_SETUP.txt](prompts/07_FONT_SETUP.txt) |

提示词是通用流程，不内置某款游戏的哈希、地址或补丁；使用前填写具体项目与授权范围。初始化工具不启动游戏任务，也不恢复暂停项目。

## Windows 初始化

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Initialize_Environment.ps1
```

也可双击 `Initialize_Environment.cmd`。不需要管理员权限，不修改系统 PATH、注册表或全局执行策略。便携 Python、Arm 工具链、RGBDS、官方 mGBA 安装到 `runtime/`，官方 URL 与完整 SHA-256 在 [Windows 锁文件](dependencies.lock.json)。

已有缓存可加 `-CacheDirectory "D:\ROM_AI_CACHE"`。安装/归档身份不符时保留文件并报错，不覆盖未知目录。

初始化后：

```powershell
.\python.cmd tools\romkit.py identity "D:\ROMs\game.gba"
.\python.cmd tools\romkit.py init "D:\ROMs\game.gba" --platform gba --project "workspace\projects\my_game"
.\python.cmd tools\verify_package.py
```

`Open_AI_Shell.cmd` 打开本地工具终端，`Open_mGBA.cmd` 启动官方图形版。只使用隔离 ROM/SAV 副本。

## Linux 初始化

需要 **Bash、已有 Python 3.12+、x86_64/glibc**。不自动安装系统包，不需要 sudo 或 FUSE；当前实测环境和限制见 [验证范围](docs/VALIDATION_SCOPE.txt)。

```bash
bash Initialize_Environment.sh
bash python.sh tools/romkit.py identity "/path/game.gba"
bash python.sh tools/romkit.py init "/path/game.gba" --platform gba --project "workspace/projects/my_game"
bash python.sh tools/verify_package.py
```

依赖存放在独立的 `runtime/linux/`，来自 [Linux 锁文件](dependencies.linux.lock.json)，与 Windows 并存。缓存可用 `--cache-dir "/path/with spaces/cache"`。`bash Open_AI_Shell.sh` 打开工具终端，`bash Open_mGBA.sh` 在有显示服务时启动官方 AppImage。

详见 [Linux 使用与故障说明](docs/LINUX_SETUP.txt)。ARM64、musl/Alpine、macOS 暂无自动安装支持；WSL2 上的 Linux 测试单独标记。无显示时可做工具链自测，版本探测不代表图形游戏验收。

GB/GBC 的 `--platform` 改为 `gb` / `gbc`。`init` 可加 `--save "<SAV路径>"`；已有项目不能覆盖初始化。

## 游戏改版与汉化指南

- [改版工作流](docs/MODDING_WORKFLOW.txt)：需求规格、机制追踪、平台 Hook、注入所有权、组合/移植、存档与交付；参考 SHARE 的有效方法重新整理，未复制游戏补丁或私有工程。
- [改版规格模板](templates/MOD_SPEC_TEMPLATE.txt) / [改版用例矩阵](templates/MOD_TEST_MATRIX.tsv)。
- [GB/GBC 与 GBA 的区别](docs/PLATFORM_GUIDE.txt)：SM83/bank 与 ARM7TDMI/ARM/Thumb 分开。
- [汉化扩容与验收](docs/LOCALIZATION_WORKFLOW.txt)：字库、控制码、指针、布局、原生命名与保存。
- [依赖来源与环境](docs/DOWNLOADS_AND_ENVIRONMENT.txt) / [可选 mGBA 后端](docs/MGBA_AI_GUIDE.txt)。
- [验证范围](docs/VALIDATION_SCOPE.txt) / [全部模板](templates/)。
- [格兰宝空间重叠案例](docs/cases/GURANBO_OVERLAP.txt)：独立案例，不是通用默认参数。

只检查受当前改动影响的项目，沿用未受影响的通过证据；不默认完整通关。静态、受控诊断、正常模拟器路径、普通保存/新进程读回和真机分别报告。

`romkit.py patch` 仅处理等长定点写入；不自动汇编/重定位、扩 ROM、判断空间所有权、证明补丁语义或生成 IPS/BPS。复杂项目须保留自己的源码构建器、依赖与验证。

## 中文字体与字模

仓库内已附 Fusion Pixel 8/10/12px、GNU Unifont 16px，以及用户指定的 `400.ttf`（MuzaiPixel）原件、原点阵源和 8×12 BDF 子集。无需安装系统字体或额外模块。字体版本、覆盖、来源与完整 SHA-256 见 [字体目录](fonts/FONT_CATALOG.json) 和 [来源记录](fonts/FONT_SOURCES.json)。

`400.ttf` 完整保留；其无裁切 BDF 子集含 15,764 个 Unicode 字形，另 168 个超格/悬挂字形仍在原件中。转换子集使用名称 ROM Toolkit 400 Grid12，范围见 [400 字体说明](docs/FONT_400_README.txt)。

初始化后，在仓库根目录运行：

```powershell
# Windows
.\python.cmd tools/font_tool.py verify-assets
.\python.cmd tools/font_tool.py check --font fonts/user-provided/400-native-8x12.bdf --chars-file fonts/SAMPLE_CHARACTERS.txt
```

```bash
# Linux
bash python.sh tools/font_tool.py verify-assets
bash python.sh tools/font_tool.py check --font fonts/user-provided/400-native-8x12.bdf --chars-file fonts/SAMPLE_CHARACTERS.txt
```

工具支持逐像素预览、缺字检查、1bpp / GB-GBC 2bpp / GBA 4bpp 导出，见 [字体操作指南](docs/FONT_USAGE.txt) 与 [预览](font_previews/)。导出的 slot 需要项目码表映射；这些检查不代表游戏内字体、布局或存档已验收。字体原版权和许可保存在 [licenses/fonts](licenses/fonts/)。

## 可选无头扩展

官方 mGBA 不保证定制暂停逐帧、认证 TCP、私有 GDB 接口。`tools/windows_mgba/` 只提供依赖特定 Windows 后端的脚本，当前不分发定制二进制或尚未整理的修改源码。Linux 未提供对应定制后端。

Windows 用户自行取得来源、许可、版本匹配的后端后，按 [构建与兼容性说明](tools/windows_mgba/BUILD_NOTES.md) 单独验证：

```powershell
.\python.cmd tools\check_environment.py --require-headless
.\python.cmd tools\self_test.py --with-headless
```

默认自测只覆盖工具链、自制构建和补丁保护，模拟器功能标记 `not_run`；缺少可选后端不会冒充已通过。

## 源码、测试与许可

源码测试仅用合成数据与自制样例，不需要商业 ROM：

```bash
# Linux；Windows 对应 .\python.cmd -m unittest discover -s tests -v
bash python.sh -m unittest discover -s tests -v
```

字体资源与格式检查：Windows 运行 `.\python.cmd tools/test_font_tool.py`；Linux 运行 `bash python.sh tools/test_font_tool.py`。字体清单校验使用 `tools/font_tool.py verify-assets`。

原创代码、文档、提示词、模板与自制示例采用 [MIT](LICENSE)；所附第三方字体及其衍生字模遵从各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。

仓库不包含商业 ROM、BIOS、玩家 SAV、即时状态、令牌、运行会话或第三方程序包。`runtime/`、`workspace/`、`reports/` 与缓存都排除在 Git 外。请仅处理自己有权使用的输入。

这是辅助工具和工作流程，不是自动完成任意游戏汉化或改版的程序。
