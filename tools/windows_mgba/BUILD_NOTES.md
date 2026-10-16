# 公开源码版说明

本目录发布控制脚本源码；下面记录的是历史本地后端的兼容性约束，不表示对应 C 源码或二进制已包含在仓库。当前初始化不获取这些定制后端，缺项单独报告。

若未来分发定制二进制，必须先整理相应 MPL 源码修改与可复核构建方法；单靠以下描述及上游版本链接不能替代对应修改源码。

# 构建说明与已知限制

- 基于项目已有 mGBA 0.10.5 源码的 `BUILD_HEADLESS=ON` Windows x64 构建。
- 启用 Headless、Lua scripting、GDB stub、截图和 savestate 支持；不依赖 Qt/SDL 窗口。
- Windows 无头入口补充了 `SocketSubsystemInit()` / `SocketSubsystemDeinit()`，否则 Lua socket 在 Windows 返回 Winsock `10093`。
- 默认/帧门控二进制 SHA-256：`c8cf3ffce8f37c84c3c1ef18f61487b5dcbcae186595ac751ee0a03693a0b6cb`。
- GDB 专用二进制 SHA-256：`bad51e793db0dbe844497382c35790aed7a3a025f96c27f2542bbee1f4fb4e6a`。
- Windows 默认模式把 Linux 私有 FIFO 适配为每实例追加控制文件，并处理 Windows `rename()` 不覆盖目标的问题。
- GDB 专用构建从 `GBA_GDB_PORT` 读取动态端口；上游入口固定 2345，不适合隔离多实例。管理器会按模式自动选取二进制。
- 当前交付采用 Debug 配置。先前 Release 优化构建在 Lua frame callback 注册处失败，仍未作为运行版本。
- `mgba-headless-debug.exe` 是默认帧门控二进制的同一副本，仅保留作构建身份提示。
- MinGW 无头入口不能可靠接收含中文的启动路径。管理器支持中文源 ROM/SAV 名称，因为会先复制到 ASCII 运行目录；分享包和 `--runtime-root` 本身应放在 ASCII 路径。
- `default` Lua/帧门控模式与 `gdb` 模式须分别启动。GDB 单客户端端口不能用普通 TCP readiness 探测，否则会占用 accept 槽。

这些源码级调整仅发生在隔离构建副本，未修改源项目。


## 本工具包的新副本适配（2026-10-13）

- 保持源 SHARE 和两个原始二进制不变；仅修改本包 Python/Lua 副本。
- 按 .gba/.gb/.gbc 保留隔离 ROM 扩展名，GB/GBC READBLOCK/DUMPBLOCK 使用 16 位总线范围。
- PC 跟踪及 GDB 限定 GBA；GDB 与普通 SAV 的组合明确拒绝。
- 拒绝重用已有实例历史；检查无头可执行程序、Lua 与运行目录为 ASCII。
- 普通 SAV 不仅复制，还由 Lua loadSaveFile 显式载入隔离副本；已用三平台自制 RAM 保存标记核验。
- Windows 环境检查使用自定义无头入口的 help/加载检查（它对 --help/--version 返回 usage/1），功能由自测证明。
- 历史本地报告未随公开源码上传；当前验证以 docs/VALIDATION_SCOPE.txt 和本次实际报告为准。商业游戏、全路线、真机和普通保存/冷启动兼容仍须单独验收。
