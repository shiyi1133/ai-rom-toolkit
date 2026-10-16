-- Public source edition: optional control script; custom backend is not bundled.
-- Historical compatibility notes below do not validate official runtime builds.
-- See docs/MGBA_AI_GUIDE.txt and THIRD_PARTY_NOTICES.md.

-- ============================================================================
-- mgba_server.lua — mGBA 常驻 TCP 调试服务（修正版，2026-08-26 全量实测）
--
-- 运行于 mgba-headless（0.11-dev，commit fa977ccc）内部，供外部 AI/工具经
-- TCP 文本协议驱动模拟器。socket 调用约定为 OO 实例方法风格（经 nikouu/mGBA-http
-- 参考实现与本环境实测确认），emu:* 方法面经 probe 实测（见 docs/AI调用调试服务指南.md）。
--
-- 启动：
--   mgba-headless --script mgba_server.lua [-g] rom.gba
--   （推荐用 scripts/start-gba-service.sh，含就绪探测与日志管理）
--
-- 协议（每行一条命令，\n 结尾；数值带 0x 前缀按十六进制，无前缀按十进制）：
--   PING                          -> PONG
--   READ8|READ16|READ32 0xADDR    -> OK HH
--   READBLOCK 0xADDR LEN          -> OK addr=... length=... frame=... sha256=... data=...
--   DUMPBLOCK 0xADDR LEN PATH     -> OK ... path=...（仅 tooling/analysis；LEN<=0x10000）
--   WRITE8|WRITE16|WRITE32 0xADDR 0xVAL -> OK
--   RANGE 0xADDR 0xLEN            -> OK <hex 串>        (len <= 0x10000)
--   WRITERANGE 0xADDR <hex 串>    -> OK
--   REG <名>                      -> OK 0xXXXXXXXX       (r0-r15/cpsr/spsr)
--   WREG <名> 0xVAL               -> OK
--   KEYS 0xMASK [帧数]            -> OK   按住 N 帧后自动松开
--   KEYDOWN 0xMASK                -> OK   持续按下（跨连接保持）
--   KEYUP 0xMASK                  -> OK   释放指定持续按键
--   KEYSTATE                      -> OK ... 查询实际/持续/定时按键与队列
--   WAIT <帧数>                   -> OK <当前帧计数>  同步等待 N 帧后响应（时序推理请用帧！）
--   RESET                         -> OK
--   FRAMES                        -> OK <帧计数>
--   SHOT <绝对路径.png>           -> OK
--   QUIT                          -> BYE  关闭连接
--   LOAD <绝对路径.gba>           -> OK   热切换 ROM（无需重启进程，已实测）
--   SAVESLOT <槽号>               -> OK   存即时存档到 savestatePath（GDB 换挡中转用）
--   SAVESTATE <路径.ss*>          -> OK   存即时存档到指定文件（路径支持 ~ 前缀）
--   LOADSLOT <槽号>               -> OK   读即时存档（savestatePath 下的 <rom名>.ss<槽>）
--   LOADSTATE <路径.ss*>          -> OK   读即时存档文件（路径支持 ~ 前缀）
--   TRACE_PC_START START END MAX  -> OK   tooling-only 有界只读 PC 跟踪
--   TRACE_PC_START A,B,C MAX      -> OK   跟踪非连续偶数代码入口
--   TRACE_PC_RESULT|TRACE_PC_STOP -> OK   查询/停止，JSONL 位于 tooling/analysis
--   ROM                           -> OK <路径>  当前 ROM（初始自 last-rom.txt）
--   错误统一返回: ERR <说明>
--
-- 按键位掩码: A=0x001 B=0x002 SELECT=0x004 START=0x008
--             RIGHT=0x010 LEFT=0x020 UP=0x040 DOWN=0x080 R=0x100 L=0x200
--
-- 已知约束（见指南文档）：
--   * 默认运行时 socket 事件按帧派发；原生帧门控暂停时由 headless idle 回调继续轮询；
--   * GDB 会话不运行原生帧门控，核心挂起期间本通道仍冻结，GDB 退出后自动恢复；
--   * emu:quit / emu:pause 在本构建不存在，退出由外部进程管理（SIGTERM）。
-- ============================================================================

