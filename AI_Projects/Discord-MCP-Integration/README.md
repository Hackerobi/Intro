# Integrating Discord with Claude AI: A Complete Guide to the Discord MCP Server

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Beginner-Intermediate  
**Time Required:** 30-45 minutes

---

## Introduction

Imagine telling your AI assistant: *"Create a cybersecurity-focused Discord server with channels for CTFs, certifications, and penetration testing"* — and watching it build the entire thing in real time. This guide will show you how to connect **Discord** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude direct control over your Discord server management.

By the end of this guide, you'll have:
- 21 Discord management tools available in Claude Desktop
- AI-powered channel and category creation
- Automated message sending, editing, and management
- Webhook integration for notifications and automation
- The ability to manage your Discord community through natural conversation

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude talk to your favorite platforms — in this case, Discord.

### What You'll Need

- **Discord account** with a server you own or administer
- **Claude Desktop** application
- **Docker** installed and running
- **Linux workstation** (this guide uses Pop!_OS/Ubuntu, but works on any OS)
- Basic familiarity with command line

---

## Architecture Overview

```
┌─────────────────┐     stdio      ┌──────────────────┐    Discord     ┌─────────────────┐
│  Claude Desktop │◄──────────────►│  Discord MCP     │◄──────────────►│  Discord API    │
│                 │   JSON-RPC     │  Server (Docker)  │    Gateway     │  (JDA)          │
└─────────────────┘                └──────────────────┘               └────────┬────────┘
                                                                               │
                                                                               ▼
                                                                    ┌──────────────────┐
                                                                    │  Your Discord    │
                                                                    │  Server          │
                                                                    └──────────────────┘
```

The Discord MCP server uses **JDA (Java Discord API)** to connect to Discord's gateway. Claude Desktop communicates with it via stdio, and the server translates those commands into Discord API calls.

---

## Part 1: Creating Your Discord Bot

### Step 1: Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"**
3. Name it something meaningful (e.g., `ObiSecBot`)
4. Click **Create**

### Step 2: Configure the Bot

Navigate to the **Bot** tab in the left sidebar:

1. Click **"Reset Token"** to generate your bot token
2. **Copy the token immediately** — you won't see it again
3. Store it somewhere secure (password manager, encrypted notes)

Enable these **Privileged Gateway Intents**:
- ✅ **Presence Intent** — Required for presence update events
- ✅ **Server Members Intent** — Required for member-related events
- ✅ **Message Content Intent** — Required for reading message content

### Step 3: Set Bot Permissions via OAuth2

Navigate to the **OAuth2** tab:

1. Scroll down to the **OAuth2 URL Generator**
2. Under **Scopes**, check: `bot`
3. Under **Bot Permissions**, select:

**General Permissions:**
- Manage Channels
- Manage Webhooks
- View Channels
- Manage Roles

**Text Permissions:**
- Send Messages
- Manage Messages
- Read Message History
- Add Reactions
- Embed Links
- Attach Files

4. Copy the **Generated URL** at the bottom
5. Open it in your browser to invite the bot to your server

### Step 4: Get Your Server (Guild) ID

1. In Discord, go to **Settings → Advanced → Developer Mode** (toggle ON)
2. Right-click your server name in the sidebar
3. Click **"Copy Server ID"**
4. Save this ID alongside your bot token

---

## Part 2: Setting Up the MCP Server

### Step 1: Pull the Docker Image

```bash
docker pull saseq/discord-mcp:latest
```

### Important: Platform Compatibility

The official Docker image is built for **ARM64 (arm64/v8)**. If you're running on an **AMD64/x86_64** system (most Linux desktops and laptops), the container will run under QEMU emulation and be extremely slow — causing initialization timeouts.

**Check your architecture:**
```bash
uname -m
# x86_64 = AMD64 (needs native build)
# aarch64 = ARM64 (official image works fine)
```

**If you're on AMD64, build natively:**
```bash
cd ~/Documents/Docker_Projects
git clone https://github.com/SaseQ/discord-mcp.git
cd discord-mcp
docker build -t discord-mcp:local .
```

Use `discord-mcp:local` instead of `saseq/discord-mcp:latest` in your config below.

### Step 2: Test the Container

