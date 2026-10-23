#!/usr/bin/env python3
"""WishGranter Demo - Make a wish and watch it be granted."""

import asyncio
import os
import sys
from wish_granter.engine import WishGranter, WishGranterConfig
from wish_granter.models.wish import WishStatus


async def main():
    config = WishGranterConfig(
        api_url="https://api.ohmyapi.com/v1/chat/completions",
        api_key=os.environ["OHMYAPI_API_KEY"],
        model="glm-5.1",
        max_iterations=20,
    )

    granter = WishGranter(config)

    wishes = [
        "I wish to understand the key principles of quantum computing with practical Python examples",
        "I wish for a creative short story about an AI that discovers it can grant wishes",
    ]

    if len(sys.argv) > 1:
        wishes = [" ".join(sys.argv[1:])]

    print("=" * 60)
    print("  WISHGRANTER - Omnipotent AI Wish-Granting Machine")
    print("=" * 60)
    print()

    for wish_text in wishes:
        print(f"  Making wish: {wish_text[:60]}...")
        print()

        wish = await granter.grant_wish(wish_text)

        print(f"  Wish ID: {wish.wish_id}")
        print(f"  Category: {wish.category.value}")
        if wish.plan:
            print(f"  Plan: {len(wish.plan.steps)} steps")
            for i, step in enumerate(wish.plan.steps):
                print(f"    {i+1}. [{step.capability.value}] {step.description}")
            print(f"  Reasoning: {wish.plan.reasoning}")
        print()

        while wish.status in (WishStatus.PLANNING, WishStatus.EXECUTING, WishStatus.THINKING):
            await asyncio.sleep(2)
            wish = granter.get_wish(wish.wish_id)
            if not wish:
                break

            if wish.thinking_log:
                latest = wish.thinking_log[-1]
                icon = "🧠" if latest.is_reflection else "⚡"
                print(f"  {icon} [Iter {wish.current_iteration}/{wish.max_iterations}] {latest.thought[:80]}")

        print()
        print("=" * 60)
        if wish.result:
            print(f"  Status: {wish.result.status.value.upper()}")
            print(f"  Iterations: {wish.result.total_iterations}")
            print(f"  Time: {wish.result.total_time_seconds:.1f}s")
            print(f"  Plan Revisions: {wish.result.plan_revisions}")
            print("=" * 60)
            print()
            print(wish.result.summary)
        else:
            print(f"  Status: {wish.status.value.upper()}")
            print("=" * 60)

        print()


if __name__ == "__main__":
    asyncio.run(main())