#!/usr/bin/env python3
"""Quick test script to verify Slack API connection."""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

import httpx

SLACK_API_BASE = "https://slack.com/api"


async def test_auth():
    """Test auth.test endpoint."""
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        print("ERROR: SLACK_BOT_TOKEN not set")
        return

    print(f"Token prefix: {token[:20]}...")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SLACK_API_BASE}/auth.test",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        data = resp.json()
        print(f"\nauth.test response:")
        print(f"  ok: {data.get('ok')}")
        if data.get("ok"):
            print(f"  user: {data.get('user')}")
            print(f"  team: {data.get('team')}")
            print(f"  url: {data.get('url')}")
        else:
            print(f"  error: {data.get('error')}")

        # If token expired, try refresh
        if data.get("error") == "token_expired":
            print("\nToken expired, trying refresh...")
            refresh_token = os.getenv("SLACK_REFRESH_TOKEN")
            if refresh_token:
                resp = await client.post(
                    f"{SLACK_API_BASE}/tooling.tokens.rotate",
                    data={"refresh_token": refresh_token},
                )
                refresh_data = resp.json()
                print(f"Refresh response: ok={refresh_data.get('ok')}, error={refresh_data.get('error')}")
                if refresh_data.get("ok"):
                    print(f"New token: {refresh_data.get('token', '')[:20]}...")


async def test_conversations():
    """Test conversations.list endpoint."""
    token = os.getenv("SLACK_BOT_TOKEN")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SLACK_API_BASE}/conversations.list",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"types": "public_channel", "limit": 5},
        )
        data = resp.json()
        print(f"\nconversations.list response:")
        print(f"  ok: {data.get('ok')}")
        if data.get("ok"):
            channels = data.get("channels", [])
            print(f"  Found {len(channels)} channels:")
            for ch in channels[:5]:
                print(f"    - #{ch.get('name')} ({ch.get('id')})")
        else:
            print(f"  error: {data.get('error')}")


if __name__ == "__main__":
    asyncio.run(test_auth())
    asyncio.run(test_conversations())
