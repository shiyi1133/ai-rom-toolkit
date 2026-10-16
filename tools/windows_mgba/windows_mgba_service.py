"""Windows-native lifecycle manager for isolated headless mGBA instances."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from mgba_client import send_commands

CREATE_NO_WINDOW = 0x08000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_image(pid: int) -> str | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = ctypes.c_ulong(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return str(Path(buf.value).resolve())
    finally:
        kernel32.CloseHandle(handle)


def process_matches(pid: int, executable: Path) -> bool:
    image = process_image(pid)
    return bool(image and os.path.normcase(image) == os.path.normcase(str(executable.resolve())))


def free_port(preferred: int | None = None) -> int:
    if preferred:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", preferred))
        return preferred
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def free_gdb_port(preferred: int | None = None) -> int:
    if preferred:
        return free_port(preferred)
    for _ in range(256):
        candidate = 23000 + secrets.randbelow(36000)
        try:
            return free_port(candidate)
        except OSError:
            continue
    raise RuntimeError("could not allocate a GDB port below 59000")


def receive_line(sock: socket.socket) -> str:
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return data.decode(errors="replace").strip()


def wait_tcp(port: int, deadline: float) -> None:
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.5):
                return
        except OSError as exc:
            last = exc
            time.sleep(0.1)
    raise TimeoutError(f"port {port} did not become ready: {last}")


def skeleton(instance: Path) -> None:
    for name in ("roms", "saves", "savestates", "screenshots", "analysis", "logs", "records"):
        (instance / name).mkdir(parents=True, exist_ok=True)


def read_session(instance: Path) -> dict:
    return json.loads((instance / "session.json").read_text(encoding="utf-8"))


def read_control_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, PermissionError):
        # The headless process publishes this file with temp-file replacement.
        # On Windows there is a short unlink/rename window in which readers may
        # see no file or ERROR_ACCESS_DENIED. Callers poll, so treat both as a
        # transient state instead of failing the control command.
        return values
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def start(args: argparse.Namespace) -> int:
    root = args.runtime_root.resolve()
    instance = (root / args.instance).resolve()
    if instance.parent != root:
        raise ValueError("instance must be one path component")
    skeleton(instance)
    session_path = instance / "session.json"
    executable = (args.executable or (args.tool_dir / "bin" / (
        "mgba-headless-gdb.exe" if args.mode == "gdb" else "mgba-headless.exe"
    ))).resolve(strict=True)
    if session_path.exists():
        old = read_session(instance)
        if process_matches(int(old["pid"]), executable):
            raise RuntimeError(f"instance is already running: pid {old['pid']}")

    source_rom = args.rom.resolve(strict=True)
    source_save = args.save.resolve(strict=True) if args.save else None
    if args.mode == "gdb" and source_save:
        raise ValueError("GDB mode cannot explicitly load an ordinary SAV in this build; use Lua mode or a verified isolated savestate")
    extension = source_rom.suffix.lower()
    if extension not in (".gba", ".gb", ".gbc"):
        raise ValueError("expected .gba, .gb, or .gbc ROM")
    if args.mode == "gdb" and extension != ".gba":
        raise ValueError("this GDB mode is GBA-only")
    if session_path.exists():
        raise RuntimeError("instance history exists; choose a new instance name")
    if not str(executable).isascii() or not str(args.lua.resolve()).isascii() or not str(instance).isascii():
        raise ValueError("headless executable, Lua, and runtime paths must be ASCII; source ROM/SAV names may be Chinese")
    rom_copy = instance / "roms" / ("game" + extension)
    save_copy = instance / "saves" / "game.sav"
    shutil.copyfile(source_rom, rom_copy)
    if source_save:
        shutil.copyfile(source_save, save_copy)
    elif save_copy.exists():
        raise RuntimeError("existing isolated save present; pass --save or use a new instance")

    lua_port = free_port(args.lua_port)
    gdb_port = free_gdb_port(args.gdb_port) if args.mode == "gdb" else args.gdb_port or 0
    token = secrets.token_hex(24)
    log_path = instance / "logs" / "mgba.log"
    stdout_path = instance / "logs" / "stdout.log"
    stderr_path = instance / "logs" / "stderr.log"
    control_path = instance / "control.commands"
    control_state_path = instance / "control.state"
    control_path.write_bytes(b"")
    if control_state_path.exists():
        control_state_path.unlink()
    command = [
        str(executable),
        "-l",
        "15",
        "-C",
        f"savestatePath={instance / 'savestates'}",
        "-C", f"savegamePath={instance / 'saves'}",
        "-C", f"screenshotPath={instance / 'screenshots'}",
        "-C", "useBios=0",
    ]
    if args.mode == "gdb":
        command += ["-C", f"gdbPort={gdb_port}", "-g"]
    else:
        command += ["--script", str(args.lua.resolve(strict=True))]
    if args.savestate:
        command += ["-t", str(args.savestate.resolve(strict=True))]
    command.append(str(rom_copy))

    environment = os.environ.copy()
    environment.update(
        ROM_TOOLKIT_PLATFORM=extension[1:].upper(),
        ROM_TOOLKIT_SAVE=str(save_copy).replace("\\", "/") if source_save else "",
        GBA_HOST="127.0.0.1",
        GBA_PORT=str(lua_port),
        GBA_GDB_PORT=str(gdb_port),
        GBA_SERVICE_DIR=str(instance).replace("\\", "/"),
        GBA_LOG=str(log_path),
        GBA_SESSION_TOKEN=token,
        GBA_ALLOW_PC_TRACE="1",
        GBA_SPEED=str(args.speed),
    )
    if args.mode == "default":
        environment.update(
            GBA_CONTROL_FIFO=str(control_path).replace("\\", "/"),
            GBA_CONTROL_STATE=str(control_state_path).replace("\\", "/"),
            GBA_RUN_MODE="paused" if args.paused else "play",
        )
    (instance / "last-rom.txt").write_text(str(rom_copy), encoding="utf-8")
    stdout = stdout_path.open("ab", buffering=0)
    stderr = stderr_path.open("ab", buffering=0)
    try:
        process = subprocess.Popen(
            command,
            cwd=instance,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    finally:
        stdout.close()
        stderr.close()

    session = {
        "schema_version": 1,
        "instance": args.instance,
        "mode": args.mode,
        "host": "127.0.0.1",
        "lua_port": lua_port,
        "gdb_port": gdb_port,
        "pid": process.pid,
        "executable": str(executable),
        "executable_sha256": sha256(executable),
        "token": token,
        "source_rom": str(source_rom),
        "rom_copy": str(rom_copy),
        "rom_sha256": sha256(rom_copy),
        "source_save": str(source_save) if source_save else None,
        "save_copy": str(save_copy) if source_save else None,
        "save_sha256_before": sha256(save_copy) if source_save else None,
        "control_path": str(control_path),
        "control_state_path": str(control_state_path),
        "initial_mode": "paused" if args.paused else "play",
        "speed_multiplier": args.speed,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
    }
    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        if args.mode == "gdb":
            # A readiness TCP connect is not harmless for mGBA's single-client
            # GDB stub: it consumes the accept slot before the real debugger.
            deadline = time.monotonic() + min(args.timeout, 1.0)
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"mGBA exited early with code {process.returncode}")
                time.sleep(0.05)
        else:
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"mGBA exited early with code {process.returncode}")
                try:
                    if send_commands(session_path, ["PING"], 0.75) == ["PONG"]:
                        break
                except (OSError, ConnectionError, PermissionError, TimeoutError):
                    time.sleep(0.1)
            else:
                raise TimeoutError("Lua service did not answer PING")
        session["ready"] = True
        session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(session, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(3)
            except subprocess.TimeoutExpired:
                process.kill()
        raise


def control(args: argparse.Namespace) -> int:
    instance = (args.runtime_root.resolve() / args.instance).resolve()
    session = read_session(instance)
    executable = Path(session["executable"])
    if not process_matches(int(session["pid"]), executable):
        raise RuntimeError("instance is not running")
    control_path = Path(session["control_path"])
    state_path = Path(session["control_state_path"])
    before = read_control_state(state_path)
    before_serial = int(before.get("command_serial", "-1"))
    if args.action == "frame":
        command = f"FRAME {args.count}"
        expected = "FRAME"
    else:
        command = args.action.upper()
        expected = command
    with control_path.open("a", encoding="ascii", newline="\n") as stream:
        stream.write(command + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        state = read_control_state(state_path)
        serial = int(state.get("command_serial", "-1"))
        if serial > before_serial and state.get("last_command") == expected:
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0 if state.get("last_result") == "ok" else 1
        time.sleep(0.02)
    raise TimeoutError(f"control command did not complete: {command}")


def status(args: argparse.Namespace) -> int:
    instance = (args.runtime_root.resolve() / args.instance).resolve()
    session = read_session(instance)
    executable = Path(session["executable"])
    alive = process_matches(int(session["pid"]), executable)
    health = "stopped"
    if alive and session["mode"] == "default":
        try:
            health = "ready" if send_commands(instance / "session.json", ["PING"], 1.0) == ["PONG"] else "unhealthy"
        except Exception:
            health = "unhealthy"
    elif alive:
        health = "gdb-running"
    print(json.dumps({"alive": alive, "health": health, **session}, ensure_ascii=False, indent=2))
    return 0 if alive and health in {"ready", "gdb-running"} else 1


def stop(args: argparse.Namespace) -> int:
    instance = (args.runtime_root.resolve() / args.instance).resolve()
    session = read_session(instance)
    pid = int(session["pid"])
    executable = Path(session["executable"])
    if not process_matches(pid, executable):
        print("instance is not running; refusing to terminate an unrelated PID")
        return 0
    handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)
    if not handle:
        raise OSError(f"cannot open pid {pid}")
    try:
        if not ctypes.windll.kernel32.TerminateProcess(handle, 0):
            raise OSError(f"cannot terminate pid {pid}")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and process_matches(pid, executable):
        time.sleep(0.1)
    session["stopped_utc"] = datetime.now(timezone.utc).isoformat()
    session["save_sha256_after"] = sha256(Path(session["save_copy"])) if session.get("save_copy") and Path(session["save_copy"]).exists() else None
    (instance / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(session, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=here.parents[1] / "workspace" / "runtime")
    sub = parser.add_subparsers(dest="action", required=True)
    start_p = sub.add_parser("start")
    start_p.add_argument("--instance", required=True)
    start_p.add_argument("--rom", type=Path, required=True)
    start_p.add_argument("--save", type=Path)
    start_p.add_argument("--savestate", type=Path)
    start_p.add_argument("--mode", choices=("default", "gdb"), default="default")
    start_p.add_argument("--lua-port", type=int)
    start_p.add_argument("--gdb-port", type=int)
    start_p.add_argument("--timeout", type=float, default=15.0)
    start_p.add_argument("--paused", action="store_true")
    start_p.add_argument("--speed", type=int, choices=range(0, 11), default=1)
    start_p.add_argument("--executable", type=Path)
    start_p.add_argument("--lua", type=Path, default=here / "mgba_server.lua")
    for name in ("status", "stop"):
        item = sub.add_parser(name)
        item.add_argument("--instance", required=True)
    for name in ("pause", "resume"):
        item = sub.add_parser(name)
        item.add_argument("--instance", required=True)
        item.add_argument("--timeout", type=float, default=5.0)
    frame_p = sub.add_parser("frame")
    frame_p.add_argument("--instance", required=True)
    frame_p.add_argument("count", type=int, choices=range(1, 1000001))
    frame_p.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    args.tool_dir = here
    try:
        return {"start": start, "status": status, "stop": stop,
                "pause": control, "resume": control, "frame": control}[args.action](args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
