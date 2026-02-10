# Integrating Splunk Enterprise with Claude AI: A Complete Guide to the Splunk MCP Server

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Intermediate  
**Time Required:** 30-45 minutes  
**Prerequisites:** [Splunk-Docker-HomeLab](../Splunk-Docker-HomeLab/) setup complete

---

## Introduction

Imagine asking your AI assistant: *"Create indexes for my Linux and Windows logs, then show me what data is flowing in"* — and having it done in seconds. This guide connects **Splunk Enterprise** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude direct access to search your SIEM, list indexes, manage KV stores, and inspect your entire Splunk environment through natural conversation.

This is a companion to the [Splunk Docker HomeLab](../Splunk-Docker-HomeLab/) guide. If you haven't deployed Splunk in Docker yet, start there first.

By the end of this guide, you'll have:
- 12+ Splunk tools available in Claude Desktop
- Real-time search capability across all your indexes
- Index and sourcetype inspection through conversation
- KV store management for lookups and enrichment data
- A dedicated Claude Desktop profile for Splunk operations

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude talk to your security infrastructure.

### What You'll Need

- **Splunk Enterprise** running in Docker (see [Splunk-Docker-HomeLab](../Splunk-Docker-HomeLab/))
- **Claude Desktop** application
- **Docker** and Docker Compose
- **Linux workstation** (this guide uses Pop!_OS/Ubuntu)
- The `splunk-net` Docker network already created

---

## Architecture Overview

```
┌─────────────────┐     stdio      ┌──────────────────┐    REST API    ┌─────────────────┐
│  Claude Desktop │◄──────────────►│  Splunk MCP      │◄─────────────►│  Splunk         │
│                 │   JSON-RPC     │  (Docker)        │   Port 8089   │  Enterprise     │
│                 │                │  splunk_mcp-mcp  │   (HTTPS)     │  (Docker)       │
└─────────────────┘                └──────────────────┘               └─────────────────┘
                                          │                                  │
                                          └──────── splunk-net ──────────────┘
                                              (isolated Docker network)
```

**How it works:**
1. Claude Desktop launches the MCP container in **stdio mode** on every conversation
2. The container connects to Splunk's REST API on port 8089 via the shared `splunk-net` Docker network
3. Claude can search, list indexes, inspect sourcetypes, and manage KV stores through natural language
4. The container uses the hostname `splunk` (not localhost) because both containers share the same Docker network

---

## Part 1: Clone and Build the Splunk MCP Server

### Step 1: Clone the Repository

```bash
mkdir -p ~/Documents/Docker_Projects/SPLUNK_MCP
cd ~/Documents/Docker_Projects/SPLUNK_MCP

git clone https://github.com/livehybrid/splunk-mcp.git Splunk_MCP
cd Splunk_MCP
```

### Step 2: Create Your Environment File

```bash
cat > .env << 'EOF'
SPLUNK_HOST=splunk
SPLUNK_PORT=8089
SPLUNK_USERNAME=admin
SPLUNK_PASSWORD=YourSplunkPassword
SPLUNK_SCHEME=https
VERIFY_SSL=false
FASTMCP_LOG_LEVEL=DEBUG
PUBLISH_PORT=8002
EOF
```

> ⚠️ **Key Configuration Notes:**
>
> 1. **SPLUNK_HOST=splunk** — Uses the container hostname, NOT localhost. Both containers are on the same Docker network (`splunk-net`), so they communicate by container name.
> 2. **VERIFY_SSL=false** — Splunk's Docker image uses a self-signed certificate. Required for home lab setups.
> 3. **PUBLISH_PORT=8002** — The SSE mode port. We use 8002 because 8001 was already taken by mcp-kali in our environment. Adjust if needed.

### Step 3: Fix the FastMCP Compatibility Issue (Critical)

The `livehybrid/splunk-mcp` project specifies `mcp>=1.5.0` as a dependency, but versions `1.12.3+` introduced a breaking change that removed the `description` parameter from `FastMCP.__init__()`. This causes the server to crash on startup with:

```
TypeError: FastMCP.__init__() got an unexpected keyword argument 'description'
```

**The fix:** Pin the `mcp` package to a compatible version:

