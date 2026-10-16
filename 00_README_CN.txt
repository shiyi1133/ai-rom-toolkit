AI ROM Toolkit · 公开源码版

从 README.md 开始。首次使用可将 prompts/00_BOOTSTRAP_ENVIRONMENT.txt 整段交给 AI，或运行 Initialize_Environment.cmd。
本仓库以源码、指南、模板和自制示例为主体；Python、Arm 工具链、RGBDS、官方 mGBA 由初始化脚本按 dependencies.lock.json 下载并校验到本地 runtime。
不需要管理员权限，不修改系统 PATH 或注册表。已有项目、ROM、玩家存档和历史保持原样。
定制无头 mGBA 后端为可选外部组件，当前不随仓库提供；详情见 README.md 和 docs/MGBA_AI_GUIDE.txt。
