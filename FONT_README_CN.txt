中文字库与字模工具 · 2026-10-16

仓库已携带可直接读取的字体文件，无需安装系统字体或额外 Python 模块。
- Fusion Pixel 8/10/12px zh-Hans：BDF 点阵与 TTF。
- GNU Unifont 16px：HEX 点阵与 OTF。
- 用户指定 400.ttf（MuzaiPixel）：完整原件、原点阵源、8x12 无裁切 BDF 子集。
来源、校验与覆盖统计见 fonts/FONT_SOURCES.json 和 fonts/FONT_CATALOG.json；原版权与许可在 licenses/fonts。

先按 README.md 初始化对应系统环境，再使用本仓库本地 Python：
Windows PowerShell：.\python.cmd tools/font_tool.py catalog
Linux：bash python.sh tools/font_tool.py catalog
上述命令把 catalog 换成 verify-assets 即可核对字体相关文件。

操作指南：docs/FONT_USAGE.txt；400.ttf 的原件/子集区别：docs/FONT_400_README.txt。
AI 接入提示词：prompts/07_FONT_SETUP.txt。
预览：font_previews/all_sizes.png 和 font_previews/400-muzaipixel-8x12.png。
格式样本：font_examples，只有字模，不含游戏 ROM。

字模工具支持 BDF/HEX，不直接栅格化任意 TTF/OTF。缺字、裁切与已有输出均拒绝；10/12px 标准图块留白补齐，不拉伸。
字模 slot 不是游戏编码。接入前仍须确认码表、控制码、字宽、容量、指针、bank、缓存和项目占用；预览/回读通过不代表游戏内验收。
每个字体及其转换字模继续遵从自身许可，根目录 MIT 不替代字体许可。400.ttf 原件保持完整，转换子集另用名称 ROM Toolkit 400 Grid12。