```bash
docker run --rm -it \
  -e "DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE" \
  -e "DISCORD_GUILD_ID=YOUR_SERVER_ID_HERE" \
  discord-mcp:local
```

You should see the JDA bot connect to Discord's gateway. If it hangs or crashes, check:
- Your bot token is correct
- The bot has been invited to the server
- You're using the native build (not ARM on AMD64)

Press `Ctrl+C` to stop the test.

---

## Part 3: Configuring Claude Desktop

### Locate Your Config File

```bash
# Linux
~/.config/Claude/claude_desktop_config.json

# macOS
~/Library/Application Support/Claude/claude_desktop_config.json

# Windows
%APPDATA%\Claude\claude_desktop_config.json
```

### Add the Discord MCP Server

Add this to your `mcpServers` block:

```json
{
  "mcpServers": {
    "discord-mcp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE",
        "-e", "DISCORD_GUILD_ID=YOUR_SERVER_ID_HERE",
        "discord-mcp:local"
      ]
    }
  }
}
```

> 💡 **Tip:** If you already have other MCP servers configured, just add the `"discord-mcp"` entry inside the existing `mcpServers` object.

### Restart Claude Desktop

Close and reopen Claude Desktop. The Discord tools should now appear in the tools list.

---

## Part 4: Available Tools

Once connected, you'll have access to **21 Discord management tools**:

### Server Information
| Tool | Description |
|------|-------------|
| `get_server_info` | Get detailed server information (members, channels, boosts) |

### User Management
| Tool | Description |
|------|-------------|
| `get_user_id_by_name` | Look up a user's ID by username for mentions |
| `send_private_message` | Send a DM to a specific user |
| `edit_private_message` | Edit a previously sent DM |
| `delete_private_message` | Delete a DM |
| `read_private_messages` | Read DM history with a user |

### Message Management
| Tool | Description |
|------|-------------|
| `send_message` | Send a message to a channel |
| `edit_message` | Edit a message in a channel |
| `delete_message` | Delete a message from a channel |
| `read_messages` | Read message history from a channel |
| `add_reaction` | Add an emoji reaction to a message |
| `remove_reaction` | Remove an emoji reaction from a message |

### Channel Management
| Tool | Description |
|------|-------------|
| `create_text_channel` | Create a new text channel |
| `delete_channel` | Delete a channel |
| `find_channel` | Find a channel by name |
| `list_channels` | List all channels in the server |

### Category Management
| Tool | Description |
|------|-------------|
| `create_category` | Create a new category |
| `delete_category` | Delete a category |
| `find_category` | Find a category by name |
| `list_channels_in_category` | List channels within a category |

### Webhook Management
| Tool | Description |
|------|-------------|
| `create_webhook` | Create a webhook on a channel |
| `delete_webhook` | Delete a webhook |
| `list_webhooks` | List webhooks on a channel |
| `send_webhook_message` | Send a message via webhook |

---

## Part 5: What We Built — A Real-World Example

Here's exactly what we accomplished using Claude + Discord MCP in a single conversation:

### The Goal
Transform a bare-bones Discord server (1 text channel, 1 voice channel) into a fully structured cybersecurity education and content creation community.

### The Result

Claude analyzed the existing server, proposed a channel structure, and built it all out:

```
📋 WELCOME & INFO
   ├── #rules-and-info
   └── #announcements

💬 GENERAL
   ├── #general-chat
   └── #introductions

🔐 CYBERSECURITY
   ├── #ctf-challenges
   ├── #penetration-testing
   ├── #certifications
   └── #tools-and-resources

🤖 AI & MCP
   ├── #mcp-integrations
   └── #ai-in-security

🎥 CONTENT
   ├── #stream-announcements
   └── #video-discussion
```

Claude also cleaned up the old default channels and categories — all through natural conversation. No manual clicking, no Discord UI navigation. Just:

> **Me:** "Clean up and rebrand this server for content creation focused on cybersecurity education and CTFs."
>
> **Claude:** *Creates 6 categories, 12 channels, deletes old defaults, verifies the structure.*

Total time: **Under 2 minutes.**

---

## Part 6: Example Conversations

### Build a Server From Scratch
> **You:** Create a Discord server structure for a cybersecurity study group with channels for CTFs, certs, and tools.
>
> **Claude:** *Creates categories, channels, and organizes everything based on your requirements.*