-- 端口/绑定地址由环境变量注入（多实例隔离用），默认 127.0.0.1:4114
local HOST = os.getenv("GBA_HOST") or "127.0.0.1"
local PORT = tonumber(os.getenv("GBA_PORT") or "4114")
local SESSION_TOKEN = os.getenv("GBA_SESSION_TOKEN") or ""
local ALLOW_PC_TRACE = os.getenv("GBA_ALLOW_PC_TRACE") == "1"
-- The custom headless entry does not autoload the ordinary save file.
-- The manager supplies only the isolated copy, never the user's original SAV.
local isolated_save = os.getenv("ROM_TOOLKIT_SAVE") or ""
if isolated_save ~= "" then
    if not emu:loadSaveFile(isolated_save, false) then
        error("Could not load the isolated ordinary save file")
    end
end

-- 前置声明：WAIT 帧回调（定义在下方）需要调用 send_all，Lua 无函数提升，
-- 必须在所有使用点之前声明该局部变量。
local send_all
local process_buffer
local resume_socket
local cleanup

----------------------------------------------------------------------------
-- 工具函数（兼容 Lua 5.4；mGBA 内置无 os/sleep，全部依赖帧回调）
----------------------------------------------------------------------------
local HEX = "0123456789ABCDEF"

local function hex2num(s)
    s = tostring(s)
    if s:match("^0[xX]") then return tonumber(string.sub(s, 3), 16) end
    return tonumber(s, 10)
end

local function tohex(n, digits)
    local d = digits or 8
    n = math.floor(n)
    if n < 0 then n = n + 4294967296 end
    local out = {}
    for i = 1, d do
        out[i] = string.sub(HEX, (n % 16) + 1, (n % 16) + 1)
        n = math.floor(n / 16)
    end
    local s = ""
    for i = d, 1, -1 do s = s .. out[i] end
    return s
end

