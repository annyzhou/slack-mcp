# Slack MCP Server

An MCP server implementation that integrates the Slack API, providing messaging, channel management, and search capabilities.

## Features

- **Conversations**: List channels, read message history, manage threads
- **Messaging**: Send, update, and delete messages; add reactions
- **Search**: Find messages across your workspace (user token only)
- **Users**: List users, get profiles, lookup by email
- **Files & Pins**: List files, manage pinned messages
- **Token Rotation**: Automatic refresh for rotatable tokens

## Tools

### Conversations
- `slack_list_conversations` - List channels, DMs, and group DMs
- `slack_get_conversation_info` - Get channel details
- `slack_conversations_history` - Fetch message history
- `slack_conversations_replies` - Get thread replies
- `slack_conversations_members` - List channel members
- `slack_conversations_join` - Join a public channel
- `slack_conversations_leave` - Leave a conversation
- `slack_conversations_open` - Open a DM or group DM

### Messages
- `slack_chat_post_message` - Send a message to a channel or thread
- `slack_chat_update` - Update an existing message
- `slack_chat_delete` - Delete a message
- `slack_reactions_add` - Add emoji reaction
- `slack_reactions_remove` - Remove emoji reaction

### Search
- `slack_search_messages` - Search messages (requires user token)

### Users
- `slack_users_list` - List workspace users
- `slack_users_info` - Get user details by ID
- `slack_users_lookup_by_email` - Find user by email
- `slack_auth_test` - Get current token info

### Other
- `slack_team_info` - Get workspace info
- `slack_bookmarks_list` - List channel bookmarks
- `slack_pins_list` / `slack_pins_add` / `slack_pins_remove` - Manage pins
- `slack_reminders_list` / `slack_reminders_add` / `slack_reminders_delete` - Manage reminders
- `slack_files_list` / `slack_files_info` - List and get file details

## Configuration

### Getting a Slack Token

1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Go to **OAuth & Permissions**
4. Add scopes under **Bot Token Scopes** or **User Token Scopes**:
   ```
   channels:read, channels:history, chat:write, users:read, team:read
   ```
5. Click **Install to Workspace**
6. Copy the token (`xoxb-...` or `xoxp-...`)

### Token Types

| Token | Prefix | Search? | Access |
|-------|--------|---------|--------|
| Bot | `xoxb-` | No | Invited channels only |
| User | `xoxp-` | Yes | All user's channels |
| Rotatable | `xoxe.xoxp-` | Yes | Auto-refreshes |

## Development

### Install Dependencies

```bash
uv sync
```

### Run the Server

```bash
uv run python src/main.py
```

### Test the API

```bash
uv run python test_api.py
```

### Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv run python src/main.py
```

## License

MIT License - see [LICENSE](LICENSE) for details.
