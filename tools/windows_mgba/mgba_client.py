"""Authenticated client for the Windows mGBA Lua service."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path


def receive_line(stream: socket.SocketIO) -> str:
    raw = stream.readline(1_048_576)
    if not raw:
        raise ConnectionError("mGBA closed the connection")
    return raw.decode("utf-8", errors="replace").rstrip("\r\n")


def send_commands(session_file: Path, commands: list[str], timeout: float) -> list[str]:
    session = json.loads(session_file.read_text(encoding="utf-8"))
    with socket.create_connection((session["host"], session["lua_port"]), timeout) as sock:
        sock.settimeout(timeout)
        stream = sock.makefile("rb")
        sock.sendall(f"AUTH {session['token']}\n".encode())
        auth = receive_line(stream)
        if auth != "OK AUTH":
            raise PermissionError(f"authentication failed: {auth}")
        output = []
        for command in commands:
            if "\n" in command or "\r" in command:
                raise ValueError("commands must be single lines")
            sock.sendall((command + "\n").encode("utf-8"))
            output.append(receive_line(stream))
        return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session", type=Path, help="instance session.json")
    parser.add_argument("commands", nargs="*", help="one or more protocol commands")
    parser.add_argument("--file", type=Path, help="UTF-8 command file, one command per line")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    commands = list(args.commands)
    if args.file:
        commands.extend(
            line.strip()
            for line in args.file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if not commands:
        parser.error("provide commands or --file")
    try:
        for response in send_commands(args.session.resolve(), commands, args.timeout):
            print(response)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
