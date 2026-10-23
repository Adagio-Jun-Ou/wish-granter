"""Knowledge capability - LLM-powered knowledge synthesis."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from wish_granter.capabilities.base import Capability, CapabilityResult


class KnowledgeCapability(Capability):
    name = "knowledge"
    description = "LLM-powered knowledge synthesis, reasoning, and creative generation"

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.api_url = (config or {}).get("api_url", "https://api.ohmyapi.com/v1/chat/completions")
        self.api_key = (config or {}).get("api_key", "")
        self.model = (config or {}).get("model", "glm-5.1")

    async def execute(self, params: dict[str, Any]) -> CapabilityResult:
        start = time.time()
        action = params.get("action", "ask")
        query = params.get("query", "")
        context = params.get("context", "")
        style = params.get("style", "informative")

        if not query and action != "brainstorm":
            return self._result(False, error="No query provided", start_time=start)

        try:
            if action == "ask":
                result = await self._ask(query, context)
            elif action == "brainstorm":
                result = await self._brainstorm(query, params)
            elif action == "summarize":
                result = await self._summarize(query, context)
            elif action == "synthesize":
                result = await self._synthesize(query, context)
            elif action == "reason":
                result = await self._reason(query, context)
            elif action == "creative":
                result = await self._creative(query, style)
            else:
                result = await self._ask(query, context)

            return self._result(True, data=result, start_time=start)
        except Exception as e:
            return self._result(False, error=str(e), start_time=start)

    async def _call_llm(self, system: str, user: str, temperature: float = 0.7) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(self.api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _ask(self, query: str, context: str = "") -> dict[str, Any]:
        system = "You are an omniscient knowledge engine. Provide thorough, accurate, and insightful answers. Be comprehensive yet concise."
        prompt = query
        if context:
            prompt = f"Context:\n{context}\n\nQuestion: {query}"
        response = await self._call_llm(system, prompt)
        return {"answer": response, "query": query}

    async def _brainstorm(self, query: str, params: dict) -> dict[str, Any]:
        domain = params.get("domain", "general")
        count = params.get("count", 10)
        system = f"You are a creative genius specializing in {domain}. Generate {count} innovative ideas. Be bold and unconventional."
        response = await self._call_llm(system, query or "brainstorm groundbreaking innovations", temperature=0.9)
        return {"ideas": response, "domain": domain, "count": count}

    async def _summarize(self, query: str, context: str) -> dict[str, Any]:
        system = "You are a master summarizer. Distill the key points with clarity and precision. Use bullet points for structure."
        prompt = f"Summarize the following:\n\n{context or query}"
        response = await self._call_llm(system, prompt, temperature=0.3)
        return {"summary": response}

    async def _synthesize(self, query: str, context: str) -> dict[str, Any]:
        system = "You are a synthesis engine. Combine multiple perspectives and information into unified, coherent insights. Identify patterns, connections, and implications."
        prompt = f"Synthesize the following information into a coherent analysis:\n\n{context or query}"
        response = await self._call_llm(system, prompt)
        return {"synthesis": response}

    async def _reason(self, query: str, context: str) -> dict[str, Any]:
        system = "You are an expert analytical reasoner. Think step-by-step. Show your reasoning chain. Consider multiple hypotheses and evaluate evidence."
        prompt = query
        if context:
            prompt = f"Given this context:\n{context}\n\nReason about: {query}"
        response = await self._call_llm(system, prompt, temperature=0.2)
        return {"reasoning": response}

    async def _creative(self, query: str, style: str = "informative") -> dict[str, Any]:
        styles = {
            "informative": "Provide clear, factual, well-structured information.",
            "poetic": "Respond with beautiful, evocative language and imagery.",
            "dramatic": "Respond with dramatic flair, as if narrating an epic.",
            "humorous": "Respond with wit and clever humor while being informative.",
            "philosophical": "Respond with deep philosophical insight and contemplation.",
            "oracular": "Respond as an ancient oracle, speaking in riddles and prophecy.",
        }
        style_prompt = styles.get(style, styles["informative"])
        system = f"You are an omnipotent wish-granting entity. {style_prompt}"
        response = await self._call_llm(system, f"Grant this wish with deep understanding: {query}", temperature=0.8)
        return {"response": response, "style": style}