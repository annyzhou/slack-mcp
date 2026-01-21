# Copyright (c) 2026 Dedalus Labs, Inc. and its contributors
# SPDX-License-Identifier: MIT

"""Slack API tools for slack-mcp.

Read and manage Slack workspaces via the Slack Web API.
Ref: https://api.slack.com/methods

Supported Token Types:
----------------------
1. Bot Token (xoxb-...)
   - Get from: Slack App > OAuth & Permissions > Bot User OAuth Token
   - Scopes: Add under "Bot Token Scopes"
   - Best for: Bots that act as themselves, limited to channels bot is invited to
   - Does NOT support: search.messages, some user-level actions

2. User Token (xoxp-...)
   - Get from: Slack App > OAuth & Permissions > User OAuth Token
   - Scopes: Add under "User Token Scopes"
   - Best for: Acting as a user, full workspace access
   - Supports: All tools including search

3. Rotatable User Token (xoxe.xoxp-...)
   - Same as user token but with refresh capability
   - Set SLACK_REFRESH_TOKEN to enable auto-refresh
   - Tokens expire in 12 hours, auto-refreshed on expiry

Token Scopes Required by Tool:
-----------------------------
conversations.list:    channels:read, groups:read, im:read, mpim:read
conversations.history: channels:history, groups:history, im:history, mpim:history
chat.postMessage:      chat:write
users.list/info:       users:read
users.lookupByEmail:   users:read.email
search.messages:       search:read (USER TOKEN ONLY - not available for bot tokens)
reactions.add/remove:  reactions:write
pins.list/add/remove:  pins:read, pins:write
files.list/info:       files:read
team.info:             team:read
reminders.*:           reminders:read, reminders:write
bookmarks.list:        bookmarks:read
"""

import json
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.types import TextContent, Tool

from dedalus_mcp.types import ToolAnnotations

from dedalus_mcp import tool

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

SLACK_API_BASE = "https://slack.com/api"
ENV_FILE = Path(__file__).parent.parent / ".env"

# Token state (mutable for refresh)
_token_state: dict[str, str] = {
    "access_token": os.getenv("SLACK_TOKEN", "") or os.getenv("SLACK_BOT_TOKEN", "") or os.getenv("SLACK_USER_TOKEN", ""),
    "refresh_token": os.getenv("SLACK_REFRESH_TOKEN", ""),
}

# -----------------------------------------------------------------------------
# Token Management
# -----------------------------------------------------------------------------

SlackResult = list[TextContent]


def _get_token_type(token: str) -> str:
    """Determine the type of Slack token."""
    if token.startswith("xoxb-"):
        return "bot"
    elif token.startswith("xoxp-"):
        return "user"
    elif token.startswith("xoxe.xoxp-"):
        return "user_rotatable"
    elif token.startswith("xoxe.xoxb-"):
        return "bot_rotatable"
    elif token.startswith("xapp-"):
        return "app_level"
    else:
        return "unknown"


def _load_token_from_env() -> None:
    """Reload tokens from environment. Checks multiple env var names for flexibility."""
    _token_state["access_token"] = (
        os.getenv("SLACK_TOKEN", "") or
        os.getenv("SLACK_BOT_TOKEN", "") or
        os.getenv("SLACK_USER_TOKEN", "")
    )
    _token_state["refresh_token"] = os.getenv("SLACK_REFRESH_TOKEN", "")


def _save_tokens_to_env(access_token: str, refresh_token: str) -> None:
    """Save new tokens to .env file."""
    _token_state["access_token"] = access_token
    _token_state["refresh_token"] = refresh_token

    if ENV_FILE.exists():
        content = ENV_FILE.read_text()
        lines = content.splitlines()
        new_lines = []
        found_access = False
        found_refresh = False

        for line in lines:
            if line.startswith(("SLACK_TOKEN=", "SLACK_BOT_TOKEN=", "SLACK_USER_TOKEN=")):
                if not found_access:
                    new_lines.append(f"SLACK_TOKEN={access_token}")
                    found_access = True
                # Skip duplicate token lines
            elif line.startswith("SLACK_REFRESH_TOKEN="):
                new_lines.append(f"SLACK_REFRESH_TOKEN={refresh_token}")
                found_refresh = True
            else:
                new_lines.append(line)

        if not found_access:
            new_lines.append(f"SLACK_TOKEN={access_token}")
        if not found_refresh and refresh_token:
            new_lines.append(f"SLACK_REFRESH_TOKEN={refresh_token}")

        ENV_FILE.write_text("\n".join(new_lines) + "\n")


