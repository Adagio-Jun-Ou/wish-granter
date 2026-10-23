"""CLI interface for WishGranter."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from wish_granter.engine import WishGranter, WishGranterConfig
from wish_granter.models.wish import WishStatus


async def grant_wish(text: str, config: WishGranterConfig, max_iterations: int = 50, priority: int = 5):
    granter = WishGranter(config)
    config.max_iterations = max_iterations

    wish = await granter.grant_wish(text, priority=priority)

    print(f"\n{'='*60}")
    print(f"  Wish: {text[:80]}{'...' if len(text) > 80 else ''}")
    print(f"  ID: {wish.wish_id}")
    print(f"{'='*60}\n")

    while wish.status in (WishStatus.PLANNING, WishStatus.EXECUTING, WishStatus.THINKING):
        await asyncio.sleep(2)
        wish = granter.get_wish(wish.wish_id)
        if not wish:
            break

        if wish.thinking_log:
            latest = wish.thinking_log[-1]
            status_icon = {
                WishStatus.THINKING: "🧠",
                WishStatus.EXECUTING: "⚡",
                WishStatus.PLANNING: "📋",
            }.get(wish.status, "🔄")
            print(f"  {status_icon} [{wish.current_iteration}/{wish.max_iterations}] {latest.thought[:100]}")

    print(f"\n{'='*60}")
    if wish.result:
        print(f"  Status: {wish.status.value.upper()}")
        print(f"  Iterations: {wish.result.total_iterations}")
        print(f"  Time: {wish.result.total_time_seconds:.1f}s")
        print(f"  Plan Revisions: {wish.result.plan_revisions}")
        print(f"{'='*60}\n")
        print(wish.result.summary)
    else:
        print(f"  Status: {wish.status.value.upper()}")
        print(f"{'='*60}\n")

    return wish


async def watch_wish(wish_id: str, config: WishGranterConfig):
    granter = WishGranter(config)
    wish = granter.get_wish(wish_id)
    if not wish:
        print(f"Wish {wish_id} not found")
        return

    print(f"Watching wish {wish_id}: {wish.text[:60]}...")
    while wish.status in (WishStatus.PLANNING, WishStatus.EXECUTING, WishStatus.THINKING):
        await asyncio.sleep(2)
        for log in wish.thinking_log:
            print(f"  [{log.iteration}] {log.thought}")
        wish = granter.get_wish(wish_id)
        if not wish:
            break


def serve_cmd(config: WishGranterConfig, host: str = "0.0.0.0", port: int = 8020):
    import uvicorn
    from wish_granter.web.app import create_app
    app = create_app(config)
    print(f"WishGranter starting on http://{host}:{port}")
    print(f"Dashboard: http://{host}:{port}/")
    print(f"API: http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port)


def main():
    parser = argparse.ArgumentParser(
        prog="wish-granter",
        description="WishGranter - AI-powered omnipotent wish-granting machine",
    )
    parser.add_argument("wish", nargs="*", help="The wish to grant")
    parser.add_argument("--serve", action="store_true", help="Start the web server")
    parser.add_argument("--host", default="0.0.0.0", help="Host for web server")
    parser.add_argument("--port", type=int, default=8020, help="Port for web server")
    parser.add_argument("--api-url", default="https://api.ohmyapi.com/v1/chat/completions", help="LLM API URL")
    parser.add_argument("--api-key", default="", help="LLM API key")
    parser.add_argument("--model", default="glm-5.1", help="LLM model name")
    parser.add_argument("--max-iterations", type=int, default=50, help="Max thinking iterations")
    parser.add_argument("--priority", type=int, default=5, help="Wish priority (1-10)")
    parser.add_argument("--watch", help="Watch an existing wish by ID")

    args = parser.parse_args()

    config = WishGranterConfig(
        api_url=args.api_url,
        api_key=args.api_key,
        model=args.model,
        max_iterations=args.max_iterations,
    )

    if args.serve:
        serve_cmd(config, args.host, args.port)
    elif args.watch:
        asyncio.run(watch_wish(args.watch, config))
    elif args.wish:
        wish_text = " ".join(args.wish)
        asyncio.run(grant_wish(wish_text, config, args.max_iterations, args.priority))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()