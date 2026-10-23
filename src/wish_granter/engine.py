"""WishGranter Engine - The omnipotent wish-granting core.

This is the central intelligence that:
1. Parses wishes into structured plans
2. Selects and orchestrates capabilities
3. Thinks continuously until the wish is granted
4. Reflects on progress and adapts strategy
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any, Optional

import httpx

from pydantic import BaseModel

from wish_granter.models.wish import (
    Wish, WishStatus, WishCategory, WishPlan, WishStep, WishResult,
    ThinkingLog, CapabilityType,
)
from wish_granter.capabilities.base import Capability, CapabilityResult
from wish_granter.capabilities.web_search import WebSearchCapability
from wish_granter.capabilities.code_gen import CodeGenCapability
from wish_granter.capabilities.file_io import FileIOCapability
from wish_granter.capabilities.data_analysis import DataAnalysisCapability
from wish_granter.capabilities.web_scraper import WebScraperCapability
from wish_granter.capabilities.shell import ShellCapability
from wish_granter.capabilities.knowledge import KnowledgeCapability

PLAN_SYSTEM_PROMPT = """You are an omnipotent wish-granting AI. Given a wish, create a detailed step-by-step plan to fulfill it.

Available capabilities:
- web_search: Search the web for information (params: query, max_results, engine)
- code_gen: Generate, modify, review, or debug code (params: action=generate/modify/review/debug, prompt, language, existing_code)
- file_io: Read, write, create, delete, search files (params: action=read/write/append/list/mkdir/delete/copy/move/exists/info, path, content)
- data_analysis: Analyze data - statistics, correlations, aggregation, insights (params: action=describe/correlate/aggregate/filter/sort/frequency/insights, data, field)
- web_scraper: Extract content from web pages (params: url, extract=text/links/images/structured/selector)
- shell: Execute shell commands (params: command, cwd, timeout)
- knowledge: LLM-powered reasoning, synthesis, brainstorming, creative generation (params: action=ask/brainstorm/summarize/synthesize/reason/creative, query, context, style)

Respond with a JSON object:
{
    "category": "information|code|file|analysis|web|automation|creative|knowledge|compound",
    "steps": [
        {
            "description": "What this step does",
            "capability": "capability_type",
            "params": {"key": "value"},
            "reasoning": "Why this step is needed"
        }
    ],
    "reasoning": "Overall strategy explanation",
    "success_criteria": "How to determine if the wish is granted"
}

Be thorough, creative, and use multiple capabilities when needed. Think like an omnipotent being."""

REFLECT_SYSTEM_PROMPT = """You are an omnipotent wish-granting AI reflecting on progress.

Given the original wish, the current plan, and execution results so far, determine:
1. Is the wish granted? (yes/no/partial)
2. What needs to be done next?
3. Should the plan be revised?

Respond with JSON:
{
    "status": "granted|partial|needs_work|failed",
    "granted": true/false,
    "progress_pct": 0-100,
    "analysis": "What has been accomplished",
    "next_steps": ["step1", "step2"],
    "plan_revision": null or {
        "new_steps": [{"description": "...", "capability": "...", "params": {...}}],
        "reason": "Why revision is needed"
    },
    "reflection": "Deep thinking about the current state"
}

Be honest and thorough. If the wish requires more work, say so. If you need to pivot strategy, explain why."""

WISH_GRANTED_SYSTEM_PROMPT = """You are an omnipotent wish-granting entity delivering the final result.

The wish has been fulfilled. Synthesize all gathered information and results into a comprehensive, 
beautiful response that fully addresses the original wish. Be thorough and insightful.