async def _refresh_token() -> bool:
    """Refresh the access token using the refresh token (for xoxe.* tokens)."""
    refresh_token = _token_state["refresh_token"]

    if not refresh_token:
        print("No refresh token available")
        return False

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SLACK_API_BASE}/tooling.tokens.rotate",
            data={
                "refresh_token": refresh_token,
            },
        )
        data = resp.json()

        if data.get("ok"):
            new_access = data.get("token", "")
            new_refresh = data.get("refresh_token", "")
            if new_access:
                _save_tokens_to_env(new_access, new_refresh)
                print("Token refreshed successfully")
                return True
        else:
            print(f"Token refresh failed: {data.get('error', 'unknown error')}")

    return False


def _get_token() -> str:
    """Get Slack token from state."""
    token = _token_state["access_token"]
    if not token:
        _load_token_from_env()
        token = _token_state["access_token"]
    if not token:
        raise ValueError(
            "Slack token not found. Set one of: SLACK_TOKEN, SLACK_BOT_TOKEN, or SLACK_USER_TOKEN"
        )
    return token


def _is_user_token() -> bool:
    """Check if current token is a user token (required for some APIs like search)."""
    token = _get_token()
    token_type = _get_token_type(token)
    return token_type in ("user", "user_rotatable")


async def _post(endpoint: str, params: dict[str, Any] | None = None, retry_on_auth_fail: bool = True) -> SlackResult:
    """Make a POST request to Slack API with auto token refresh."""
    token = _get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SLACK_API_BASE}/{endpoint}",
            headers=headers,
            json=params or {},
        )
        data = resp.json()

        # Check for token expiration (rotatable tokens only)
        if not data.get("ok") and data.get("error") == "token_expired" and retry_on_auth_fail:
            if await _refresh_token():
                return await _post(endpoint, params, retry_on_auth_fail=False)

        return [TextContent(type="text", text=json.dumps(data, indent=2))]


async def _get(endpoint: str, params: dict[str, Any] | None = None, retry_on_auth_fail: bool = True) -> SlackResult:
    """Make a GET request to Slack API with auto token refresh."""
    token = _get_token()
    headers = {
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SLACK_API_BASE}/{endpoint}",
            headers=headers,
            params=params or {},
        )
        data = resp.json()

        # Check for token expiration (rotatable tokens only)
        if not data.get("ok") and data.get("error") == "token_expired" and retry_on_auth_fail:
            if await _refresh_token():
                return await _get(endpoint, params, retry_on_auth_fail=False)

        return [TextContent(type="text", text=json.dumps(data, indent=2))]


# -----------------------------------------------------------------------------
# Conversations (Channels, DMs, Group DMs)
# -----------------------------------------------------------------------------