-- Pure Lua 5.4 SHA-256, used for auditable read-only block responses and trace
-- artifacts. Keeping it in-process avoids shell execution from the service.
local SHA256_K = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
}
local function ror(x, n) return ((x >> n) | (x << (32 - n))) & 0xffffffff end
local function sha256(data)
    local bitlen = #data * 8
    data = data .. string.char(0x80)
    data = data .. string.rep("\0", (56 - (#data % 64)) % 64)
    local hi, lo = math.floor(bitlen / 4294967296), bitlen & 0xffffffff
    data = data .. string.char((hi>>24)&255,(hi>>16)&255,(hi>>8)&255,hi&255,
                              (lo>>24)&255,(lo>>16)&255,(lo>>8)&255,lo&255)
    local h = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}
    for off = 1, #data, 64 do
        local w = {}
        for i = 0, 15 do
            local a,b,c,d = data:byte(off+i*4, off+i*4+3)
            w[i] = ((a<<24)|(b<<16)|(c<<8)|d) & 0xffffffff
        end
        for i = 16, 63 do
            local s0 = ror(w[i-15],7) ~ ror(w[i-15],18) ~ (w[i-15]>>3)
            local s1 = ror(w[i-2],17) ~ ror(w[i-2],19) ~ (w[i-2]>>10)
            w[i] = (w[i-16] + s0 + w[i-7] + s1) & 0xffffffff
        end
        local a,b,c,d,e,f,g,hh = table.unpack(h)
        for i = 0, 63 do
            local s1 = ror(e,6) ~ ror(e,11) ~ ror(e,25)
            local ch = (e & f) ~ ((~e) & g)
            local t1 = (hh + s1 + ch + SHA256_K[i+1] + w[i]) & 0xffffffff
            local s0 = ror(a,2) ~ ror(a,13) ~ ror(a,22)
            local maj = (a & b) ~ (a & c) ~ (b & c)
            local t2 = (s0 + maj) & 0xffffffff
            hh,g,f,e,d,c,b,a = g,f,e,(d+t1)&0xffffffff,c,b,a,(t1+t2)&0xffffffff
        end
        h[1]=(h[1]+a)&0xffffffff; h[2]=(h[2]+b)&0xffffffff
        h[3]=(h[3]+c)&0xffffffff; h[4]=(h[4]+d)&0xffffffff
        h[5]=(h[5]+e)&0xffffffff; h[6]=(h[6]+f)&0xffffffff
        h[7]=(h[7]+g)&0xffffffff; h[8]=(h[8]+hh)&0xffffffff
    end
    local out = {}; for i=1,8 do out[i]=tohex(h[i],8):lower() end
    return table.concat(out)
end

local function readable_block(addr, length, maximum)
    if not addr or not length or length < 1 or length > maximum or length % 1 ~= 0 then return nil, "BADARGS" end
    local last = addr + length - 1
    if last < addr then return nil, "BADRANGE" end
    local ranges = {
        {0x02000000,0x0203ffff}, {0x03000000,0x03007fff},
        {0x04000000,0x04000057}, {0x04000120,0x04000131}, {0x04000200,0x0400020b},
        {0x08000000,0x09ffffff}
    }
    local platform = os.getenv("ROM_TOOLKIT_PLATFORM") or "GBA"
    if platform == "GB" or platform == "GBC" then ranges = {{0x0000, 0xffff}} end
    for _, r in ipairs(ranges) do if addr >= r[1] and last <= r[2] then return true end end
    return nil, "UNSUPPORTED_RANGE"
end

local function read_block(addr, length)
    local chunks, part = {}, {}
    for i=0,length-1 do
        part[#part+1] = string.char(emu:read8(addr+i))
        if #part == 4096 then chunks[#chunks+1]=table.concat(part); part={} end
    end
    if #part > 0 then chunks[#chunks+1]=table.concat(part) end
    return table.concat(chunks)
end

-- 展开 ~ 前缀：TCP 协议里 shell 不会展开 ~，统一在服务端处理
local function expand_path(p)
    local home = os.getenv("HOME")
    if home and (p == "~" or p:sub(1, 2) == "~/") then
        return home .. p:sub(2)
    end
    return p
end

-- 前置声明：last_state_log_reason 运行时调用 service_dir（定义在本文件后方）。
-- Lua 无函数提升，必须先声明局部变量，否则编译期把引用解析为全局（nil）。
local service_dir

-- 失败原因提取：mGBA 把拒绝载入/保存的具体原因写进 GBA_LOG（GBA_STATE WARN 行，
-- 如 BIOS 不匹配/游戏不符/损坏/ROM 尺寸不同）。失败后读日志尾部，把最后一条
-- "Savestate + 拒绝关键字"行原样带回给调用方（拒绝发生在 loadStateFile 返回前，
-- 且 stdbuf 行缓冲保证该行已落盘）。after 参数 = 命令执行前的日志字节位置，
-- 只返回该位置之后新写入的原因行，避免带回上一次失败的陈旧行。
local function log_size_now()
    local log_path = os.getenv("GBA_LOG") or (service_dir() .. "/logs/mgba.log")
    local f = io.open(log_path, "r")
    if not f then return nil end
    local size = f:seek("end") or 0
    f:close()
    return size
end

local function last_state_log_reason(after)
    local log_path = os.getenv("GBA_LOG") or (service_dir() .. "/logs/mgba.log")
    local f = io.open(log_path, "r")
    if not f then return nil end
    local size = f:seek("end") or 0
    local start = after or 0
    if size - start > 262144 then start = size - 262144 end
    if start >= size then
        f:close()
        return nil
    end
    f:seek("set", start)
    local tail = f:read("*a")
    f:close()
    if not tail then return nil end
    local best = nil
    for line in tail:gmatch("[^\r\n]+") do
        -- 注意：Lua 模式无 "|" 交替符，须逐关键字判断
        local hit = line:find("Savestate") and (
            line:find("different") or line:find("corrupt") or line:find("Invalid")
            or line:find("invalid") or line:find("no game") or line:find("Failed to load"))
        if hit then
            best = line:gsub("%s+$", "")
        end
    end
    return best
end

-- 防御包装：原因提取绝不抛出——任何异常都降级为通用提示，并记入服务日志。
local function safe_state_reason(after)
    local ok, got = pcall(last_state_log_reason, after)
    if ok and got then return got end
    if not ok then console:log("[mgba_server] state-log-reason err: " .. tostring(got)) end
    return "see mgba.log"
end

----------------------------------------------------------------------------
-- 帧计数 + 按键队列 + 崩溃哨兵 + 当前 ROM 记忆
----------------------------------------------------------------------------
local frame_count = 0
local crashed = false
local current_rom = nil
local in_idle_service = false
local state_queue = {}
local trace = { active=false, ids={}, hits=0, max_hits=0, path=nil, bytes=0, stop_requested=false }

local function core_frame()
    local ok, value = pcall(emu.currentFrame, emu)
    return (ok and value) or frame_count
end

-- last-rom 持久化路径：与 start-gba-service.sh 的 GBA_SERVICE_DIR 约定一致
service_dir = function()
    return os.getenv("GBA_SERVICE_DIR") or (os.getenv("HOME") .. "/gba-runtime/main")
end

local function last_rom_file()
    return service_dir() .. "/last-rom.txt"
end

local function persist_rom(path)
    local f = io.open(last_rom_file(), "w")
    if f then
        f:write(path)
        f:close()
    end
end

-- 启动时恢复上次 ROM 的记忆（仅用于 ROM 查询，实际加载由启动脚本决定）
do
    local f = io.open(last_rom_file(), "r")
    if f then
        current_rom = f:read("*l")
        f:close()
        if current_rom == "" then current_rom = nil end
    end
end

callbacks:add("frame", function()
    frame_count = frame_count + 1
end)

local function trace_stop()
    for _, id in ipairs(trace.ids) do pcall(emu.clearBreakpoint, emu, id) end
    trace.ids = {}; trace.active = false; trace.stop_requested = false
end

callbacks:add("frame", function()
    if trace.stop_requested then trace_stop() end
end)

local key_queue = {}
local manual_key_mask = 0
local timed_key_mask = 0

local function apply_keys()
    emu:setKeys(manual_key_mask | timed_key_mask)
end

local function release_all_keys()
    key_queue = {}
    manual_key_mask = 0
    timed_key_mask = 0
    emu:setKeys(0)
end

local function start_next_timed_key()
    local k = key_queue[1]
    if k then
        k.started_at = frame_count
        timed_key_mask = k.mask
    else
        timed_key_mask = 0
    end
    apply_keys()
end

callbacks:add("frame", function()
    if #key_queue > 0 then
        local k = key_queue[1]
        -- KEYS 在命令处理时立即为下一模拟帧置键。只有帧计数真正前进后才扣减，
        -- 因而 KEYS mask N 会精确保持 N 个完整模拟帧（旧实现实际只有 N-1）。
        if frame_count > k.started_at then
            k.frames = k.frames - 1
            k.started_at = frame_count
        end
        if k.frames <= 0 then
            table.remove(key_queue, 1)
            start_next_timed_key()
        end
    end
end)

-- WAIT 队列：{sock=..., frames=...}，每帧递减，到 0 时响应。
-- 注意：默认 GBA_SPEED=1（约 60fps），0 可不限速；帧计数始终是稳定时序单位。
local wait_queue = {}
callbacks:add("frame", function()
    if #wait_queue > 0 then
        local i = 1
        while i <= #wait_queue do
            local w = wait_queue[i]
            if frame_count > w.started_at then
                w.frames = w.frames - 1
                w.started_at = frame_count
            end
            if w.frames <= 0 then
                table.remove(wait_queue, i)
                resume_socket(w.sock, "OK " .. tostring(frame_count) .. "\n")
            else
                i = i + 1
            end
        end
    end
end)

-- SHOT 串行队列：每帧只处理一个。同一帧回调内连续多次截图会取到无效
-- 帧缓冲（产出 0 字节文件，实测复现），串行化后每次截图都在稳定的帧边界执行。
-- 原生暂停时由 idle 回调处理当前稳定帧，并用 cooldown 避免同一帧密集截图。
local shot_queue = {}
local idle_shot_cooldown = 0

local function try_shot(w)
    pcall(emu.screenshot, emu, w.path)
    local f = io.open(w.path, "r")
    local sz = 0
    if f then
        sz = f:seek("end") or 0
        f:close()
    end
    if sz > 0 then
        table.remove(shot_queue, 1)
        resume_socket(w.sock, "OK\n")
    else
        w.tries = w.tries + 1
        if w.tries >= 3 then
            table.remove(shot_queue, 1)
            resume_socket(w.sock, "ERR SHOTFAILED\n")
        else
            w.wait = 2
        end
    end
end

callbacks:add("frame", function()
    if #shot_queue > 0 then
        local w = shot_queue[1]
        if w.wait > 0 then
            w.wait = w.wait - 1
        else
            try_shot(w)
        end
    end
end)

callbacks:add("crashed", function()
    crashed = true
    console:log("[mgba_server] CRASHED 模拟器崩溃（外部可查日志/CRASHED 命令）")
end)

----------------------------------------------------------------------------
-- 命令处理
----------------------------------------------------------------------------
local function handle_line(line, sock)
    local cmd, rest = line:match("^(%S+)%s*(.-)%s*$")
    cmd = cmd and cmd:upper() or ""
    local addr, val

    if cmd == "PING" then
        return "PONG"

    elseif cmd == "CRASHED" then
        return crashed and "OK 1" or "OK 0"

    elseif cmd == "READ8" or cmd == "READ16" or cmd == "READ32" then
        addr = hex2num(rest)
        if not addr then return "ERR BADADDR" end
        if cmd == "READ8"  then return "OK " .. tohex(emu:read8(addr), 2) end
        if cmd == "READ16" then return "OK " .. tohex(emu:read16(addr), 4) end
        return "OK " .. tohex(emu:read32(addr), 8)

    elseif cmd == "READBLOCK" or cmd == "DUMPBLOCK" then
        local a, n, path = rest:match("^(%S+)%s+(%S+)%s*(.-)$")
        addr, val = hex2num(a), hex2num(n)
        local allowed, why = readable_block(addr, val, cmd=="READBLOCK" and 0x4000 or 0x10000)
        if not allowed then return "ERR " .. why end
        local data = read_block(addr, val)
        local digest = sha256(data)
        local meta = "addr=0x"..tohex(addr,8).." length="..val.." frame="..core_frame().." sha256="..digest
        if cmd == "DUMPBLOCK" then
            path = expand_path(path or "")
            local root = service_dir() .. "/analysis/"
            if path:sub(1,#root) ~= root or path:find("..",1,true) then return "ERR BADPATH" end
            local f = io.open(path, "wb"); if not f then return "ERR OPENFAILED" end
            local ok = f:write(data); f:close(); if not ok then return "ERR WRITEFAILED" end
            return "OK " .. meta .. " path=" .. path
        end
        local hex = {}; for i=1,#data do hex[i]=tohex(data:byte(i),2) end
        return "OK " .. meta .. " data=" .. table.concat(hex)

    elseif cmd == "WRITE8" or cmd == "WRITE16" or cmd == "WRITE32" then
        addr, val = rest:match("^(%S+)%s+(%S+)$")
        addr, val = hex2num(addr), hex2num(val)
        if not (addr and val) then return "ERR BADARGS" end
        if cmd == "WRITE8"  then emu:write8(addr, val) end
        if cmd == "WRITE16" then emu:write16(addr, val) end
        if cmd == "WRITE32" then emu:write32(addr, val) end
        return "OK"

    elseif cmd == "RANGE" then
        addr, val = rest:match("^(%S+)%s+(%S+)$")
        addr, val = hex2num(addr), hex2num(val)
        if not (addr and val) then return "ERR BADARGS" end
        if val > 0x10000 then return "ERR TOOBIG" end
        local out = {}
        for i = 0, val - 1 do
            out[#out + 1] = tohex(emu:read8(addr + i), 2)
        end
        return "OK " .. table.concat(out)

    elseif cmd == "WRITERANGE" then
        addr, val = rest:match("^(%S+)%s+(%S+)$")
        addr = hex2num(addr)
        val = val or ""
        if not addr then return "ERR BADARGS" end
        if #val > 0x20000 or #val % 2 ~= 0 then return "ERR BADDATA" end
        local i = 0
        while i + 2 <= #val do
            emu:write8(addr + i / 2, tonumber(string.sub(val, i + 1, i + 2), 16))
            i = i + 2
        end
        return "OK"

    elseif cmd == "REG" then
        local ok, v = pcall(emu.readRegister, emu, rest)
        if not ok or v == nil then return "ERR BADREG" end
        return "OK " .. tohex(v, 8)

    elseif cmd == "WREG" then
        local name, v = rest:match("^(%S+)%s+(%S+)$")
        v = hex2num(v)
        if not (name and v) then return "ERR BADARGS" end
        local ok = pcall(emu.writeRegister, emu, name, v)
        if not ok then return "ERR BADREG" end
        return "OK"

    elseif cmd == "KEYS" then
        local mask, frames = rest:match("^(%S+)%s*(%S*)$")
        mask = hex2num(mask)
        frames = tonumber(frames) or 3
        if not mask or mask < 0 or mask > 0x3FF or mask % 1 ~= 0 or frames < 1
            or frames > 0x1FFFFF or frames % 1 ~= 0 then
            return "ERR BADARGS"
        end
        key_queue[#key_queue + 1] = { mask = mask, frames = frames, started_at = nil }
        if #key_queue == 1 then start_next_timed_key() end
        return "OK"

    elseif cmd == "KEYDOWN" then
        local mask = hex2num(rest)
        if not mask or mask < 0 or mask > 0x3FF or mask % 1 ~= 0 then return "ERR BADARGS" end
        manual_key_mask = manual_key_mask | mask
        apply_keys()
        return "OK"

    elseif cmd == "KEYUP" then
        local mask = hex2num(rest)
        if not mask or mask < 0 or mask > 0x3FF or mask % 1 ~= 0 then return "ERR BADARGS" end
        manual_key_mask = manual_key_mask & (0x3FF ~ mask)
        apply_keys()
        return "OK"

    elseif cmd == "KEYSTATE" then
        local remaining = 0
        if key_queue[1] then remaining = key_queue[1].frames end
        local active = manual_key_mask | timed_key_mask
        local ok, actual = pcall(emu.getKeys, emu)
        if not ok or actual == nil then actual = active end
        return "OK active=0x" .. tohex(actual, 3)
            .. " manual=0x" .. tohex(manual_key_mask, 3)
            .. " timed=0x" .. tohex(timed_key_mask, 3)
            .. " remaining=" .. tostring(remaining)
            .. " queued=" .. tostring(#key_queue)

    elseif cmd == "WAIT" then
        local n = hex2num(rest)
        if not n or n <= 0 or n > 0x1FFFFF or n % 1 ~= 0 then return "ERR BADARGS" end
        wait_queue[#wait_queue + 1] = { sock = sock, frames = n, started_at = frame_count }
        return "__DEFER__"

    elseif cmd == "RESET" then
        emu:reset()
        frame_count = 0
        release_all_keys()
        return "OK"

    elseif cmd == "FRAMES" then
        return "OK " .. tostring(frame_count)

    elseif cmd == "TRACE_PC_START" then
        if (os.getenv("ROM_TOOLKIT_PLATFORM") or "GBA") ~= "GBA" then return "ERR GBA_ONLY" end
        if not ALLOW_PC_TRACE then return "ERR TRACE_DISABLED" end
        if trace.active then return "ERR TRACE_ACTIVE" end
        local first,second,third = rest:match("^(%S+)%s*(%S*)%s*(%S*)$")
        local addresses, m = {}, 10000
        if first and first:find(",",1,true) then
            m=tonumber(second) or 10000
            for item in first:gmatch("[^,]+") do addresses[#addresses+1]=hex2num(item) end
        else
            local s,e=hex2num(first),hex2num(second); m=tonumber(third) or 10000
            if not s or not e or e<s or (e-s)>8190 then return "ERR BADARGS" end
            for address=s&0xfffffffe,e&0xfffffffe,2 do addresses[#addresses+1]=address end
        end
        if #addresses<1 or #addresses>4096 or m<1 or m>100000 then return "ERR BADARGS" end
        for _,address in ipairs(addresses) do
            if not address or address<0x08000000 or address>0x09ffffff then return "ERR BADARGS" end
        end
        trace.active=true; trace.ids={}; trace.hits=0; trace.max_hits=m; trace.bytes=0; trace.stop_requested=false
        trace.path=service_dir().."/analysis/pc-trace.jsonl"
        local f=io.open(trace.path,"w"); if not f then trace.active=false; return "ERR OPENFAILED" end
        local listed={}; for _,address in ipairs(addresses) do listed[#listed+1]='"0x'..tohex(address&0xfffffffe,8)..'"' end
        f:write('{"event":"start","frame":'..core_frame()..',"addresses":['..table.concat(listed,",")..'],"max_hits":'..m..'}\n'); f:close()
        for _,address in ipairs(addresses) do
            local captured=address&0xfffffffe
            local id=emu:setBreakpoint(function()
                if not trace.active then return end
                if trace.hits>=trace.max_hits or trace.bytes>=16777216 then
                    trace.stop_requested=true
                    return
                end
                local function reg(name) local ok,v=pcall(emu.readRegister,emu,name); return ok and v or 0 end
                local cpsr=reg("cpsr")
                local row=('{"frame":%d,"pc":"0x%s","thumb":%s,"lr":"0x%s","r0":"0x%s","r1":"0x%s","r2":"0x%s","r3":"0x%s"}\n'):format(
                    core_frame(),tohex(captured,8),((cpsr&0x20)~=0) and "true" or "false",tohex(reg("lr"),8),tohex(reg("r0"),8),tohex(reg("r1"),8),tohex(reg("r2"),8),tohex(reg("r3"),8))
                local out=io.open(trace.path,"a"); if out then out:write(row); out:close(); trace.bytes=trace.bytes+#row end
                trace.hits=trace.hits+1
                if trace.hits>=trace.max_hits or trace.bytes>=16777216 then trace.stop_requested=true end
            end,captured)
            if not id or id < 0 then trace_stop(); return "ERR DEBUGGER_UNAVAILABLE" end
            trace.ids[#trace.ids+1]=id
        end
        return "OK path="..trace.path.." points="..#trace.ids.." max_hits="..trace.max_hits

    elseif cmd == "TRACE_PC_STOP" then
        trace_stop(); return "OK hits="..trace.hits.." path="..tostring(trace.path)

    elseif cmd == "TRACE_PC_RESULT" then
        return "OK active="..(trace.active and "1" or "0").." hits="..trace.hits.." bytes="..trace.bytes.." frame="..core_frame().." path="..tostring(trace.path)

    elseif cmd == "SHOT" then
        if rest == "" then return "ERR BADPATH" end
        if in_idle_service and frame_count == 0 then return "ERR NOFRAME" end
        rest = expand_path(rest)
        -- 统一走串行队列（每帧一个），避免同帧多次截图取到无效帧缓冲
        shot_queue[#shot_queue + 1] = { sock = sock, path = rest, tries = 0, wait = 1 }
        return "__DEFER__"

    elseif cmd == "QUIT" then
        return nil

    elseif cmd == "LOAD" then
        if rest == "" then return "ERR BADPATH" end
        rest = expand_path(rest)
        local ok, err = pcall(emu.loadFile, emu, rest)
        if not ok then return "ERR " .. tostring(err) end
        frame_count = 0
        release_all_keys()
        crashed = false
        current_rom = rest
        persist_rom(rest)
        console:log("[mgba_server] LOAD " .. rest)
        return "OK"

    elseif cmd == "ROM" then
        return current_rom and ("OK " .. current_rom) or "OK unknown"

    elseif cmd == "SAVESLOT" then
        local slot = hex2num(rest)
        if not slot or slot < 0 or slot > 9 then return "ERR BADARGS" end
        local mark = log_size_now()
        local ok, r = pcall(emu.saveStateSlot, emu, slot)
        if not ok then return "ERR " .. tostring(r) end
        if r == false then return "ERR SAVEFAILED: " .. safe_state_reason(mark) end
        return "OK"

    elseif cmd == "SAVESTATE" then
        if rest == "" then return "ERR BADPATH" end
        rest = expand_path(rest)
        local mark = log_size_now()
        local ok, r = pcall(emu.saveStateFile, emu, rest)
        if not ok then return "ERR " .. tostring(r) end
        if r == false then return "ERR SAVEFAILED: " .. safe_state_reason(mark) end
        return "OK"

    elseif cmd == "LOADSLOT" then
        local slot = hex2num(rest)
        if not slot or slot < 0 or slot > 9 then return "ERR BADARGS" end
        state_queue[#state_queue+1]={sock=sock,kind="slot",value=slot,mark=log_size_now()}
        return "__DEFER__"

    elseif cmd == "LOADSTATE" then
        if rest == "" then return "ERR BADPATH" end
        rest = expand_path(rest)
        state_queue[#state_queue+1]={sock=sock,kind="file",value=rest,mark=log_size_now()}
        return "__DEFER__"

    else
        return "ERR UNKNOWN"
    end
end

-- Savestate restore is intentionally executed after the socket receive callback
-- has unwound. Restoring the core from inside that callback can invalidate the
-- active poll/dispatch state and was observed as a lost response / GDB fd error.
local function process_state_queue()
    if #state_queue == 0 then return end
    local item = table.remove(state_queue, 1)
    local ok, r
    if item.kind == "slot" then ok, r = pcall(emu.loadStateSlot, emu, item.value)
    else ok, r = pcall(emu.loadStateFile, emu, item.value) end
    if not ok then resume_socket(item.sock, "ERR "..tostring(r).."\n"); return end
    if r == false then resume_socket(item.sock, "ERR LOADFAILED: "..safe_state_reason(item.mark).."\n"); return end
    release_all_keys()
    resume_socket(item.sock, "OK\n")
end

callbacks:add("frame", process_state_queue)

----------------------------------------------------------------------------
-- TCP 服务（OO 实例方法约定，实测通过）
----------------------------------------------------------------------------
local MAX_BUF = 65536
local sockets = {}        -- sock -> { buf=..., cbid=..., ebid=..., blocked=... }

send_all = function(sock, data)
    local off = 1
    while off <= #data do
        local sent, serr = sock:send(string.sub(data, off))
        if not sent then
            console:log("[mgba_server] send err: " .. tostring(serr))
            return false
        end
        off = off + sent
    end
    return true
end

cleanup = function(sock)
    local st = sockets[sock]
    if st then
        pcall(sock.remove, sock, st.cbid)
        pcall(sock.remove, sock, st.ebid)
        pcall(sock.close, sock)
        sockets[sock] = nil
        console:log("[mgba_server] client disconnected")
    end
    -- 丢弃该连接的未完成 WAIT 与 SHOT 重试
    for i = #wait_queue, 1, -1 do
        if wait_queue[i].sock == sock then table.remove(wait_queue, i) end
    end
    for i = #shot_queue, 1, -1 do
        if shot_queue[i].sock == sock then table.remove(shot_queue, i) end
    end
    for i = #state_queue, 1, -1 do
        if state_queue[i].sock == sock then table.remove(state_queue, i) end
    end
end

resume_socket = function(sock, response)
    local st = sockets[sock]
    if not st then return end
    if not send_all(sock, response) then
        cleanup(sock)
        return
    end
    st.blocked = false
    process_buffer(sock)
end

process_buffer = function(sock)
    local st = sockets[sock]
    if not st or st.blocked then return end
    while true do
        local line, remaining = st.buf:match("^(.-)\n(.*)$")
        if not line then break end
        st.buf = remaining
        line = line:gsub("\r$", "")
        if SESSION_TOKEN ~= "" and not st.authenticated then
            if line == ("AUTH " .. SESSION_TOKEN) then
                st.authenticated = true
                if not send_all(sock, "OK AUTH\n") then cleanup(sock) end
            else
                send_all(sock, "ERR AUTH\n")
                cleanup(sock)
            end
            return
        end
        local resp = handle_line(line, sock)
        if resp == "__DEFER__" then
            -- WAIT/SHOT 是同一连接内的顺序屏障；完成后 resume_socket 才处理后续行。
            st.blocked = true
            return
        elseif resp then
            if not send_all(sock, resp .. "\n") then
                cleanup(sock)
                return
            end
        else
            send_all(sock, "BYE\n")
            cleanup(sock)
            return
        end
    end
    if #st.buf > MAX_BUF then st.buf = "" end
end

local function on_received(sock)
    local st = sockets[sock]
    if not st then return end
    local chunk, rerr = sock:receive(4096)
    if chunk then
        st.buf = st.buf .. chunk
        process_buffer(sock)
    elseif rerr then
        if rerr ~= socket.ERRORS.AGAIN then
            console:log("[mgba_server] recv err: " .. tostring(rerr))
            cleanup(sock)
        end
    end
end

local server, berr = socket.bind(HOST, PORT)
if not server then
    console:log("[mgba_server] bind failed: " .. tostring(berr))
else
    local ok, lerr = server:listen()
    if not ok then
        console:log("[mgba_server] listen failed: " .. tostring(lerr))
    else
        server:add("received", function()
            local sock, aerr = server:accept()
            if sock then
                local st = { buf = "", blocked = false, authenticated = (SESSION_TOKEN == "") }
                st.cbid = sock:add("received", function() on_received(sock) end)
                st.ebid = sock:add("error", function() cleanup(sock) end)
                sockets[sock] = st
                console:log("[mgba_server] client connected")
            elseif aerr then
                console:log("[mgba_server] accept err: " .. tostring(aerr))
            end
        end)
        console:log("[mgba_server] listening on port " .. PORT)

        -- mGBA 内置 socket 默认把 poll() 挂到 frame 回调。原生帧门控暂停时，
        -- headless 主循环只触发 idle：仅轮询网络和处理稳定帧截图，不触碰
        -- frame_count、WAIT 或定时按键队列。
        local function poll_idle_network()
            server:poll()
            local active = {}
            for sock, _ in pairs(sockets) do active[#active + 1] = sock end
            for _, sock in ipairs(active) do
                if sockets[sock] then sock:poll() end
            end
        end

        callbacks:add("idle", function()
            in_idle_service = true
            local poll_ok, poll_err = pcall(poll_idle_network)
            in_idle_service = false
            if not poll_ok then
                console:log("[mgba_server] idle poll err: " .. tostring(poll_err))
            end

            process_state_queue()
            if trace.stop_requested then trace_stop() end

            if idle_shot_cooldown > 0 then
                idle_shot_cooldown = idle_shot_cooldown - 1
            elseif #shot_queue > 0 then
                try_shot(shot_queue[1])
                idle_shot_cooldown = 2
            end
        end)
    end
end
