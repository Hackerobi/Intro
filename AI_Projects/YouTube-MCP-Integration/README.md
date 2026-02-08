# Integrating YouTube with Claude AI: A Complete Guide to the YouTube Channel Management MCP Server

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Beginner-Intermediate  
**Time Required:** 15-20 minutes

---

## Introduction

Imagine managing your YouTube channel by simply asking: *"Show me my latest video stats"* or *"Compare my last 5 videos by engagement rate"* and getting instant, structured results. This guide will show you how to connect **YouTube's Data API v3** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude direct access to YouTube channel analytics, video management, search, and competitive analysis.

By the end of this guide, you'll have:
- 12 YouTube management tools available in Claude Desktop
- Channel analytics at your fingertips (subscribers, views, engagement)
- Video search, comparison, and trending analysis
- Playlist management and comment reading
- Competitor channel analysis

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude interact with your favorite services — in this case, YouTube.

### What You'll Need

- **YouTube Data API v3 Key** (free from Google Cloud Console)
- **Claude Desktop** application
- **Python 3.10+** installed on your system
- **Linux workstation** (this guide uses Pop!_OS/Ubuntu — works on macOS/Windows too)
- Basic familiarity with command line

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Your Workstation                                   │
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────────────────────────────┐  │
│  │  Claude Desktop  │         │          YouTube Data API v3             │  │
│  │                  │         │       (googleapis.com/youtube)           │  │
│  └────────┬─────────┘         └──────────────────▲───────────────────────┘  │
│           │                                       │                          │
│           │ stdio                                 │ HTTPS (API Key)          │
│           ▼                                       │                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │              YouTube MCP Server (Python + venv)                      │   │
│  │                                                                      │   │
│  │  • Channel Info & Analytics    • Video Search & Discovery           │   │
│  │  • Video Details & Stats       • Playlist Management                │   │
│  │  • Comment Reading             • Trending Videos                    │   │
│  │  • Video Comparison            • Competitor Analysis                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**How It Works:**

1. You give Claude natural language instructions about YouTube
2. Claude translates them into MCP tool calls
3. The MCP server queries the YouTube Data API v3
4. Claude presents the results in a clear, conversational format

---

## The Journey: Why We Built This

Before building this custom server, I tried several existing YouTube MCP packages. Here's what I found:

### What Didn't Work

- **zubeid-youtube-mcp-server** (npm) — Fundamentally broken. The `@modelcontextprotocol/sdk` npm package has a CJS build bug where `dist/cjs/index.js` doesn't exist in any version. After hours of manual patching (creating missing module files, re-exporting symbols), we hit a final API incompatibility: the package uses the old `server.addMethod()` API while the SDK now requires `server.tool()`. [GitHub Issue #21](https://github.com/ZubeidHendricks/youtube-mcp-server/issues/21) confirms it's unusable.

- **adhikasp/mcp-youtube** — Works, but transcript-only. Doesn't provide channel management features.

### The Solution: Build It Ourselves

Since I'd already built custom MCP servers for [Wazuh SIEM](../Wazuh-MCP-Integration/), [Burp Suite](../Burp-Suite-MCP-Integration/), [OBS Studio](../OBS-MCP-Integration/), and [Discord](../Discord-MCP-Integration/), I knew the pattern. Python + FastMCP + the YouTube Data API client = a clean, working server in under an hour.

**No Docker required.** Unlike some of my other MCP integrations, this one runs directly in a Python virtual environment. Simple, fast, and lightweight.

---

## Part 1: Getting Your YouTube API Key

### Step 1: Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a Project** → **New Project**
3. Name it something like `youtube-mcp` and click **Create**

### Step 2: Enable the YouTube Data API v3

1. In your new project, go to **APIs & Services** → **Library**
2. Search for **YouTube Data API v3**
3. Click **Enable**

### Step 3: Create an API Key

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **API Key**
3. Copy the key — you'll need it for the configuration
4. *(Optional but recommended)* Click **Restrict Key** and limit it to the YouTube Data API v3

> **⚠️ Security Note:** Keep your API key safe. Don't commit it to public repos or share it publicly. The key gives access to your API quota.

---

## Part 2: Setting Up the MCP Server

