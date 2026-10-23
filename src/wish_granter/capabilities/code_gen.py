"""Code generation capability using LLM."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from wish_granter.capabilities.base import Capability, CapabilityResult


class CodeGenCapability(Capability):
    name = "code_gen"
    description = "Generate, modify, and execute code using LLM"

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.api_url = config.get("api_url", "https://api.ohmyapi.com/v1/chat/completions") if config else "https://api.ohmyapi.com/v1/chat/completions"
        self.api_key = config.get("api_key", "") if config else ""
        self.model = config.get("model", "glm-5.1") if config else "glm-5.1"

    async def execute(self, params: dict[str, Any]) -> CapabilityResult:
        start = time.time()
        action = params.get("action", "generate")
        prompt = params.get("prompt", "")
        language = params.get("language", "python")
        existing_code = params.get("existing_code", "")
        execute = params.get("execute", False)

        if not prompt and action != "review":
            return self._result(False, error="No prompt provided", start_time=start)

        try:
            if action == "generate":
                result = await self._generate(prompt, language)
            elif action == "modify":
                result = await self._modify(prompt, existing_code, language)
            elif action == "review":
                result = await self._review(existing_code or prompt)
            elif action == "debug":
                result = await self._debug(prompt, existing_code, language)
            else:
                result = await self._generate(prompt, language)

            return self._result(True, data=result, start_time=start)
        except Exception as e:
            return self._result(False, error=str(e), start_time=start)

    async def _call_llm(self, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(self.api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _generate(self, prompt: str, language: str) -> dict[str, Any]:
        system = f"You are an expert {language} programmer. Generate clean, production-quality code. Output ONLY the code inside ```{language}``` blocks, with brief comments."
        response = await self._call_llm(system, prompt)
        code = self._extract_code(response)
        return {"code": code, "language": language, "raw_response": response}

    async def _modify(self, prompt: str, existing_code: str, language: str) -> dict[str, Any]:
        system = f"You are an expert {language} programmer. Modify the provided code according to the instructions. Output ONLY the modified code inside ```{language}``` blocks."
        user = f"Here is the code to modify:\n```\n{existing_code}\n```\n\nModification instructions: {prompt}"
        response = await self._call_llm(system, user)
        code = self._extract_code(response)
        return {"code": code, "language": language, "raw_response": response}

    async def _review(self, code: str) -> dict[str, Any]:
        system = "You are an expert code reviewer. Analyze the code for bugs, security issues, style problems, and improvements. Provide specific, actionable feedback."
        response = await self._call_llm(system, f"Review this code:\n```\n{code}\n```")
        return {"review": response, "code": code}

    async def _debug(self, error_msg: str, existing_code: str, language: str) -> dict[str, Any]:
        system = f"You are an expert {language} debugger. Identify and fix the bug. Output ONLY the fixed code inside ```{language}``` blocks."
        user = f"Code:\n```\n{existing_code}\n```\n\nError: {error_msg}"
        response = await self._call_llm(system, user)
        code = self._extract_code(response)
        return {"code": code, "language": language, "raw_response": response}

    @staticmethod
    def _extract_code(response: str) -> str:
        pattern = r'```(?:\w+)?\s*\n(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            return matches[0].strip()
        return response.strip()