# Integrating SysReptor Pentest Reporting with Claude AI: A Complete Guide

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Intermediate  
**Time Required:** 45-60 minutes

---

## Introduction

Imagine finishing a penetration test and telling your AI assistant: *"Create a finding for the Kerberoasting vulnerability we discovered, include the affected SPNs, and push it to the report"* — and watching the finding appear in your professional pentest report instantly. This guide will show you how to connect **SysReptor** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude direct control over your pentest reporting workflow.

By the end of this guide, you'll have:
- 27 pentest reporting tools available in Claude Desktop
- AI-powered finding creation and management
- Direct integration with vulnerability scanners (Nessus, Burp, OpenVAS, Qualys, ZAP)
- Automated report generation and template management
- The ability to manage your entire pentest reporting pipeline through natural conversation

### What is SysReptor?

[SysReptor](https://github.com/Syslifters/sysreptor) is a professional, open-source penetration testing reporting platform. It provides:

- Professional report templates with customizable designs
- Finding management with CVSS scoring
- Multi-language support and translation
- PDF report rendering
- Team collaboration features
- Finding template libraries for common vulnerabilities

Think of it as the last mile of your pentest — where raw findings become polished, client-ready deliverables.

### What is reptor-mcp?

[reptor-mcp](https://github.com/slvnlrt/reptor-mcp) is an MCP server built on top of [reptor](https://github.com/Syslifters/reptor) (SysReptor's CLI tool) by [slvnlrt](https://github.com/slvnlrt). It exposes SysReptor's full functionality as MCP tools, letting Claude interact with your reporting platform directly.

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude talk to your favorite platforms — in this case, your pentest reporting system.

### What You'll Need

- **Linux workstation** (this guide uses Pop!_OS, but Ubuntu/Debian will work)
- **Docker Engine** (Docker CE) with Compose plugin
- **SysReptor** running locally (self-hosted)
- **Claude Desktop** application
- **A SysReptor API token** (generated from the web portal)
- Basic familiarity with command line and Docker

---

## Architecture Overview

```
┌─────────────────┐  docker exec   ┌───────────────────────────────┐    HTTP     ┌──────────────────────┐
│  Claude Desktop │◄──────────────►│  reptor-mcp Container         │◄───────────►│  SysReptor Server    │
│                 │    stdio       │  (FastMCP + reptor CLI)        │  REST API   │  (Docker Compose)    │
└─────────────────┘                │                               │             │                      │
                                   │  ┌─────────────────────────┐  │             │  ┌────────────────┐  │
                                   │  │ Scanner Importers        │  │             │  │ Report Engine   │  │
                                   │  │ • Nessus                 │  │             │  │ • PDF Render    │  │
                                   │  │ • Burp Suite             │  │             │  │ • Templates     │  │
                                   │  │ • OpenVAS                │  │             │  │ • Designs       │  │
                                   │  │ • Qualys                 │  │             │  └────────────────┘  │
                                   │  │ • ZAP                    │  │             │  ┌────────────────┐  │
                                   │  │ • SSLyze                 │  │             │  │ Finding Store   │  │
                                   │  └─────────────────────────┘  │             │  │ • CVSS Scoring  │  │
                                   │  ┌─────────────────────────┐  │             │  │ • Templates     │  │
                                   │  │ Reporting Tools          │  │             │  │ • Projects      │  │
                                   │  │ • Notes                  │  │             │  └────────────────┘  │
                                   │  │ • Findings               │  │             │  ┌────────────────┐  │
                                   │  │ • Templates              │  │             │  │ Collaboration   │  │
                                   │  │ • Export/Import          │  │             │  │ • Multi-user    │  │
                                   │  │ • Translation            │  │             │  │ • Comments      │  │
                                   │  └─────────────────────────┘  │             │  └────────────────┘  │
                                   └───────────────────────────────┘             └──────────────────────┘
```

**How it works:**

1. SysReptor runs as a Docker Compose stack on your host (port 8000)
2. The reptor-mcp container runs reptor CLI + FastMCP server
3. Claude Desktop communicates with reptor-mcp via `docker exec` using stdio transport
4. reptor-mcp translates Claude's requests into SysReptor API calls
5. You talk to Claude, Claude manages your pentest reports

**Key Insight — Transport Protocol:** Claude Desktop on Linux works best with **stdio** transport via `docker exec`. We tried streamable-http and SSE transports first, but stdio proved to be the most reliable approach. This is a pattern we've used successfully across multiple MCP integrations.

---

## Part 1: Prerequisites

### Step 1: Verify Docker is Running

```bash
docker --version
# Docker version 29.x.x or higher

docker compose version
# Docker Compose version v2.x.x
```

### Step 2: Verify SysReptor is Running

If you already have SysReptor installed and running, verify it:

```bash
# Check if SysReptor is responding
curl -s http://127.0.0.1:8000/api/ | head -20

# Or check Docker processes
sudo ss -tlnp | grep 8000
```

If SysReptor isn't installed yet, follow the [official SysReptor installation guide](https://docs.sysreptor.com/setup/installation/). The quick version:

```bash
# Create a directory for SysReptor
mkdir -p ~/Documents/Notes/SysReptor
cd ~/Documents/Notes/SysReptor

# Clone SysReptor
git clone https://github.com/Syslifters/sysreptor.git
cd sysreptor/deploy/sysreptor

# Start SysReptor
docker compose up -d
```

SysReptor should now be accessible at **http://127.0.0.1:8000**.

### Step 3: Get Your API Token

1. Open **http://127.0.0.1:8000** in your browser
2. Log in with your admin credentials
3. Navigate to your **User Profile** (click your username → Profile)
4. Under **API Tokens**, click **Create Token**
5. Give it a name like `reptor-mcp`
6. **Copy the token** — you'll need it for the Docker configuration

> ⚠️ **Save your token securely!** It won't be shown again after creation.

---

## Part 2: Building the reptor-mcp Docker Container

### Step 1: Create the Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/SYS_Rep_Reporting_MCP
cd ~/Documents/Docker_Projects/SYS_Rep_Reporting_MCP
```

### Step 2: Create the Dockerfile

```bash
cat > Dockerfile << 'DOCKERFILE'
FROM python:3.11-slim

WORKDIR /app

# Install git for cloning repos
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone both repos as siblings (reptor-mcp expects this layout)
RUN git clone https://github.com/Syslifters/reptor.git /app/reptor
RUN git clone https://github.com/slvnlrt/reptor-mcp.git /app/reptor-mcp

# Install reptor (the CLI tool) in editable mode
RUN pip install --no-cache-dir -e /app/reptor

# Install reptor-mcp dependencies
RUN pip install --no-cache-dir fastmcp

# Install reptor-mcp in editable mode
RUN pip install --no-cache-dir -e /app/reptor-mcp

# Set working directory to the MCP server
WORKDIR /app/reptor-mcp/src/reptor_mcp

# Keep the container running (for docker exec access)
CMD ["tail", "-f", "/dev/null"]
DOCKERFILE
```

**Why this layout?** The reptor-mcp package imports from the reptor CLI library. Cloning both as siblings under `/app/` and installing them in editable mode ensures the import paths work correctly.

### Step 3: Create the Build and Run Script

```bash
cat > build_and_run.sh << 'SCRIPT'
#!/bin/bash
# Build and run reptor-mcp container

IMAGE_NAME="reptor-mcp:local"
CONTAINER_NAME="reptor-mcp-server"

# Your SysReptor details
SYSREPTOR_SERVER="http://host.docker.internal:8000"
SYSREPTOR_TOKEN="YOUR_API_TOKEN_HERE"

echo "[*] Building reptor-mcp Docker image..."
docker build -t "$IMAGE_NAME" .

echo "[*] Stopping any existing container..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null

echo "[*] Starting reptor-mcp container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --add-host=host.docker.internal:host-gateway \
    -e REPTOR_SERVER="$SYSREPTOR_SERVER" \
    -e REPTOR_TOKEN="$SYSREPTOR_TOKEN" \
    -e REPTOR_MCP_INSECURE=true \
    -e REPTOR_MCP_DEBUG=true \
    -p 8008:8008 \
    "$IMAGE_NAME"

echo "[*] Waiting for container to start..."
sleep 3

echo "[*] Container status:"
docker ps --filter name="$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "[*] Testing MCP server..."
docker exec "$CONTAINER_NAME" fastmcp run mcp_server.py:mcp --transport stdio <<< '{"jsonrpc":"2.0","method":"tools/list","id":1}' 2>/dev/null | head -5

echo ""
echo "[+] Done! Container '$CONTAINER_NAME' is running."
echo "[+] Configure Claude Desktop to use: docker exec -i $CONTAINER_NAME fastmcp run mcp_server.py:mcp --transport stdio"
SCRIPT

chmod +x build_and_run.sh
```

### Step 4: Edit the Script with Your Token

```bash
# Replace YOUR_API_TOKEN_HERE with your actual SysReptor API token
nano build_and_run.sh
```

### Step 5: Build and Run

```bash
./build_and_run.sh
```

Expected output:
```
[*] Building reptor-mcp Docker image...
...
[*] Starting reptor-mcp container...
[*] Container status:
NAMES               STATUS          PORTS
reptor-mcp-server   Up 3 seconds    0.0.0.0:8008->8008/tcp
[+] Done! Container 'reptor-mcp-server' is running.
```

### Step 6: Verify the Container

```bash
# Check it's running
docker ps --filter name=reptor-mcp-server

# Test the MCP server responds
docker exec -i reptor-mcp-server fastmcp run mcp_server.py:mcp --transport stdio <<< '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

---

## Part 3: Understanding the Transport Protocol (The Hard Part)

This is where things get interesting — and where we learned some valuable lessons that might save you hours of debugging.

### The Problem

reptor-mcp is built with FastMCP, which supports multiple transport protocols:
- **Streamable HTTP** — FastMCP's default, serves on a port
- **SSE (Server-Sent Events)** — Real-time streaming over HTTP
- **stdio** — Standard input/output, the simplest approach

### What We Tried (and Why It Failed)

**Attempt 1: Streamable HTTP (port 8008)**
We configured Claude Desktop to connect to `http://localhost:8008/mcp/`. The server started fine, responded to `curl` tests, but **Claude Desktop froze on launch**. The `type: "url"` configuration wasn't working reliably.

**Attempt 2: SSE Transport**
We switched to SSE on port 8008 at `/sse`. Same problem — **Claude Desktop froze**. The `type: "sse"` configuration isn't well-supported by Claude Desktop on Linux.

**Attempt 3: stdio via docker exec (Success! ✅)**
The solution that works reliably on Linux is using `docker exec` with stdio transport. This is the same approach we've used successfully for other MCP integrations (Wazuh, Burp Suite, etc.).

### Why stdio Works

Claude Desktop on Linux communicates with MCP servers through stdin/stdout. Using `docker exec -i`, we pipe JSON-RPC messages directly into the container and read responses back — no HTTP servers, no ports, no network complexity. It just works.

> 💡 **Pro Tip for Linux Users:** If you're running Claude Desktop on Linux and an MCP server supports multiple transports, always try stdio first. It's the most reliable option.

---

## Part 4: Configuring Claude Desktop

### Locate Your Config File

```bash
# Linux
~/.config/Claude/claude_desktop_config.json

# macOS
~/Library/Application Support/Claude/claude_desktop_config.json

# Windows
%APPDATA%\Claude\claude_desktop_config.json
```

### Add the reptor-mcp Server

Edit your config to add the `reptor-mcp` entry:

```json
{
  "mcpServers": {
    "reptor-mcp": {
      "command": "docker",
      "args": [
        "exec", "-i", "reptor-mcp-server",
        "fastmcp", "run", "mcp_server.py:mcp", "--transport", "stdio"
      ]
    }
  }
}
```

> 📝 **Note:** If you already have other MCP servers configured (like Wazuh, Burp Suite, LitterBox, etc.), just add the `reptor-mcp` entry alongside them inside the existing `mcpServers` object.

### Restart Claude Desktop

Close and reopen Claude Desktop. The reptor-mcp tools should now appear in the tools list — all 27 of them!

### Verify the Connection

In Claude Desktop, ask:

> "Show me the reptor-mcp configuration"

Claude will call the `conf` tool and you should see:
```
Server:     http://host.docker.internal:8000
Project ID: Writing globally.
```

If you see the server URL, you're connected.

---

## Part 5: Available Tools

Once connected, you'll have access to **27 pentest reporting tools** organized into several categories:

### Scanner Importers
| Tool | Description |
|------|-------------|
| `openvas` | Import findings from OpenVAS vulnerability scans |
| `burp` | Import findings from Burp Suite scans |
| `nessus` | Import findings from Nessus vulnerability scans |
| `zap` | Import findings from OWASP ZAP scans |
| `qualys` | Import findings from Qualys vulnerability scans |
| `sslyze` | Import findings from SSLyze TLS analysis |
| `nmap` | Format and import Nmap scan results |

### Finding Management
| Tool | Description |
|------|-------------|
| `finding` | Create or update findings from JSON/TOML data |
| `list_findings` | List findings with filters (status, severity, title) |
| `get_finding_details` | Retrieve full details of a specific finding |
| `findingfromtemplate` | Create findings from reusable templates |
| `deletefindings` | Delete findings by title (with dry-run safety) |
| `exportfindings` | Export findings as CSV, JSON, TOML, or YAML |

### Template Management
| Tool | Description |
|------|-------------|
| `template` | Search, list, and export finding templates |
| `upload_template` | Upload new finding templates |

### Note & File Management
| Tool | Description |
|------|-------------|
| `note` | Create, upload, and list project notes |
| `file` | Upload files to the project |

### Project Management
| Tool | Description |
|------|-------------|
| `project` | Search, export, render, duplicate, or finish projects |
| `createproject` | Create a new pentest project with a design template |
| `pushproject` | Push project data from JSON or TOML |
| `deleteprojects` | Delete projects by title |

### Import/Export
| Tool | Description |
|------|-------------|
| `ghostwriter` | Import finding templates from GhostWriter |
| `defectdojo` | Import finding templates from DefectDojo |
| `unpackarchive` | Unpack exported .tar.gz archives |
| `packarchive` | Pack directories into .tar.gz archives |

### Utilities
| Tool | Description |
|------|-------------|
| `translate` | Translate projects to other languages via DeepL |
| `conf` | View current connection settings |
| `plugins` | Manage and discover available plugins |
| `importers` | Show available finding template importers |

---

## Part 6: Example Conversations

### Check Connection Status
> **You:** Show me the reptor-mcp configuration.
>
> **Claude:** *[Calls conf]* Connected to SysReptor at http://host.docker.internal:8000. Currently writing globally (no project ID set).

### Browse Finding Templates
> **You:** What finding templates do I have available?
>
> **Claude:** *[Calls template with list=true]* You have 14 finding templates loaded, including Kerberoasting, DCSync Attack, Generic Write, Unconstrained Delegation, NTLM Relay, GPO Abuse, and more. Most are tagged for Active Directory assessments.

### Create a Finding from Template
> **You:** Create a finding for the Kerberoasting vulnerability we found.
>
> **Claude:** *[Calls findingfromtemplate]* Finding created from the "Kerberoastable Accounts" template. You can now update it with the specific SPNs and hashes you discovered.

### Import Scanner Results
> **You:** Import the Nessus scan results from /path/to/scan.nessus, only high and critical findings.
>
> **Claude:** *[Calls nessus with severity_filter="high,critical"]* Imported 23 findings from the Nessus scan — 5 critical and 18 high severity. They've been pushed to your project.

### Create a Custom Finding
> **You:** Create a finding for the insecure file upload we found on the admin portal.
>
> **Claude:** *[Calls finding with structured JSON data]* Finding created with title "Unrestricted File Upload", CVSS 8.8, affected component admin.example.com/upload, and detailed remediation steps.

### Export Findings Summary
> **You:** Export all findings as a CSV for the project tracker.
>
> **Claude:** *[Calls exportfindings with export="csv"]* Here's your findings summary with columns for retest status, title, affected components, and CVSS scores.

### Render the Final Report
> **You:** Render the project as a PDF report.
>
> **Claude:** *[Calls project with render=true]* Report rendered successfully. The PDF has been generated with your project's design template.

---

## Part 7: Workflow — From Scanner to Report

Here's a typical end-to-end pentest reporting workflow using reptor-mcp:

### 1. Create a New Project
```
You: Create a new pentest project called "ACME Corp External Assessment Q1 2026"
Claude: [Calls createproject] Project created with ID abc123...
```

### 2. Import Scanner Findings
```
You: Import the Nessus results from /scans/acme-external.nessus,
     filter for medium severity and above.
Claude: [Calls nessus] Imported 47 findings (5 critical, 12 high, 30 medium).
```

### 3. Add Manual Findings
```
You: Create a critical finding for the SQL injection we found on the
     login page at login.acme.com/auth?username=
Claude: [Calls finding] Finding created with CVSS 9.8, full description,
        proof of concept, and remediation guidance.
```

### 4. Add Findings from Templates
```
You: Add a finding from the Kerberoasting template — we found 3 SPNs
     with weak passwords.
Claude: [Calls findingfromtemplate, then updates the finding]
        Finding created and updated with the specific SPN details.
```

### 5. Upload Supporting Evidence
```
You: Upload the screenshot evidence from /evidence/sqli-proof.png
Claude: [Calls file] Screenshot uploaded to the project.
```

### 6. Add Executive Summary Notes
```
You: Add a note titled "Executive Summary" with the key findings overview.
Claude: [Calls note] Executive summary note added to the project.
```

### 7. Export and Render
```
You: Render the final report and export the findings as a CSV checklist.
Claude: [Calls project with render=true, then exportfindings]
        PDF report rendered. CSV checklist exported with all 52 findings.
```

---

## Part 8: Combining with Other MCP Tools

One of the most powerful aspects of this setup is combining reptor-mcp with your other MCP integrations. If you've followed the previous guides in this series, you now have an end-to-end security workflow:

### BloodHound → SysReptor Pipeline
```
You: Show me all Kerberoastable users from BloodHound, then create
     findings for each one in SysReptor.
Claude: [Queries BloodHound for Kerberoastable users]
        [Creates findings in SysReptor from template for each user]
        Found 5 Kerberoastable accounts. Created findings for each with
        the SPN details and risk assessment.
```

### Wazuh → SysReptor Pipeline
```
You: Pull the critical alerts from Wazuh for the last 24 hours and
     create a security incident report in SysReptor.
Claude: [Queries Wazuh for critical alerts]
        [Creates findings and notes in SysReptor]
        12 critical alerts imported as findings with full alert details.
```

### Burp Suite → SysReptor Pipeline
```
You: Import today's Burp scan results into the project, high and
     critical only.
Claude: [Calls burp importer with severity filter]
        Imported 8 web application findings from Burp Suite.
```

This is the vision — **AI as the glue between your security tools**, automating the tedious reporting work so you can focus on what matters: finding vulnerabilities and helping your clients.

---

## Troubleshooting

### Claude Desktop Freezes on Launch

**Problem:** After adding reptor-mcp to the config, Claude Desktop freezes or hangs.

**Solution:** This usually means the transport protocol is wrong. Make sure you're using the `docker exec` stdio approach, NOT a URL-based configuration:

```json
// ✅ CORRECT — stdio via docker exec
"reptor-mcp": {
    "command": "docker",
    "args": ["exec", "-i", "reptor-mcp-server", "fastmcp", "run", "mcp_server.py:mcp", "--transport", "stdio"]
}

// ❌ WRONG — URL-based (causes freezing on Linux)
"reptor-mcp": {
    "type": "url",
    "url": "http://localhost:8008/mcp/"
}
```

### "No Project ID configured" Error

**Problem:** Tools like `project`, `list_findings`, and `note` return a configuration error about missing project ID.

**Solution:** Some tools require a project context. You can either:
1. Create a new project: Ask Claude to use `createproject`
2. Set an existing project ID by adding `REPTOR_PROJECT_ID` to your container environment:

```bash
docker rm -f reptor-mcp-server
docker run -d \
    --name reptor-mcp-server \
    --add-host=host.docker.internal:host-gateway \
    -e REPTOR_SERVER="http://host.docker.internal:8000" \
    -e REPTOR_TOKEN="your-token-here" \
    -e REPTOR_PROJECT_ID="your-project-uuid" \
    -e REPTOR_MCP_INSECURE=true \
    reptor-mcp:local
```

### Container Can't Reach SysReptor

**Problem:** reptor-mcp can't connect to SysReptor on the host.

**Solution:** The `--add-host=host.docker.internal:host-gateway` flag is critical on Linux. It maps `host.docker.internal` to your host machine's IP. Verify:

```bash
# From inside the container
docker exec reptor-mcp-server curl -s http://host.docker.internal:8000/api/

# If that fails, find the Docker bridge IP
docker exec reptor-mcp-server ip route | grep default
# Then use that IP directly in REPTOR_SERVER
```

### SysReptor Not Visible in `docker ps`

**Problem:** SysReptor containers don't show up in `docker ps` but the web portal works.

**Solution:** SysReptor might be running under a different Docker context or Compose project. Check:

```bash
# Find what's listening on port 8000
sudo ss -tlnp | grep 8000

# Check all Docker networks
docker network ls

# Look for SysReptor on the sysreptor_default network
docker network inspect sysreptor_default
```

### SSL/TLS Certificate Errors

**Problem:** Connection refused or SSL errors when connecting to SysReptor.

**Solution:** Set `REPTOR_MCP_INSECURE=true` in your container environment. This disables SSL verification for local development. Don't use this in production.

### FastMCP Import Errors

**Problem:** The container builds but `fastmcp run` fails with import errors.

**Solution:** Ensure both repos are installed in editable mode:

```bash
docker exec reptor-mcp-server pip list | grep -E "reptor|fastmcp"
# Should show:
# reptor        x.x.x    /app/reptor
# reptor-mcp    x.x.x    /app/reptor-mcp
# fastmcp       x.x.x
```

---

## Quick Reference

### Start reptor-mcp
```bash
# If container exists but is stopped
docker start reptor-mcp-server

# If you need to rebuild
cd ~/Documents/Docker_Projects/SYS_Rep_Reporting_MCP
./build_and_run.sh
```

### Stop reptor-mcp
```bash
docker stop reptor-mcp-server
```

### Check Status
```bash
docker ps --filter name=reptor-mcp-server
```

### View Container Logs
```bash
docker logs reptor-mcp-server
```

### Test MCP Server Manually
```bash
docker exec -i reptor-mcp-server fastmcp run mcp_server.py:mcp --transport stdio <<< '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### Access SysReptor Web Portal
Open **http://127.0.0.1:8000** in your browser.

---

## Security Considerations

- **API Token:** Your SysReptor API token is stored as an environment variable in the Docker container. Don't commit it to version control.
- **Network Access:** The container uses `host.docker.internal` to reach SysReptor. This is a local-only connection.
- **Insecure Mode:** We set `REPTOR_MCP_INSECURE=true` for local development. If running SysReptor with a proper TLS certificate, remove this flag.
- **Project Access:** The API token inherits the permissions of the user who created it. Use a dedicated service account with appropriate access levels for production use.
- **Finding Data:** Pentest findings contain sensitive client data. Ensure your Docker volumes and SysReptor database are properly secured.

---

## Conclusion

You now have AI-powered pentest reporting integrated directly into your workflow. This setup lets you:

- Import vulnerability scanner results through natural conversation
- Create and manage findings without leaving Claude Desktop
- Use pre-built templates for common vulnerabilities (AD attacks, web vulns, infrastructure issues)
- Generate professional PDF reports on demand
- Combine with your other MCP tools (BloodHound, Wazuh, Burp Suite) for end-to-end automation

The days of manually copying and pasting findings between tools are over. Tell Claude what you found, and it handles the reporting. You focus on the hacking.

### What's Next?

- Create custom finding templates for your most common findings
- Build automated reporting workflows that chain multiple MCP tools
- Set up project templates for different engagement types (external, internal, web app, AD)
- Explore the translation feature for multi-language report delivery
- Combine BloodHound AD analysis → reptor-mcp findings for fully automated AD reports

---

## Resources

- [SysReptor](https://github.com/Syslifters/sysreptor) — Professional pentest reporting platform
- [reptor](https://github.com/Syslifters/reptor) — SysReptor CLI tool
- [reptor-mcp](https://github.com/slvnlrt/reptor-mcp) — MCP server for SysReptor
- [SysReptor Documentation](https://docs.sysreptor.com/) — Official documentation
- [MCP Protocol Specification](https://modelcontextprotocol.io/) — Learn about MCP
- [Claude Desktop](https://claude.ai/download) — Download Claude Desktop
- [FastMCP Documentation](https://github.com/jlowin/fastmcp) — MCP Python framework

---

## Acknowledgments

Special thanks to:
- **Syslifters** for building SysReptor — a game-changer for pentest reporting
- **slvnlrt** for creating [reptor-mcp](https://github.com/slvnlrt/reptor-mcp) and bridging SysReptor to the MCP ecosystem
- **Anthropic** for Claude and the Model Context Protocol
- The **penetration testing community** for always pushing to make reporting less painful
- **You** for taking the time to check out this project

---

*Happy hacking, stay curious, and may your reports write themselves!* 📝

**— Hackerobi**