### Post Announcements
> **You:** Post an announcement in #stream-announcements that I'm going live at 8PM EST doing a HackTheBox walkthrough.
>
> **Claude:** *Sends a formatted message to the announcements channel.*

### Manage Webhooks
> **You:** Create a webhook in #announcements so I can send automated notifications from my CI/CD pipeline.
>
> **Claude:** *Creates the webhook and provides the URL.*

### Read and Moderate
> **You:** Show me the last 10 messages in #general-chat.
>
> **Claude:** *Retrieves and displays recent message history.*

### Clean Up Channels
> **You:** Delete the #old-channel and create a new one called #writeups under the CYBERSECURITY category.
>
> **Claude:** *Handles the deletion and creation in sequence.*

---

## Troubleshooting

### Initialization Timeout (Most Common)

**Symptom:** Log shows `MCP error -32001: Request timed out` after 60 seconds.

**Cause:** The Docker image is ARM64 and your system is AMD64. QEMU emulation makes JDA startup extremely slow.

**Solution:** Build the image natively:
```bash
git clone https://github.com/SaseQ/discord-mcp.git
cd discord-mcp
docker build -t discord-mcp:local .
```

### Bot Not Responding

**Symptom:** Container starts but tools return errors.

**Cause:** Missing privileged intents or insufficient permissions.

**Solution:** 
1. Enable all three intents in Developer Portal → Bot tab
2. Re-invite the bot using a fresh OAuth2 URL with correct permissions

### "Server transport closed unexpectedly"

**Symptom:** Container crashes immediately after starting.

**Cause:** Invalid bot token or the bot hasn't been invited to the specified guild.

**Solution:**
1. Verify your bot token is correct (reset it if unsure)
2. Confirm the bot is a member of the server matching your GUILD_ID
3. Test manually: `docker run --rm -it -e DISCORD_TOKEN=... -e DISCORD_GUILD_ID=... discord-mcp:local`

### Permission Errors on Specific Actions

**Symptom:** Some tools work but others fail (e.g., can read messages but can't create channels).

**Solution:** Re-invite the bot with the full permission set from Part 1, Step 3.

---

## Security Considerations

- 🔑 **Never commit your bot token to Git** — use environment variables or secrets management
- 🔒 **Rotate your bot token** if it's ever exposed (Developer Portal → Bot → Reset Token)
- 👁️ **The bot can read all channels it has access to** — be mindful of sensitive information
- 🛡️ **Use role-based permissions** in Discord to limit what channels the bot can access
- 📋 **Review bot permissions regularly** — only grant what's needed

---

## Quick Reference

### Start the MCP Server (via Claude Desktop)
The server starts automatically when Claude Desktop launches. No manual steps needed.

### Check Server Info
Ask Claude: *"Show me the server info for my Discord"*

### List All Channels
Ask Claude: *"List all channels in my Discord server"*

### Create a Channel
Ask Claude: *"Create a text channel called writeups in the CYBERSECURITY category"*

### Send a Message
Ask Claude: *"Send a welcome message to #general-chat"*

---

## Conclusion

You now have a fully functional integration between Discord and Claude Desktop. This setup allows you to:

- Manage your entire Discord server through natural conversation
- Create and organize channels and categories instantly
- Send messages, announcements, and automated notifications
- Set up webhooks for external integrations
- Read and moderate messages across your server

Combined with other MCP integrations like Wazuh, Burp Suite, and OBS, you now have an AI-powered command center for your cybersecurity content creation workflow — from security testing to streaming to community management, all through Claude.

### What's Next?

- 🎥 **Stream integration** — Use OBS MCP + Discord MCP for automated "going live" notifications
- 🔔 **Security alerts** — Pipe Wazuh alerts to a Discord channel via webhooks
- 🤖 **Automated moderation** — Use Claude to monitor and manage community discussions
- 📊 **CTF coordination** — Manage CTF teams and share challenges through Discord

---

## Resources

- [Discord Developer Portal](https://discord.com/developers/applications)
- [SaseQ/discord-mcp](https://github.com/SaseQ/discord-mcp) — The MCP server we used
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)
- [JDA (Java Discord API)](https://github.com/discord-jda/JDA)

---

*Happy hacking, and welcome to the community! 🎮🛡️*