### Step 1: Create Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/YouTube_MCP
cd ~/Documents/Docker_Projects/YouTube_MCP
```

### Step 2: Create the Server File

Create `youtube_mcp_server.py` — this is the complete MCP server with all 12 tools:

```python
#!/usr/bin/env python3
"""
YouTube Channel Management MCP Server
A Model Context Protocol server for managing YouTube channels via the YouTube Data API v3.

Author: Obi1 (Hackerobi)
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Logging to stderr so it doesn't interfere with MCP stdio
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [YouTube-MCP] %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("youtube-mcp")

# YouTube API client
API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
if not API_KEY:
    log.error("YOUTUBE_API_KEY environment variable is not set!")

def get_youtube_client():
    return build("youtube", "v3", developerKey=API_KEY)

mcp = FastMCP("YouTube Channel Manager")

# ... (see full source file: youtube_mcp_server.py)

if __name__ == "__main__":
    log.info("Starting YouTube Channel Management MCP Server v1.0.0")
    mcp.run(transport="stdio")
```

> **📄 The complete source code is included in this repository as [`youtube_mcp_server.py`](./youtube_mcp_server.py)**

### Step 3: Create requirements.txt

```
mcp>=1.0.0
google-api-python-client>=2.100.0
google-auth>=2.23.0
```

### Step 4: Set Up the Python Virtual Environment

```bash
cd ~/Documents/Docker_Projects/YouTube_MCP
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 5: Verify Installation

```bash
python3 -c "from mcp.server.fastmcp import FastMCP; print('✓ MCP SDK OK')"
python3 -c "from googleapiclient.discovery import build; print('✓ Google API Client OK')"
```

Both checks should print success messages.

---

## Part 3: Configuring Claude Desktop

### Step 1: Locate Your Config File

```bash
# Linux
~/.config/Claude/claude_desktop_config.json

# macOS
~/Library/Application Support/Claude/claude_desktop_config.json

# Windows
%APPDATA%\Claude\claude_desktop_config.json
```

### Step 2: Add the YouTube MCP Server

Add this to the `mcpServers` section of your config:

```json
"youtube": {
    "command": "/home/YOUR_USERNAME/Documents/Docker_Projects/YouTube_MCP/venv/bin/python3",
    "args": ["/home/YOUR_USERNAME/Documents/Docker_Projects/YouTube_MCP/youtube_mcp_server.py"],
    "env": {
        "YOUTUBE_API_KEY": "YOUR_API_KEY_HERE"
    }
}
```

Replace `YOUR_USERNAME` with your actual username and `YOUR_API_KEY_HERE` with your YouTube Data API v3 key.

> **🔒 Security Tip:** Set restrictive permissions on your config file since it contains your API key:
> ```bash
> chmod 600 ~/.config/Claude/claude_desktop_config.json
> ```

### Step 3: Restart Claude Desktop

Close and reopen Claude Desktop. You should see the YouTube tools become available.

### Verifying the Connection

Check the MCP logs to confirm a successful connection:

```bash
# Linux
tail -f ~/.config/Claude/logs/mcp-server-youtube.log
```

You should see:
```
Server started and connected successfully
Starting YouTube Channel Management MCP Server v1.0.0
API Key configured: Yes
```

---

## Part 4: Available Tools

Once connected, you'll have access to **12 YouTube management tools**:

### Channel Tools
| Tool | Description |
|------|-------------|
| `get_channel_info` | Detailed channel info — subscribers, views, videos, keywords, description |
| `get_channel_videos` | List channel videos sorted by date, views, or rating with full stats |
| `get_channel_playlists` | List all playlists on a channel |

### Video Tools
| Tool | Description |
|------|-------------|
| `get_video_details` | Full video metadata — tags, stats, status, topics, duration |
| `get_video_comments` | Read comments with replies, sorted by relevance or time |

### Search
| Tool | Description |
|------|-------------|
| `search_youtube` | Search videos/channels/playlists with filters (duration, date, region) |

### Playlist Tools
| Tool | Description |
|------|-------------|
| `get_playlist_details` | Playlist metadata and item count |
| `get_playlist_items` | List all videos in a playlist with positions |

### Analytics & Comparison
| Tool | Description |
|------|-------------|
| `compare_videos` | Side-by-side video stats with engagement rates |
| `get_trending_videos` | Regional trending videos, filterable by category |
| `get_video_categories` | List available YouTube categories per region |
| `channel_competitor_analysis` | Compare multiple channels — subs, views, efficiency metrics |

---

## Part 5: Example Conversations

### Get Channel Info
> **You:** Tell me about John Hammond's YouTube channel
>
> **Claude:** *[Calls get_channel_info with handle @JohnHammond]*
> John Hammond's channel has 2.1M subscribers, 84.7M total views across 1,775 videos. He focuses on free cybersecurity education and ethical hacking, and he's been active since 2011.

### Search for Content
> **You:** Find recent cybersecurity CTF walkthrough videos
>
> **Claude:** *[Calls search_youtube]* Here are the latest CTF walkthrough videos...

### Compare Videos
> **You:** Compare these three videos and tell me which performed best
>
> **Claude:** *[Calls compare_videos]* Here's the comparison with engagement rates...

### Competitor Analysis
> **You:** Compare John Hammond, NetworkChuck, and David Bombal's channels
>
> **Claude:** *[Calls channel_competitor_analysis]* Here's the side-by-side breakdown of all three channels...

### Trending Videos
> **You:** What's trending in Science & Tech right now?
>
> **Claude:** *[Calls get_trending_videos with category_id 28]* Here are the top trending tech videos...

### Read Comments
> **You:** Show me the top comments on that video
>
> **Claude:** *[Calls get_video_comments]* Here are the most relevant comments...

### Playlist Management
> **You:** List all playlists on my channel and show me what's in the first one
>
> **Claude:** *[Calls get_channel_playlists, then get_playlist_items]* You have 5 playlists. Here's the contents of your first playlist...

---

## Part 6: Troubleshooting

### "YOUTUBE_API_KEY environment variable is not set!"

**Cause:** The API key isn't being passed to the server.

**Solution:**
1. Check your `claude_desktop_config.json` — make sure the `env` block is present with your key
2. Ensure there are no typos in the key
3. Restart Claude Desktop after making changes

### "FastMCP.__init__() got an unexpected keyword argument 'version'"

**Cause:** The installed version of the MCP SDK doesn't support the `version` parameter.

**Solution:** Use the simple constructor:
```python
mcp = FastMCP("YouTube Channel Manager")
```

### "YouTube API error: 403"

**Cause:** API key issues or quota exceeded.

**Solution:**
1. Verify your API key is valid in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Check that the YouTube Data API v3 is **enabled** for your project
3. Check your [quota usage](https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas) — default is 10,000 units/day

### "Server transport closed unexpectedly"

**Cause:** The Python process crashed during startup.

**Solution:**
1. Test the server manually:
   ```bash
   cd ~/Documents/Docker_Projects/YouTube_MCP
   source venv/bin/activate
   YOUTUBE_API_KEY=your_key_here python3 youtube_mcp_server.py
   ```
2. Check for import errors or missing dependencies
3. Ensure you're using the venv Python (`venv/bin/python3`), not system Python

### Tools Not Appearing in Claude Desktop

**Solution:**
1. Check the MCP log: `~/.config/Claude/logs/mcp-server-youtube.log`
2. Verify JSON syntax in your config file (use a JSON validator)
3. Make sure the paths in your config are absolute (no `~`)
4. Restart Claude Desktop completely (not just reload)

---

## Part 7: API Quota Management

The YouTube Data API v3 has a default quota of **10,000 units per day**. Here's what each operation costs:

| Operation | Cost (units) |
|-----------|-------------|
| `search.list` | 100 |
| `videos.list` | 1 |
| `channels.list` | 1 |
| `playlists.list` | 1 |
| `playlistItems.list` | 1 |
| `commentThreads.list` | 1 |
| `videoCategories.list` | 1 |

**Tips for managing quota:**
- Search is the most expensive operation (100 units). Use it sparingly.
- Channel/video info lookups are cheap (1 unit each). Use freely.
- The `get_channel_videos` tool uses a search call (100 units) + a videos call (1 unit).
- Monitor your usage at the [Google Cloud Console](https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas)

---

## Quick Reference

### Setup Commands
```bash
# Create project
mkdir -p ~/Documents/Docker_Projects/YouTube_MCP
cd ~/Documents/Docker_Projects/YouTube_MCP

# Create venv and install
python3 -m venv venv
source venv/bin/activate
pip install mcp google-api-python-client google-auth

# Test
python3 -c "from mcp.server.fastmcp import FastMCP; print('OK')"
```

### Common Claude Commands
```
"Tell me about @ChannelName's YouTube channel"
"Show me the latest videos from channel UC..."
"Search YouTube for [topic]"
"Compare these videos: id1, id2, id3"
"What's trending in Science & Tech?"
"Show me comments on video [id]"
"List playlists for channel UC..."
"Compare these channels: UC1, UC2, UC3"
```

### File Locations
```
Server:  ~/Documents/Docker_Projects/YouTube_MCP/youtube_mcp_server.py
Venv:    ~/Documents/Docker_Projects/YouTube_MCP/venv/
Config:  ~/.config/Claude/claude_desktop_config.json
Logs:    ~/.config/Claude/logs/mcp-server-youtube.log
```

---

## Resources

- [YouTube Data API v3 Documentation](https://developers.google.com/youtube/v3)
- [Google Cloud Console](https://console.cloud.google.com/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)
- [Python google-api-python-client](https://github.com/googleapis/google-api-python-client)

---

*Happy hacking! Use these tools to understand your audience, analyze your content, and grow your channel.* 📺

**— Hackerobi**