400.ttf 字体补充 · 2026-10-16

原文件：用户提供的 400.ttf。
包内原件：fonts/user-provided/400.ttf。逐字节保留，未修改、重命名字体内部名称或重新生成原 TTF。
内部名称：MuzaiPixel（目哉像素），Regular；版本 2.0.20241013。
SHA-256：e07ef0f7b26991436f600e414ee5286164bd5ea1d779eb8914975d69af23e6f8。
已核对：与同版本官方 MZPXorig.ttf 字节完全一致；没有用官方下载文件替换用户原件。
版权、保留字体名和 SIL OFL 1.1：licenses/fonts/MuzaiPixel-OFL.md；原 TTF 名称/版权信息另附 JSON。

便于现有字模工具使用的点阵
fonts/user-provided/400-native-8x12.bdf：8x12 格的便利子集，不缩放、不裁切原始笔画。
原字体名 MuzaiPixel 为保留字体名，转换子集使用新名字 ROM Toolkit 400 Grid12。
官方原始点阵源 fonts/user-provided/400-upstream-source.kbitx 同包保留。
原点阵源共有15,932条Unicode记录，便利子集保留15,764条；另168条因悬挂、超过8x12高度/宽度或字宽超格，未进入该便利BDF。
这些字符仍完整保留在原400.ttf和原点阵源中。排除清单：400-native-8x12-excluded.json。
不能把BDF子集当作原TTF的全量替代；目标译文必须先检查缺字，需要超格字符时按实际游戏字宽与窗口另行处理。
典型汉字步进8像素，高12像素；西文步进可能不同，按glyphs.json的source_advance处理。

使用（仓库根目录，先按 README.md 初始化）
python tools/font_tool.py check --font fonts/user-provided/400-native-8x12.bdf --chars-file fonts/SAMPLE_CHARACTERS.txt
python tools/font_tool.py export --font fonts/user-provided/400-native-8x12.bdf --chars-file fonts/SAMPLE_CHARACTERS.txt --format gb2 --output-dir workspace/output/font400_gb2
Windows PowerShell 将 python 换成 .\python.cmd；Linux 将 python 换成 bash python.sh。
可选格式还有 mono1、gba4。mono1原格8x12每字12字节；标准图块格式会留白补齐到8x16，不把字体拉伸。
预览：font_previews/400-muzaipixel-8x12.png。

复现点阵转换
python tools/kbitx_to_bdf.py fonts/user-provided/400-upstream-source.kbitx --output workspace/output/400-rebuilt.bdf --excluded workspace/output/400-excluded.json
所有输出必须为新文件。原TTF和原点阵源保持不变；转换字模也适用同一OFL许可与原版权要求。
已将源点阵15,932条Unicode记录的每个像素与原400.ttf原生100字形单位网格上的轮廓填充逐字形对照，全部一致。
此检查仅证明字模来源/转换一致，不证明游戏码表、布局、缓存、取名或保存功能已接入。