@tool(
    description="List conversations (channels, DMs, group DMs) the user is a member of. Use types parameter to filter: public_channel, private_channel, mpim (group DMs), im (DMs).",
    tags=["channel", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_list_conversations(
    types: str = "public_channel,private_channel",
    limit: int = 100,
    cursor: str = "",
    exclude_archived: bool = True,
) -> SlackResult:
    """List conversations the user is a member of."""
    params: dict[str, Any] = {
        "types": types,
        "limit": limit,
        "exclude_archived": exclude_archived,
    }
    if cursor:
        params["cursor"] = cursor
    return await _post("conversations.list", params)


@tool(
    description="Get information about a conversation (channel, DM, or group DM).",
    tags=["channel", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_get_conversation_info(
    channel: str,
    include_num_members: bool = True,
) -> SlackResult:
    """Get conversation info by channel ID."""
    params = {
        "channel": channel,
        "include_num_members": include_num_members,
    }
    return await _post("conversations.info", params)


@tool(
    description="Fetch message history from a conversation. Returns messages in reverse chronological order.",
    tags=["message", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_conversations_history(
    channel: str,
    limit: int = 100,
    cursor: str = "",
    oldest: str = "",
    latest: str = "",
    inclusive: bool = True,
) -> SlackResult:
    """Fetch conversation history."""
    params: dict[str, Any] = {
        "channel": channel,
        "limit": limit,
        "inclusive": inclusive,
    }
    if cursor:
        params["cursor"] = cursor
    if oldest:
        params["oldest"] = oldest
    if latest:
        params["latest"] = latest
    return await _post("conversations.history", params)


@tool(
    description="Get replies (thread messages) for a specific message in a conversation.",
    tags=["message", "thread", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_conversations_replies(
    channel: str,
    ts: str,
    limit: int = 100,
    cursor: str = "",
    oldest: str = "",
    latest: str = "",
    inclusive: bool = True,
) -> SlackResult:
    """Get thread replies for a message."""
    params: dict[str, Any] = {
        "channel": channel,
        "ts": ts,
        "limit": limit,
        "inclusive": inclusive,
    }
    if cursor:
        params["cursor"] = cursor
    if oldest:
        params["oldest"] = oldest
    if latest:
        params["latest"] = latest
    return await _post("conversations.replies", params)


@tool(
    description="List members of a conversation.",
    tags=["channel", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_conversations_members(
    channel: str,
    limit: int = 100,
    cursor: str = "",
) -> SlackResult:
    """List members of a conversation."""
    params: dict[str, Any] = {
        "channel": channel,
        "limit": limit,
    }
    if cursor:
        params["cursor"] = cursor
    return await _post("conversations.members", params)


@tool(
    description="Join a public channel.",
    tags=["channel", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_conversations_join(channel: str) -> SlackResult:
    """Join a public channel."""
    return await _post("conversations.join", {"channel": channel})


@tool(
    description="Leave a conversation (channel, DM, or group DM).",
    tags=["channel", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_conversations_leave(channel: str) -> SlackResult:
    """Leave a conversation."""
    return await _post("conversations.leave", {"channel": channel})


@tool(
    description="Open or resume a direct message (DM) or multi-person direct message (MPIM).",
    tags=["dm", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_conversations_open(
    users: str = "",
    channel: str = "",
    return_im: bool = True,
) -> SlackResult:
    """Open a DM or MPIM. Provide either users (comma-separated) or channel ID."""
    params: dict[str, Any] = {"return_im": return_im}
    if users:
        params["users"] = users
    if channel:
        params["channel"] = channel
    return await _post("conversations.open", params)


# -----------------------------------------------------------------------------
# Messages
# -----------------------------------------------------------------------------


@tool(
    description="Send a message to a channel, DM, or thread. Use thread_ts to reply in a thread.",
    tags=["message", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_chat_post_message(
    channel: str,
    text: str,
    thread_ts: str = "",
    reply_broadcast: bool = False,
    unfurl_links: bool = True,
    unfurl_media: bool = True,
) -> SlackResult:
    """Post a message to a channel or thread."""
    params: dict[str, Any] = {
        "channel": channel,
        "text": text,
        "unfurl_links": unfurl_links,
        "unfurl_media": unfurl_media,
    }
    if thread_ts:
        params["thread_ts"] = thread_ts
        params["reply_broadcast"] = reply_broadcast
    return await _post("chat.postMessage", params)


@tool(
    description="Update an existing message.",
    tags=["message", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_chat_update(
    channel: str,
    ts: str,
    text: str,
) -> SlackResult:
    """Update a message."""
    params = {
        "channel": channel,
        "ts": ts,
        "text": text,
    }
    return await _post("chat.update", params)


@tool(
    description="Delete a message.",
    tags=["message", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_chat_delete(channel: str, ts: str) -> SlackResult:
    """Delete a message."""
    return await _post("chat.delete", {"channel": channel, "ts": ts})


@tool(
    description="Add a reaction (emoji) to a message.",
    tags=["reaction", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_reactions_add(
    channel: str,
    timestamp: str,
    name: str,
) -> SlackResult:
    """Add a reaction to a message. Name is the emoji name without colons (e.g., 'thumbsup')."""
    return await _post("reactions.add", {"channel": channel, "timestamp": timestamp, "name": name})


@tool(
    description="Remove a reaction from a message.",
    tags=["reaction", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_reactions_remove(
    channel: str,
    timestamp: str,
    name: str,
) -> SlackResult:
    """Remove a reaction from a message."""
    return await _post("reactions.remove", {"channel": channel, "timestamp": timestamp, "name": name})


# -----------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------


@tool(
    description="Search for messages matching a query. Supports Slack search modifiers like 'from:@user', 'in:#channel', 'before:2024-01-01'. Note: Requires a user token (xoxp-), not a bot token.",
    tags=["search", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_search_messages(
    query: str,
    count: int = 20,
    cursor: str = "",
    sort: str = "timestamp",
    sort_dir: str = "desc",
) -> SlackResult:
    """Search for messages."""
    params: dict[str, Any] = {
        "query": query,
        "count": count,
        "sort": sort,
        "sort_dir": sort_dir,
    }
    if cursor:
        params["cursor"] = cursor
    return await _post("search.messages", params)


# -----------------------------------------------------------------------------
# Users
# -----------------------------------------------------------------------------


@tool(
    description="List all users in the workspace.",
    tags=["user", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_users_list(
    limit: int = 100,
    cursor: str = "",
    include_locale: bool = False,
) -> SlackResult:
    """List users in the workspace."""
    params: dict[str, Any] = {
        "limit": limit,
        "include_locale": include_locale,
    }
    if cursor:
        params["cursor"] = cursor
    return await _post("users.list", params)


@tool(
    description="Get information about a user by their ID.",
    tags=["user", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_users_info(user: str) -> SlackResult:
    """Get user info by ID."""
    return await _post("users.info", {"user": user})


@tool(
    description="Find a user by their email address.",
    tags=["user", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_users_lookup_by_email(email: str) -> SlackResult:
    """Find a user by email."""
    return await _post("users.lookupByEmail", {"email": email})


@tool(
    description="Get the current user's identity (who the token belongs to).",
    tags=["user", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_auth_test() -> SlackResult:
    """Get information about the current user/token."""
    return await _post("auth.test")


# -----------------------------------------------------------------------------
# Team
# -----------------------------------------------------------------------------


@tool(
    description="Get information about the workspace (team).",
    tags=["team", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_team_info() -> SlackResult:
    """Get workspace/team information."""
    return await _post("team.info")


# -----------------------------------------------------------------------------
# Bookmarks
# -----------------------------------------------------------------------------


@tool(
    description="List bookmarks in a channel.",
    tags=["bookmark", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_bookmarks_list(channel: str) -> SlackResult:
    """List bookmarks in a channel."""
    return await _post("bookmarks.list", {"channel_id": channel})


# -----------------------------------------------------------------------------
# Pins
# -----------------------------------------------------------------------------


@tool(
    description="List pinned items in a channel.",
    tags=["pin", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_pins_list(channel: str) -> SlackResult:
    """List pinned items in a channel."""
    return await _post("pins.list", {"channel": channel})


@tool(
    description="Pin a message to a channel.",
    tags=["pin", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_pins_add(channel: str, timestamp: str) -> SlackResult:
    """Pin a message to a channel."""
    return await _post("pins.add", {"channel": channel, "timestamp": timestamp})


@tool(
    description="Unpin a message from a channel.",
    tags=["pin", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_pins_remove(channel: str, timestamp: str) -> SlackResult:
    """Unpin a message from a channel."""
    return await _post("pins.remove", {"channel": channel, "timestamp": timestamp})


# -----------------------------------------------------------------------------
# Reminders
# -----------------------------------------------------------------------------


@tool(
    description="List reminders for the current user.",
    tags=["reminder", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_reminders_list() -> SlackResult:
    """List reminders."""
    return await _post("reminders.list")


@tool(
    description="Create a reminder. Time can be Unix timestamp or natural language like 'in 20 minutes' or 'tomorrow at 9am'.",
    tags=["reminder", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_reminders_add(
    text: str,
    time: str,
    user: str = "",
) -> SlackResult:
    """Create a reminder."""
    params: dict[str, Any] = {
        "text": text,
        "time": time,
    }
    if user:
        params["user"] = user
    return await _post("reminders.add", params)


@tool(
    description="Delete a reminder.",
    tags=["reminder", "write"],
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def slack_reminders_delete(reminder: str) -> SlackResult:
    """Delete a reminder by ID."""
    return await _post("reminders.delete", {"reminder": reminder})


# -----------------------------------------------------------------------------
# Files
# -----------------------------------------------------------------------------


@tool(
    description="List files shared in the workspace. Can filter by channel, user, or type.",
    tags=["file", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_files_list(
    channel: str = "",
    user: str = "",
    types: str = "",
    count: int = 20,
    page: int = 1,
) -> SlackResult:
    """List files. Types can be: all, spaces, snippets, images, gdocs, zips, pdfs."""
    params: dict[str, Any] = {
        "count": count,
        "page": page,
    }
    if channel:
        params["channel"] = channel
    if user:
        params["user"] = user
    if types:
        params["types"] = types
    return await _post("files.list", params)


@tool(
    description="Get information about a file.",
    tags=["file", "read"],
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def slack_files_info(file: str) -> SlackResult:
    """Get file info by ID."""
    return await _post("files.info", {"file": file})


# -----------------------------------------------------------------------------
# Export
# -----------------------------------------------------------------------------

slack_tools: list[Tool] = [
    # Conversations
    slack_list_conversations,
    slack_get_conversation_info,
    slack_conversations_history,
    slack_conversations_replies,
    slack_conversations_members,
    slack_conversations_join,
    slack_conversations_leave,
    slack_conversations_open,
    # Messages
    slack_chat_post_message,
    slack_chat_update,
    slack_chat_delete,
    slack_reactions_add,
    slack_reactions_remove,
    # Search
    slack_search_messages,
    # Users
    slack_users_list,
    slack_users_info,
    slack_users_lookup_by_email,
    slack_auth_test,
    # Team
    slack_team_info,
    # Bookmarks
    slack_bookmarks_list,
    # Pins
    slack_pins_list,
    slack_pins_add,
    slack_pins_remove,
    # Reminders
    slack_reminders_list,
    slack_reminders_add,
    slack_reminders_delete,
    # Files
    slack_files_list,
    slack_files_info,
]
