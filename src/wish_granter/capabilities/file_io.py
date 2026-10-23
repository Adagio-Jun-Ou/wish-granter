"""File I/O capability for reading, writing, and managing files."""

from __future__ import annotations

import base64
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from wish_granter.capabilities.base import Capability, CapabilityResult


class FileIOCapability(Capability):
    name = "file_io"
    description = "Read, write, create, delete, and manage files and directories"

    SANDBOX_ROOT: str | None = None

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        sandbox = config.get("sandbox_root") if config else None
        if sandbox:
            self.SANDBOX_ROOT = sandbox

    def _resolve(self, path: str) -> Path:
        p = Path(path).expanduser().resolve()
        if self.SANDBOX_ROOT:
            sandbox = Path(self.SANDBOX_ROOT).resolve()
            if not str(p).startswith(str(sandbox)):
                raise ValueError(f"Path '{path}' is outside sandbox '{sandbox}'")
        return p

    async def execute(self, params: dict[str, Any]) -> CapabilityResult:
        start = time.time()
        action = params.get("action", "read")
        path = params.get("path", "")

        try:
            if action == "read":
                return await self._read(path, params)
            elif action == "write":
                return await self._write(path, params)
            elif action == "append":
                return await self._append(path, params)
            elif action == "list":
                return await self._list_dir(path, params)
            elif action == "mkdir":
                return await self._mkdir(path)
            elif action == "delete":
                return await self._delete(path)
            elif action == "copy":
                return await self._copy(path, params.get("destination", ""))
            elif action == "move":
                return await self._move(path, params.get("destination", ""))
            elif action == "exists":
                return await self._exists(path)
            elif action == "info":
                return await self._info(path)
            elif action == "search":
                return await self._search_files(path, params)
            else:
                return self._result(False, error=f"Unknown file action: {action}", start_time=start)
        except Exception as e:
            return self._result(False, error=str(e), start_time=start)

    async def _read(self, path: str, params: dict) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path)
        if not p.exists():
            return self._result(False, error=f"File not found: {path}", start_time=start)
        if p.is_dir():
            return self._result(False, error=f"Path is a directory, use list action: {path}", start_time=start)

        encoding = params.get("encoding", "utf-8")
        binary = params.get("binary", False)

        if binary:
            data = base64.b64encode(p.read_bytes()).decode("ascii")
            return self._result(True, data={"content": data, "encoding": "base64", "size": p.stat().st_size}, start_time=start)

        content = p.read_text(encoding=encoding)
        lines = params.get("lines")
        if lines:
            line_list = content.splitlines()
            start_line = params.get("start_line", 0)
            end_line = start_line + lines
            content = "\n".join(line_list[start_line:end_line])

        return self._result(True, data={"content": content, "size": p.stat().st_size, "lines": len(content.splitlines())}, start_time=start)

    async def _write(self, path: str, params: dict) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path)
        content = params.get("content", "")
        encoding = params.get("encoding", "utf-8")

        p.parent.mkdir(parents=True, exist_ok=True)
        if params.get("binary") and params.get("content_b64"):
            p.write_bytes(base64.b64decode(params["content_b64"]))
        else:
            p.write_text(content, encoding=encoding)

        return self._result(True, data={"path": str(p), "size": p.stat().st_size, "created": True}, start_time=start)

    async def _append(self, path: str, params: dict) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path)
        content = params.get("content", "")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(content)
        return self._result(True, data={"path": str(p), "appended": True}, start_time=start)

    async def _list_dir(self, path: str, params: dict) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path or ".")
        if not p.exists():
            return self._result(False, error=f"Directory not found: {path}", start_time=start)

        entries = []
        recursive = params.get("recursive", False)
        pattern = params.get("pattern", "*")

        if recursive:
            for item in p.rglob(pattern):
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0,
                })
        else:
            for item in p.glob(pattern):
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0,
                })

        return self._result(True, data={"path": str(p), "entries": entries, "total": len(entries)}, start_time=start)

    async def _mkdir(self, path: str) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path)
        p.mkdir(parents=True, exist_ok=True)
        return self._result(True, data={"path": str(p), "created": True}, start_time=start)

    async def _delete(self, path: str) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path)
        if not p.exists():
            return self._result(False, error=f"Path not found: {path}", start_time=start)
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return self._result(True, data={"path": str(p), "deleted": True}, start_time=start)

    async def _copy(self, src: str, dst: str) -> CapabilityResult:
        start = time.time()
        s = self._resolve(src)
        d = self._resolve(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        return self._result(True, data={"src": str(s), "dst": str(d), "copied": True}, start_time=start)

    async def _move(self, src: str, dst: str) -> CapabilityResult:
        start = time.time()
        s = self._resolve(src)
        d = self._resolve(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return self._result(True, data={"src": str(s), "dst": str(d), "moved": True}, start_time=start)

    async def _exists(self, path: str) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path)
        return self._result(True, data={"path": str(p), "exists": p.exists(), "is_dir": p.is_dir() if p.exists() else False}, start_time=start)

    async def _info(self, path: str) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path)
        if not p.exists():
            return self._result(False, error=f"Path not found: {path}", start_time=start)
        stat = p.stat()
        return self._result(True, data={
            "path": str(p), "name": p.name, "suffix": p.suffix,
            "size": stat.st_size, "is_dir": p.is_dir(),
            "modified": stat.st_mtime, "created": stat.st_ctime,
        }, start_time=start)

    async def _search_files(self, path: str, params: dict) -> CapabilityResult:
        start = time.time()
        p = self._resolve(path)
        query = params.get("query", "").lower()
        max_results = params.get("max_results", 50)
        if not p.exists() or not p.is_dir():
            return self._result(False, error=f"Directory not found: {path}", start_time=start)

        matches = []
        for item in p.rglob("*"):
            if item.is_file():
                if query in item.name.lower():
                    matches.append({"path": str(item), "name": item.name, "size": item.stat().st_size})
                    if len(matches) >= max_results:
                        break
        return self._result(True, data={"query": query, "matches": matches, "total": len(matches)}, start_time=start)