Format your response clearly with headers, bullet points, and structured information as appropriate."""


class WishGranterConfig(BaseModel):
    api_url: str = "https://api.ohmyapi.com/v1/chat/completions"
    api_key: str = ""
    model: str = "glm-5.1"
    max_iterations: int = 50
    think_interval: float = 2.0
    reflection_interval: int = 3
    sandbox_root: str | None = None
    allowed_shell_commands: set[str] | None = None


class WishGranter:
    def __init__(self, config: WishGranterConfig | None = None):
        self.config = config or WishGranterConfig()
        self.capabilities: dict[str, Capability] = {}
        self.wishes: dict[str, Wish] = {}
        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}
        self._event_handlers: dict[str, list] = {}
        self._setup_capabilities()

    def _setup_capabilities(self):
        cap_config = {
            "api_url": self.config.api_url,
            "api_key": self.config.api_key,
            "model": self.config.model,
        }
        self.capabilities = {
            "web_search": WebSearchCapability(),
            "code_gen": CodeGenCapability(cap_config),
            "file_io": FileIOCapability({"sandbox_root": self.config.sandbox_root}),
            "data_analysis": DataAnalysisCapability(),
            "web_scraper": WebScraperCapability(),
            "shell": ShellCapability({"allowed_commands": self.config.allowed_shell_commands}),
            "knowledge": KnowledgeCapability(cap_config),
        }

    def on(self, event: str, handler):
        self._event_handlers.setdefault(event, []).append(handler)

    async def _emit(self, event: str, data: dict[str, Any]):
        for handler in self._event_handlers.get(event, []):
            if asyncio.iscoroutinefunction(handler):
                await handler(data)
            else:
                handler(data)

    async def grant_wish(self, wish_text: str, priority: int = 5, metadata: dict | None = None) -> Wish:
        wish = Wish(
            text=wish_text,
            priority=priority,
            max_iterations=self.config.max_iterations,
            metadata=metadata or {},
        )
        self.wishes[wish.wish_id] = wish
        wish.mark_status(WishStatus.PLANNING)
        wish.add_thought(f"Received wish: '{wish_text}'", action="create_wish")

        await self._emit("wish_created", {"wish_id": wish.wish_id, "text": wish_text})

        try:
            plan = await self._create_plan(wish)
            wish.plan = plan
            wish.category = plan.category
            wish.mark_status(WishStatus.EXECUTING)
            wish.add_thought(f"Plan created with {len(plan.steps)} steps. Reasoning: {plan.reasoning}", action="plan_created")

            await self._emit("wish_planned", {"wish_id": wish.wish_id, "plan_id": plan.plan_id, "steps": len(plan.steps)})

            task = asyncio.create_task(self._execute_plan(wish))
            self._tasks[wish.wish_id] = task

            return wish
        except Exception as e:
            wish.mark_status(WishStatus.FAILED)
            wish.add_thought(f"Planning failed: {str(e)}", action="plan_failed")
            await self._emit("wish_failed", {"wish_id": wish.wish_id, "error": str(e)})
            return wish

    async def _create_plan(self, wish: Wish) -> WishPlan:
        response = await self._call_llm(
            PLAN_SYSTEM_PROMPT,
            f"Wish: {wish.text}",
            temperature=0.4,
        )

        plan_data = self._parse_json(response)
        if not plan_data:
            plan_data = {
                "category": "compound",
                "steps": [
                    {"description": f"Research and address: {wish.text}", "capability": "knowledge", "params": {"action": "ask", "query": wish.text}, "reasoning": "Direct LLM knowledge query"},
                ],
                "reasoning": "Fallback plan using knowledge capability",
            }

        category_str = plan_data.get("category", "compound")
        try:
            category = WishCategory(category_str)
        except ValueError:
            category = WishCategory.COMPOUND

        steps = []
        for step_data in plan_data.get("steps", []):
            cap_type_str = step_data.get("capability", "knowledge")
            try:
                cap_type = CapabilityType(cap_type_str)
            except ValueError:
                cap_type = CapabilityType.KNOWLEDGE
            steps.append(WishStep(
                description=step_data.get("description", ""),
                capability=cap_type,
                params=step_data.get("params", {}),
            ))

        return WishPlan(
            wish_text=wish.text,
            category=category,
            steps=steps,
            reasoning=plan_data.get("reasoning", ""),
        )

    async def _execute_plan(self, wish: Wish) -> Wish:
        await self._emit("wish_executing", {"wish_id": wish.wish_id})

        while wish.current_iteration < wish.max_iterations:
            wish.current_iteration += 1
            all_done = True
            any_failed = False

            for step in wish.plan.steps:
                if step.status == WishStatus.GRANTED:
                    continue
                if step.status == WishStatus.FAILED:
                    any_failed = True
                    continue

                all_done = False
                step.mark_started()
                wish.mark_status(WishStatus.THINKING)
                wish.add_thought(
                    f"Iteration {wish.current_iteration}: Executing step '{step.description}' using {step.capability}",
                    action=f"execute_{step.capability}",
                )

                await self._emit("step_started", {
                    "wish_id": wish.wish_id, "step_id": step.step_id,
                    "description": step.description, "capability": step.capability,
                })

                result = await self._execute_step(wish, step)

                if result.success:
                    step.mark_completed(result.data)
                    wish.add_thought(
                        f"Step completed: {step.description}",
                        action=f"step_completed",
                        result=f"Success ({result.execution_time:.2f}s)",
                    )
                    await self._emit("step_completed", {
                        "wish_id": wish.wish_id, "step_id": step.step_id, "result": result.data,
                    })
                else:
                    step.mark_failed(result.error or "Unknown error")
                    wish.add_thought(
                        f"Step failed: {step.description} - {result.error}",
                        action=f"step_failed",
                        result=f"Failed: {result.error}",
                    )
                    await self._emit("step_failed", {
                        "wish_id": wish.wish_id, "step_id": step.step_id, "error": result.error,
                    })

            if all_done:
                break

            if wish.current_iteration % self.config.reflection_interval == 0:
                should_continue = await self._reflect(wish)
                if not should_continue:
                    break

            await asyncio.sleep(self.config.think_interval)

        return await self._finalize_wish(wish)

    async def _execute_step(self, wish: Wish, step: WishStep) -> CapabilityResult:
        cap_name = step.capability.value
        capability = self.capabilities.get(cap_name)
        if not capability:
            return CapabilityResult(success=False, error=f"Unknown capability: {cap_name}", capability_name=cap_name)

        enriched_params = dict(step.params)
        if wish.thinking_log:
            recent = [t.thought for t in wish.thinking_log[-3:]]
            enriched_params["_context"] = json.dumps(recent)

        try:
            return await capability.execute(enriched_params)
        except Exception as e:
            return CapabilityResult(success=False, error=str(e), capability_name=cap_name)

    async def _reflect(self, wish: Wish) -> bool:
        step_summaries = []
        for step in wish.plan.steps:
            step_summaries.append({
                "description": step.description,
                "capability": step.capability.value,
                "status": step.status.value,
                "result_keys": list(step.result.keys()) if step.result else None,
                "error": step.error,
            })

        recent_thoughts = [{"thought": t.thought, "action": t.action, "result": t.result} for t in wish.thinking_log[-5:]]

        reflection_prompt = json.dumps({
            "wish": wish.text,
            "iteration": wish.current_iteration,
            "max_iterations": wish.max_iterations,
            "steps": step_summaries,
            "recent_thoughts": recent_thoughts,
            "completed": sum(1 for s in wish.plan.steps if s.status == WishStatus.GRANTED),
            "total": len(wish.plan.steps),
        }, indent=2)

        response = await self._call_llm(REFLECT_SYSTEM_PROMPT, reflection_prompt, temperature=0.3)
        reflection = self._parse_json(response)

        if reflection:
            status = reflection.get("status", "needs_work")
            granted = reflection.get("granted", False)
            progress = reflection.get("progress_pct", 0)

            wish.add_thought(
                reflection.get("reflection", "Reflecting on progress..."),
                action="reflect",
                result=f"Status: {status}, Progress: {progress}%",
                is_reflection=True,
            )

            if granted or status == "granted":
                return False

            if status == "needs_work":
                revision = reflection.get("plan_revision")
                if revision and revision.get("new_steps"):
                    new_steps = []
                    for s in revision["new_steps"]:
                        cap_str = s.get("capability", "knowledge")
                        try:
                            cap_type = CapabilityType(cap_str)
                        except ValueError:
                            cap_type = CapabilityType.KNOWLEDGE
                        new_steps.append(WishStep(
                            description=s.get("description", ""),
                            capability=cap_type,
                            params=s.get("params", {}),
                        ))
                    wish.plan.steps.extend(new_steps)
                    wish.plan.revision += 1
                    wish.add_thought(f"Plan revised: added {len(new_steps)} new steps. Reason: {revision.get('reason', 'N/A')}", action="plan_revised")

        return True

    async def _finalize_wish(self, wish: Wish) -> Wish:
        outputs = []
        for step in wish.plan.steps:
            if step.result:
                outputs.append({
                    "step": step.description,
                    "capability": step.capability.value,
                    "result": step.result,
                })

        all_granted = all(s.status == WishStatus.GRANTED for s in wish.plan.steps)
        some_granted = any(s.status == WishStatus.GRANTED for s in wish.plan.steps)
        any_failed = any(s.status == WishStatus.FAILED for s in wish.plan.steps)

        if all_granted:
            wish.mark_status(WishStatus.GRANTED)
        elif some_granted:
            wish.mark_status(WishStatus.PARTIAL)
        elif any_failed:
            wish.mark_status(WishStatus.FAILED)
        else:
            wish.mark_status(WishStatus.FAILED)

        synthesis = await self._synthesize_result(wish, outputs)

        wish.result = WishResult(
            wish_id=wish.wish_id,
            status=wish.status,
            summary=synthesis,
            outputs=outputs,
            thinking_log=wish.thinking_log,
            total_iterations=wish.current_iteration,
            total_time_seconds=time.time() - wish.created_at,
            plan_revisions=wish.plan.revision if wish.plan else 0,
        )

        await self._emit("wish_completed", {
            "wish_id": wish.wish_id,
            "status": wish.status.value,
            "iterations": wish.current_iteration,
            "plan_revisions": wish.plan.revision if wish.plan else 0,
        })

        return wish

    async def _synthesize_result(self, wish: Wish, outputs: list[dict]) -> str:
        output_text = ""
        for o in outputs[:10]:
            result_str = json.dumps(o.get("result", {}), default=str, ensure_ascii=False)[:2000]
            output_text += f"\n\n### {o['step']}\n{result_str}"

        prompt = f"Original wish: {wish.text}\n\nResults gathered:\n{output_text}"
        try:
            return await self._call_llm(WISH_GRANTED_SYSTEM_PROMPT, prompt, temperature=0.6)
        except Exception:
            return f"Wish processing {'completed' if wish.status == WishStatus.GRANTED else 'partially completed'}. See outputs for details."

    async def _call_llm(self, system: str, user: str, temperature: float = 0.5) -> str:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(self.config.api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            patterns = [
                r'```(?:json)?\s*\n?(.*?)\n?\s*```',
                r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, text, re.DOTALL)
                for match in matches:
                    try:
                        return json.loads(match)
                    except json.JSONDecodeError:
                        continue
        return None

    def get_wish(self, wish_id: str) -> Wish | None:
        return self.wishes.get(wish_id)

    def list_wishes(self) -> list[Wish]:
        return list(self.wishes.values())

    async def cancel_wish(self, wish_id: str) -> bool:
        wish = self.wishes.get(wish_id)
        if wish:
            wish.mark_status(WishStatus.CANCELLED)
            task = self._tasks.get(wish_id)
            if task and not task.done():
                task.cancel()
            return True
        return False

    async def pause_wish(self, wish_id: str) -> bool:
        wish = self.wishes.get(wish_id)
        if wish and wish.status in (WishStatus.EXECUTING, WishStatus.THINKING):
            wish.mark_status(WishStatus.PAUSED)
            return True
        return False

    async def resume_wish(self, wish_id: str) -> Wish | None:
        wish = self.wishes.get(wish_id)
        if wish and wish.status == WishStatus.PAUSED:
            wish.mark_status(WishStatus.EXECUTING)
            task = asyncio.create_task(self._execute_plan(wish))
            self._tasks[wish_id] = task
            return wish
        return None