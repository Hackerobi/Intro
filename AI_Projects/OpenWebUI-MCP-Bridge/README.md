# OpenWebUI MCP Bridge: Expose All Your MCP Tools to OpenWebUI

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Intermediate  
**Time Required:** 30-45 minutes

---

## Introduction

Imagine telling your OpenWebUI instance: *"List my GitHub repositories"* — and watching it call your MCP-connected GitHub tool server, return the results, and format them beautifully. Now imagine doing that with **every MCP server you've already built** — Wazuh, BloodHound, Burp Suite, SysReptor, Discord, YouTube, LitterBox, and more — all accessible through a single OpenWebUI endpoint.

This guide shows you how to build an **MCP-to-OpenAPI bridge** that takes your existing Claude Desktop MCP server configurations and exposes them to OpenWebUI through a unified proxy. No rebuilding, no reconfiguring — your existing MCP servers work as-is.

By the end of this guide, you'll have:
- All your existing MCP tools available in OpenWebUI
- A single endpoint that proxies multiple MCP servers
- Profile-based server grouping (pentest tools, content tools, etc.)
- Zero changes to your existing MCP server configurations
- The ability to use the same JSON profiles from Claude Desktop

### What is OpenWebUI?

[OpenWebUI](https://github.com/open-webui/open-webui) is a self-hosted, feature-rich web interface for AI models. It supports tool/function calling through OpenAPI-compatible endpoints — which is exactly what we're bridging to.

### What is the MCP Bridge?

The bridge sits between OpenWebUI and your MCP servers:

```
┌─────────────┐      HTTP/REST       ┌──────────────┐      stdio       ┌────────────────────┐
│             │  ←─────────────────→ │              │  ←──────────────→│  MCP Server: fetch  │
│  OpenWebUI  │   OpenAPI (JSON)     │  mcpo proxy  │                  ├────────────────────┤
│  (port 3000)│  ←─────────────────→ │  (port 7734) │  ←──────────────→│  MCP Server: github │
│             │                      │              │                  ├────────────────────┤
│             │                      │      ↕       │  ←──────────────→│  MCP Server: wazuh  │
│             │                      │  FastMCP     │                  ├────────────────────┤
│             │                      │  Bridge      │  ←──────────────→│  MCP Server: burp   │
│             │                      │  (stdio)     │                  ├────────────────────┤
│             │                      │              │  ←──────────────→│  ... any MCP server │
└─────────────┘                      └──────────────┘                  └────────────────────┘
```

**How it works:**

1. The FastMCP bridge reads your Claude Desktop JSON profile (same `mcpServers` format)
2. FastMCP's `as_proxy()` creates proxy connections to each MCP server via stdio
3. `mcpo` wraps the bridge in an OpenAPI-compatible HTTP server
4. OpenWebUI connects to mcpo as a standard OpenAPI tool server
5. You talk to your LLM in OpenWebUI, it calls your MCP tools naturally

**The key insight:** FastMCP v2 natively understands the `mcpServers` dictionary format from Claude Desktop. We just pass it straight through — no translation layer needed.

### What You'll Need

- **Linux workstation** (this guide uses Pop!_OS, but Ubuntu/Debian will work)
- **Python 3.10+**
- **Docker Engine** (if your MCP servers run in Docker containers)
- **uv** (for running mcpo — the MCP-to-OpenAPI proxy)
- **OpenWebUI** running and accessible
- **Existing MCP server configurations** (Claude Desktop JSON profiles)

---

## Architecture Overview

### Two Configuration Modes

**Mode 1: Claude Desktop JSON (Recommended)**
Pass your existing Claude Desktop profile JSON files directly. Zero config duplication.

```bash
./start.sh ~/.config/Claude/profiles/testing.json
```

**Mode 2: YAML Config**
Define servers and profiles in a `servers.yaml` file for more control over grouping and metadata.

```bash
./start.sh pentest
```

### How the Proxy Chain Works

```
OpenWebUI → HTTP request to mcpo (port 7734)
         → mcpo translates to MCP protocol (stdio)
         → FastMCP bridge receives MCP request
         → FastMCP proxies to the correct MCP server (stdio)
         → MCP server processes and returns result
         → Response flows back up the chain
         → OpenWebUI displays the result
```

---

## Quick Start

```bash
# 1. Clone/create the project
mkdir -p ~/Documents/Docker_Projects/OpenWebUI_MCP
cd ~/Documents/Docker_Projects/OpenWebUI_MCP

# 2. Copy the project files (main.py, servers/, scripts/)

# 3. Make the launcher executable
chmod +x scripts/start.sh
ln -sf scripts/start.sh start.sh

# 4. Launch with your existing Claude Desktop profile
./start.sh ~/.config/Claude/profiles/testing.json

# 5. In OpenWebUI: Settings → Tools → Add http://localhost:7734
```

---

## Prerequisites

```bash
python3 --version        # Python 3.10 or higher
docker --version         # For Docker-based MCP servers
uvx --version            # For mcpo proxy
```

Install uv if needed:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Project Structure

```
OpenWebUI_MCP/
├── main.py                 # CLI entry point — routes JSON vs YAML profiles
├── servers/
│   ├── bridge.py           # FastMCP bridge engine — as_proxy() + MCPConfig
│   └── config_loader.py    # Config parsing (YAML + Claude Desktop JSON)
├── configs/
│   └── servers.yaml        # Server definitions and profiles (optional)
├── scripts/
│   └── start.sh            # Launcher with auto-venv setup
├── .env                    # Your secrets (git-ignored)
└── .env.example            # Template for secrets
```

---

## Creating Your Server Profile

### Option A: Use Your Existing Claude Desktop JSON (Easiest)

```json
{
  "mcpServers": {
    "fetch": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "mcp/fetch"]
    },
    "github": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

```bash
./start.sh ~/.config/Claude/profiles/testing.json
```

### Option B: Create a YAML Config (Custom Profiles)

See `configs/servers.yaml` for the full template with server definitions and profile grouping.

---

## Launch and Connect

### Start the Bridge

```bash
./start.sh ~/.config/Claude/profiles/testing.json
```

Expected output:
```
🔗 OpenWebUI MCP Bridge

✓ Using Python: /path/to/venv/bin/python3
Mode: mcpo proxy (port 7734)
...
Secure MCP Filesystem Server running on stdio
GitHub MCP Server running on stdio
Application startup complete.
Uvicorn running on http://0.0.0.0:7734 (Press CTRL+C to quit)
```

### Connect OpenWebUI

1. Open **OpenWebUI** → **Settings** → **Tools** → **OpenAPI Servers**
2. Add URL: `http://localhost:7734`
3. Save

### Test It

Send this to your LLM in OpenWebUI:

> **"List the repositories for the GitHub user Hackerobi. If you cannot do this, explain exactly why."**

---

## Usage Reference

```bash
# Claude Desktop JSON profile
./start.sh ~/.config/Claude/profiles/testing.json

# YAML profile
./start.sh pentest

# Custom port
./start.sh --port 9000 ~/.config/Claude/profiles/testing.json

# Standalone mode (HTTP transport, no mcpo)
./start.sh --standalone pentest

# List YAML profiles
./start.sh --list
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Address already in use" | `kill $(lsof -t -i:7734)` then relaunch |
| "No module named 'fastmcp'" | `rm -rf venv` then relaunch (auto-recreates) |
| Tools not in OpenWebUI | Verify bridge running: `curl http://localhost:7734/docs` |
| Docker servers not connecting | Verify images exist: `docker images \| grep mcp` |

---

## How It Works Under the Hood

**FastMCP 2.x `as_proxy()`** natively understands the `mcpServers` JSON format from Claude Desktop. Pass it a dictionary with multiple servers and it auto-creates proxy connections with prefixed tool names.

**mcpo** wraps any MCP server in an HTTP server exposing tools as OpenAPI endpoints. OpenWebUI speaks OpenAPI, mcpo speaks MCP — perfect translator.

The combination: **existing MCP servers → FastMCP proxy → mcpo HTTP wrapper → OpenWebUI**. No code changes to any MCP server.

---

## Acknowledgments

- **[FastMCP](https://github.com/jlowin/fastmcp)** by Jared Lowin — the proxy and composition engine that makes this possible
- **[mcpo](https://github.com/open-webui/mcpo)** by the OpenWebUI team — MCP-to-OpenAPI translation
- **[OpenWebUI](https://github.com/open-webui/open-webui)** — the self-hosted AI interface
- **Anthropic** for Claude and the Model Context Protocol
- The **cybersecurity community** for always sharing knowledge

---

*This is Project #9 in the HackerObi AI Projects series. Check out the other integrations in the [AI Projects folder](../).*

*Happy hacking, stay curious, and never stop learning!* 🛡️

**— Hackerobi**