```bash
sed -i 's/"mcp>=1.5.0"/"mcp>=1.5.0,<1.12.3"/' pyproject.toml
```

This ensures the installed version supports the `description` kwarg.

### Step 4: Build the Docker Image

```bash
docker compose build
```

You'll see warnings about `SPLUNK_TOKEN` not being set — that's fine, we're using username/password authentication.

### Step 5: Test with SSE Mode (Optional)

Before wiring into Claude Desktop, you can verify the server works in SSE mode:

```bash
docker run -d --name splunk-mcp \
  --network splunk-net \
  -p 8002:8001 \
  -e SPLUNK_HOST=splunk \
  -e SPLUNK_PORT=8089 \
  -e SPLUNK_USERNAME=admin \
  -e "SPLUNK_PASSWORD=YourSplunkPassword" \
  -e SPLUNK_SCHEME=https \
  -e VERIFY_SSL=false \
  -e FASTMCP_LOG_LEVEL=DEBUG \
  -e FASTMCP_PORT=8001 \
  -e MODE=sse \
  splunk_mcp-mcp
```

Check the logs:

```bash
docker logs splunk-mcp
```

Expected output:
```
2026-02-09 20:19:40,299 - __main__ - INFO - 🚀 Starting Splunk MCP server in SSE mode
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

Test the SSE endpoint:

```bash
curl -s http://localhost:8002/sse
# Expected: event: endpoint
# data: /messages/?session_id=...
```

Clean up the test container (Claude Desktop will launch its own):

```bash
docker rm -f splunk-mcp
```

---

## Part 2: Configure Claude Desktop

### Claude Desktop Profile System

This guide uses a profile-based system for managing Claude Desktop configurations. Each profile is a separate JSON file that gets loaded as the active `claude_desktop_config.json`.

```
~/.config/Claude/profiles/
├── pentest.json       ← 8 servers (BloodHound, Burp, HexStrike, Wazuh, etc.)
├── content.json       ← 8 servers (YouTube, LinkedIn, Discord, OBS, etc.)
├── studying.json      ← 5 servers (CyberRAG, StudyCompanion, fetch, filesystem, github)
├── testing.json       ← 3 servers (lightweight sandbox)
├── splunk.json        ← 4 servers (Splunk SIEM, fetch, filesystem, github)
└── Original_test.json
```

### Step 1: Create the Splunk Profile

```bash
cat > ~/.config/Claude/profiles/splunk.json << 'EOF'
{
    "mcpServers": {
        "fetch": {
            "command": "docker",
            "args": ["run", "-i", "--rm", "mcp/fetch"]
        },
        "filesystem": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "-v", "/home/obi1:/mnt/obi1",
                "-v", "/etc:/mnt/etc",
                "mcp/filesystem",
                "/mnt/obi1",
                "/mnt/etc"
            ]
        },
        "github": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN=YOUR_GITHUB_PAT",
                "ghcr.io/github/github-mcp-server", "stdio",
                "--toolsets=default"
            ]
        },
        "splunk": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "--network", "splunk-net",
                "-e", "SPLUNK_HOST=splunk",
                "-e", "SPLUNK_PORT=8089",
                "-e", "SPLUNK_USERNAME=admin",
                "-e", "SPLUNK_PASSWORD=YourSplunkPassword",
                "-e", "SPLUNK_SCHEME=https",
                "-e", "VERIFY_SSL=false",
                "splunk_mcp-mcp",
                "python", "splunk_mcp.py", "stdio"
            ]
        }
    }
}
EOF
```

> ⚠️ **Important:** Replace `YOUR_GITHUB_PAT` and `YourSplunkPassword` with your actual credentials.

**Key design decisions:**
- **`--network splunk-net`** — Places the MCP container on the same network as Splunk, enabling hostname resolution
- **`--rm`** — Automatically removes the container when Claude Desktop closes the connection
- **`python splunk_mcp.py stdio`** — Runs in stdio mode for direct Claude Desktop communication
- **No port mapping needed** — stdio mode communicates through stdin/stdout, not HTTP

### Step 2: Switch to the Splunk Profile

```bash
claude-profile splunk
```

### Step 3: Restart Claude Desktop

Fully quit Claude Desktop (not just close the window) and relaunch it. The Splunk tools should appear in the tools menu.

---

## Part 3: Available Tools

Once connected, you'll have access to these Splunk tools:

### Health & Connectivity
| Tool | Description |
|------|-------------|
| `ping` | Verify the MCP server is alive |
| `health_check` | Test connectivity to Splunk and list available apps |

### Index Management
| Tool | Description |
|------|-------------|
| `list_indexes` | List all accessible Splunk indexes |
| `get_index_info` | Get detailed info about a specific index |
| `indexes_and_sourcetypes` | List all indexes with their sourcetypes |

### Search
| Tool | Description |
|------|-------------|
| `search_splunk` | Execute SPL queries with time range and result limits |
| `list_saved_searches` | List all saved searches |

### User Management
| Tool | Description |
|------|-------------|
| `current_user` | Show the authenticated user's info |
| `list_users` | List all Splunk users and their roles |

### KV Store
| Tool | Description |
|------|-------------|
| `list_kvstore_collections` | List all KV store collections |
| `create_kvstore_collection` | Create a new KV store collection |
| `delete_kvstore_collection` | Delete a KV store collection |

---

## Part 4: Setting Up Indexes with Claude

One of the first things you'll want to do is create custom indexes for your log sources. The MCP tools are read-only for index creation, but Claude can generate the commands for you.

We created a setup script to handle index creation and receiver configuration:

```bash
cat > /tmp/splunk_setup.sh << 'SCRIPT'
#!/bin/bash
SPLUNK_PASS='YourSplunkPassword'
SPLUNK_URL='https://localhost:8089'

