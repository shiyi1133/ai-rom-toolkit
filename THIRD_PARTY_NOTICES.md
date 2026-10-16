# 来源与第三方许可

## 本项目

本仓库从作者提供的本地 Windows AI ROM 工具包中选取通用源码、文档、模板和自制测试；公开发布由作者明确授权。未迁入游戏工程、原件、存档、会话、历史运行报告、第三方可执行文件或私有绝对路径。

新增的 Windows/Linux 环境初始化脚本、改版流程/提示词、依赖锁定配置与源码测试，以及本项目原创部分适用根目录 MIT License。

## mGBA 与控制脚本

- 上游：https://github.com/mgba-emu/mgba
- mGBA 采用 MPL-2.0；许可文本保存在 `tools/windows_mgba/MGBA_LICENSE.txt`。
- Python/Lua 控制脚本来自作者自己的本地控制工具，并保留源码中的来源与接口参考记录；脚本与 mGBA 程序分别分发。
- Lua socket 接口实现参考了 Niko 的 [mGBA-http](https://github.com/nikouu/mGBA-http)，其 MIT 许可与署名保存在 `licenses/mGBA-http-MIT.txt`；本仓库没有迁入它的 C# 程序或其第三方依赖。
- 特定定制 mGBA 后端尚未在本仓库分发。未来如分发修改版可执行文件，须同时提供获取对应 MPL 源码/修改的有效方式及构建信息；仅链接未修改的上游源码不足以替代本地修改。

## 外部下载依赖

| 组件 | 来源 | 许可处理 |
|---|---|---|
| CPython | python.org | 保留归档内 Python 与第三方许可 |
| Arm GNU Toolchain | Arm 官方分发 | 各组件遵从归档内 GPL/LGPL/其他许可，不以本项目 MIT 替代 |
| RGBDS | gbdev/rgbds | MIT；原署名见 `licenses/RGBDS_LICENSE.txt` |
| 官方 mGBA | mgba-emu/mgba | MPL-2.0 及归档内依赖许可 |

初始化脚本由用户直接下载到本机，不把这些归档提交到源码仓库。下载校验值是完整性记录；未声明它们均具备独立签名认证。来源、版本和校验依据见 `dependencies.lock.json`（Windows）和 `dependencies.linux.lock.json`（Linux）。

改版工作流参考作者提供的 SHARE 方法文档后重新整理；没有迁入其游戏 ROM、SAV、商业反编译语料、补丁数据或私有二进制。历史项目功能状态不作为本仓库动态验证。
Linux 使用现有系统 Python；本仓库不重新分发 Linux Python。AppImage 保留原始归档及内部许可，用户直接从官方来源下载到 runtime/linux。

## 随仓库提供的字体

字体是可重新分发的资源，各自许可优先适用，根目录 MIT 不替代字体许可。

| 字体 | 版本与内容 | 许可与署名 |
|---|---|---|
| Fusion Pixel | 2026.09.25，zh-Hans 8/10/12px BDF 与 TTF | OFL-1.1；`licenses/fonts/Fusion-Pixel-OFL.txt`，各上游组成字库许可完整保存在 `licenses/fonts/fusion-assets/` |
| GNU Unifont | 17.0.05，HEX 与 OTF | 选择上游双重授权中的 OFL-1.1；原完整许可及字体元数据见 `licenses/fonts/Unifont-LICENSE.txt` 与 `Unifont-Font-Metadata.txt` |
| MuzaiPixel / 400.ttf | 2.0.20241013，用户原件与同版本原 KBITX | OFL-1.1；`licenses/fonts/MuzaiPixel-OFL.md` 与 `400-Font-Metadata.json`；原 TTF 字节未修改 |
| ROM Toolkit 400 Grid12 | 从 MuzaiPixel 原点阵源生成的 8x12 无裁切 BDF 子集 | 沿用 OFL-1.1 和原版权；为遵从保留字体名要求使用新名称，未将衍生子集命名为 MuzaiPixel |

原始来源、版本与 SHA-256 在 `fonts/FONT_SOURCES.json`；子集范围、排除清单与重建命令见 `docs/FONT_400_README.txt`。导出字模时应随结果保留相应许可和署名。
