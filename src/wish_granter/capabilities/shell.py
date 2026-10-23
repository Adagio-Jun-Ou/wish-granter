"""Shell command execution capability."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from wish_granter.capabilities.base import Capability, CapabilityResult


class ShellCapability(Capability):
    name = "shell"
    description = "Execute shell commands safely"

    ALLOWED_COMMANDS: set[str] | None = None
    BLOCKED_COMMANDS: set[str] = {"rm -rf /", "mkfs", "dd if=", ":(){ :|:& }:", "format"}

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        if config and config.get("allowed_commands"):
            self.ALLOWED_COMMANDS = set(config["allowed_commands"])

    async def execute(self, params: dict[str, Any]) -> CapabilityResult:
        start = time.time()
        command = params.get("command", "")
        cwd = params.get("cwd", "")
        timeout = params.get("timeout", 60)
        env = params.get("env", {})

        if not command:
            return self._result(False, error="No command provided", start_time=start)

        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command:
                return self._result(False, error=f"Blocked command: contains '{blocked}'", start_time=start)

        if self.ALLOWED_COMMANDS:
            cmd_base = command.split()[0] if command.split() else ""
            if cmd_base not in self.ALLOWED_COMMANDS:
                return self._result(False, error=f"Command not allowed: {cmd_base}", start_time=start)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or None,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return self._result(
                proc.returncode == 0,
                data={
                    "stdout": stdout.decode("utf-8", errors="replace")[:50000],
                    "stderr": stderr.decode("utf-8", errors="replace")[:10000],
                    "returncode": proc.returncode,
                    "command": command,
                },
                error=stderr.decode("utf-8", errors="replace")[:5000] if proc.returncode != 0 else None,
                start_time=start,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return self._result(False, error=f"Command timed out after {timeout}s", start_time=start)
        except Exception as e:
            return self._result(False, error=str(e), start_time=start)