echo "Creating linux_logs..."
curl -sk -u admin:"$SPLUNK_PASS" "$SPLUNK_URL/services/data/indexes" \
  -d name=linux_logs -d datatype=event -d maxTotalDataSizeMB=50000 \
  -o /dev/null -w "%{http_code}\n"

echo "Creating windows_logs..."
curl -sk -u admin:"$SPLUNK_PASS" "$SPLUNK_URL/services/data/indexes" \
  -d name=windows_logs -d datatype=event -d maxTotalDataSizeMB=50000 \
  -o /dev/null -w "%{http_code}\n"

echo "Creating network_logs..."
curl -sk -u admin:"$SPLUNK_PASS" "$SPLUNK_URL/services/data/indexes" \
  -d name=network_logs -d datatype=event -d maxTotalDataSizeMB=50000 \
  -o /dev/null -w "%{http_code}\n"

echo "Enabling receiving on port 9997..."
curl -sk -u admin:"$SPLUNK_PASS" "$SPLUNK_URL/services/data/inputs/splunktcp" \
  -d name=9997 -o /dev/null -w "%{http_code}\n"

echo "Done!"
SCRIPT
chmod +x /tmp/splunk_setup.sh
bash /tmp/splunk_setup.sh
```

Expected output: `201` for each new index, `409` if it already exists.

Then verify through Claude Desktop:
> **You:** List my Splunk indexes.
>
> **Claude:** *[Calls list_indexes]* You have 16 indexes: linux_logs, windows_logs, network_logs, main, plus the internal Splunk indexes...

---

## Part 5: Example Conversations

Once everything is connected, here's what you can do:

### Check Server Health
> **You:** Is my Splunk instance healthy?
>
> **Claude:** *[Calls health_check]* Your Splunk instance is healthy. Connected to splunk:8089 over HTTPS. 21 apps installed including Search & Reporting (10.2.0), Dashboard Studio (1.23.5), and Monitoring Console (10.4.0).

### List All Indexes
> **You:** What indexes do I have?
>
> **Claude:** *[Calls list_indexes]* You have 16 indexes: 3 custom (linux_logs, windows_logs, network_logs), main, and 12 internal Splunk indexes.

### Search for Data
> **You:** Search for any failed SSH logins in the last 24 hours.
>
> **Claude:** *[Calls search_splunk]* `search index=linux_logs sourcetype=syslog "Failed password" earliest=-24h`

### Inspect Index Details
> **You:** How much data is in my linux_logs index?
>
> **Claude:** *[Calls get_index_info]* The linux_logs index is using 0 MB currently with a max capacity of 50,000 MB. No data yet — we need to set up forwarders!

### View Sourcetypes
> **You:** What sourcetypes are flowing into each index?
>
> **Claude:** *[Calls indexes_and_sourcetypes]* Here's the breakdown of what data is flowing into each index...

---

## Part 6: Next Steps — Forwarder Setup

With indexes created and the MCP connection live, the next step is getting data flowing:

### Pop!_OS / Linux Forwarder
1. Download the Splunk Universal Forwarder for Linux
2. Configure it to monitor `/var/log/syslog`, `/var/log/auth.log`, `/var/log/kern.log`
3. Set the default index to `linux_logs`
4. Point the forwarder at your Splunk Docker host on port 9997

### Windows Forwarder
1. Download the Splunk Universal Forwarder for Windows
2. Configure it to collect Windows Event Logs (Security, System, Application)
3. Set the default index to `windows_logs`
4. Point the forwarder at your Splunk Docker host on port 9997

---

## Troubleshooting

### FastMCP TypeError: unexpected keyword argument 'description'

**Cause:** The `mcp` package version 1.12.3+ removed the `description` parameter from `FastMCP.__init__()`.

**Solution:** Pin the mcp version in `pyproject.toml`:
```bash
sed -i 's/"mcp>=1.5.0"/"mcp>=1.5.0,<1.12.3"/' pyproject.toml
docker compose build
```

### Container Starts But Can't Reach Splunk

**Cause:** The MCP container isn't on the `splunk-net` network.

**Solution:** Ensure `--network splunk-net` is in the docker run command or Claude Desktop config. Verify with:
```bash
docker network inspect splunk-net
```

### "Unauthorized" Error

**Cause:** Wrong password or username.

**Solution:** Verify credentials work:
```bash
curl -sk -u admin:YourPassword https://localhost:8089/services/server/info | head -5
```

### SSE Endpoint Returns Nothing

**Cause:** Server crashed on startup.

**Solution:** Check logs:
```bash
docker logs splunk-mcp
```

### Port 8002 Already in Use

**Cause:** Another service on that port.

**Solution:** Change `PUBLISH_PORT` in `.env` and update the docker run command. Note: this only affects SSE mode testing — stdio mode for Claude Desktop doesn't use host ports.

### Terminal Concatenating Commands

**Cause:** Some terminal emulators (especially with Zsh + clipboard managers) paste previous clipboard content into the current command.

**Solution:** Use script files instead of long one-liners. Or press `Ctrl+A` then `Ctrl+K` to clear the line before pasting.

---

## Quick Reference

| Action | Command |
|--------|---------|
| Build MCP image | `cd ~/Documents/Docker_Projects/SPLUNK_MCP/Splunk_MCP && docker compose build` |
| Test SSE mode | `docker run -d --name splunk-mcp --network splunk-net -p 8002:8001 -e SPLUNK_HOST=splunk -e SPLUNK_PORT=8089 -e SPLUNK_USERNAME=admin -e "SPLUNK_PASSWORD=YourPass" -e SPLUNK_SCHEME=https -e VERIFY_SSL=false -e FASTMCP_PORT=8001 -e MODE=sse splunk_mcp-mcp` |
| Switch profile | `claude-profile splunk` |
| Check logs | `docker logs splunk-mcp` |
| Test SSE endpoint | `curl -s http://localhost:8002/sse` |
| Verify indexes | Ask Claude: *"List my Splunk indexes"* |

---

## Resources

- [livehybrid/splunk-mcp](https://github.com/livehybrid/splunk-mcp) — The MCP server we deployed
- [splunk/splunk-mcp-server2](https://github.com/splunk/splunk-mcp-server2) — Alternative with SPL guardrails
- [Splunk-Docker-HomeLab](../Splunk-Docker-HomeLab/) — Our companion guide for deploying Splunk in Docker
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)
- [Splunk REST API Reference](https://docs.splunk.com/Documentation/Splunk/latest/RESTREF/RESTprolog)

---

*Your SIEM now speaks AI. Time to hunt. 🛡️*

**— Hackerobi**
