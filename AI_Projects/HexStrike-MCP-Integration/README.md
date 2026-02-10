# Integrating HexStrike AI with Claude Desktop: A Complete Guide

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Intermediate  
**Time Required:** 30-45 minutes

---

## Introduction

Imagine telling your AI assistant: *"Run a full subdomain enumeration on example.com, then scan discovered hosts for vulnerabilities"* — and watching it autonomously chain together subfinder, httpx, nuclei, and nmap through a single conversation. No terminal hopping, no manual tool orchestration. This guide will show you how to connect **HexStrike AI v6.0** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude access to 150+ offensive security tools through a Docker-based two-container architecture.

By the end of this guide, you'll have:
- A persistent, Dockerized HexStrike deployment with isolated networking
- 150+ professional security tools accessible through Claude Desktop
- AI-powered reconnaissance, vulnerability scanning, and exploitation workflows
- 12+ autonomous AI agents for bug bounty, CTF, and red team operations
- Natural language security testing — describe what you want and Claude executes it
- Multi-tool chaining across your entire MCP ecosystem

### What is HexStrike AI?

[HexStrike AI](https://github.com/0x4m4/hexstrike-ai) is an advanced MCP-compatible cybersecurity automation platform created by [m0x4m4](https://www.0x4m4.com). It provides a Flask-based API server that wraps 150+ security tools across six major categories — network reconnaissance, web application testing, authentication attacks, binary analysis, cloud security, and OSINT — and exposes them through the Model Context Protocol for AI agent integration.

What sets HexStrike apart is its **multi-agent architecture**: 12+ specialized AI agents handle intelligent tool selection, parameter optimization, attack chain discovery, and graceful error recovery. It's not just a command relay — it actively assists in building effective security testing workflows.

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter — in this case, it lets Claude orchestrate professional penetration testing tools through natural conversation.

### What You'll Need

- **Linux workstation** (this guide uses Pop!_OS, but Ubuntu/Debian/Kali will work)
- **Docker Engine** (Docker CE) with networking support
- **Claude Desktop** application
- **Python 3.8+** and pip
- **Security tools** installed on the HexStrike server (nmap, nuclei, subfinder, etc.)
- Basic familiarity with command line and Docker

---

## Architecture Overview

HexStrike uses a **two-container architecture** connected over a dedicated Docker network:

```
┌─────────────────┐    stdio      ┌────────────────────────────────┐  HTTP/API   ┌──────────────────────────┐
│  Claude Desktop │◄─────────────►│  HexStrike MCP Client          │◄───────────►│  HexStrike AI Server     │
│                 │   JSON-RPC    │  (hexstrike-bb:local)           │  :8888      │  (hexstrike-server)      │
└─────────────────┘               │                                │             │                          │
                                  │  Container 1 (ephemeral)       │             │  Container 2 (persistent)│
                                  │  • Launched per Claude session  │             │  • Always running        │
                                  │  • Translates MCP ↔ HTTP       │             │  • Hosts all tools       │
                                  │  • Runs on mcpnet network       │             │  • Flask API on :8888    │
                                  │  • Security hardened:           │             │  • Smart caching engine  │
                                  │    - no-new-privileges          │             │  • Process management    │
                                  │    - CAP_DROP=ALL               │             │  • 12+ AI agents         │
                                  └────────────────────────────────┘             │                          │
                                                                                │  ┌────────────────────┐  │
                                         Docker Network: mcpnet                 │  │ Tool Categories    │  │
                                  ┌──────────────────────────────┐              │  │ • Network (25+)    │  │
                                  │  Isolated bridge network      │              │  │ • Web App (40+)    │  │
                                  │  hexstrike-server:8888        │              │  │ • Auth/Pass (12+)  │  │
                                  │  (container DNS resolution)   │              │  │ • Binary (25+)     │  │
                                  └──────────────────────────────┘              │  │ • Cloud (20+)      │  │
                                                                                │  │ • OSINT (20+)      │  │
                                                                                │  └────────────────────┘  │
                                                                                └──────────────────────────┘
```

**How it works:**

1. **HexStrike AI Server** (`hexstrike-server`) runs persistently as a Docker container on port 8888, hosting the Flask API and all security tools
2. **HexStrike MCP Client** (`hexstrike-bb:local`) is an ephemeral container launched by Claude Desktop for each session — it translates MCP protocol calls into HTTP requests to the server
3. Both containers communicate over the `mcpnet` Docker bridge network using container DNS resolution (`hexstrike-server:8888`)
4. The MCP client is security-hardened with `--no-new-privileges` and `--cap-drop=ALL` to minimize container escape risk
5. You ask Claude to perform security testing in natural language, Claude calls HexStrike tools, and results flow back through the MCP pipeline

**Key Design Decision — Dedicated Docker Network:** The `mcpnet` bridge network provides isolation from your host networking while allowing the two HexStrike containers to communicate via Docker's internal DNS. This means the HexStrike API server doesn't need to be exposed to `0.0.0.0` — only containers on `mcpnet` can reach it.

---

## Part 1: Setting Up the Docker Network

The dedicated network ensures container-to-container communication without exposing internal services to your host.

### Create the mcpnet Bridge Network

```bash
docker network create mcpnet
```

Verify it exists:

```bash
docker network ls | grep mcpnet
# Expected: mcpnet    bridge    local
```

---

## Part 2: Deploying the HexStrike AI Server

### Step 1: Clone the Repository

```bash
mkdir -p ~/Documents/Docker_Projects/HexStrike
cd ~/Documents/Docker_Projects/HexStrike
git clone https://github.com/0x4m4/hexstrike-ai.git
cd hexstrike-ai
```

### Step 2: Build the Docker Image

If the project provides a Dockerfile, build it directly. Otherwise, you can create a container from the Python setup:

```bash
# Option A: If Dockerfile is provided
docker build -t hexstrike-bb:local .

# Option B: Manual container setup
# (See the project's installation docs for specific instructions)
```

### Step 3: Start the HexStrike Server Container

```bash
docker run -d \
  --name hexstrike-server \
  --network mcpnet \
  --restart unless-stopped \
  -p 127.0.0.1:8888:8888 \
  hexstrike-bb:local \
  python3 hexstrike_server.py --port 8888
```

**Important flags:**
- `--network mcpnet` — Attaches to the isolated bridge network
- `--restart unless-stopped` — Persists across reboots
- `-p 127.0.0.1:8888:8888` — Binds to localhost only (not exposed to LAN)
- The server starts the Flask API on port 8888

### Step 4: Verify the Server is Running

```bash
# Check container status
docker ps --filter name=hexstrike-server

# Check health endpoint
curl http://localhost:8888/health
```

Expected health response:
```json
{
  "status": "healthy",
  "version": "6.0.0",
  "tools_available": 14,
  "tools_total": 127,
  "cache_hit_rate": "0.0%",
  "system": {
    "cpu_percent": 0.1,
    "memory_percent": 14.6,
    "disk_percent": 7.9
  }
}
```

> 📝 **Note:** The `tools_available` count (14 in this example) depends on which security tools are actually installed inside the container. The server can *wrap* 127+ tools, but only reports the ones it finds at startup. Tools like nmap, nuclei, subfinder, sqlmap, ffuf, httpx, katana, and curl are typically included in the base image.

### Step 5: Run a Capability Check

Verify which tools are operational:

```bash
# Test individual tools through the API
curl -X POST http://localhost:8888/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "nuclei -version"}'

curl -X POST http://localhost:8888/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "nmap --version | head -n 1"}'
```

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

### Add the HexStrike MCP Server

Edit your config to add the `hexstrike` entry:

```json
{
  "mcpServers": {
    "hexstrike": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--network", "mcpnet",
        "--security-opt", "no-new-privileges",
        "--cap-drop=ALL",
        "hexstrike-bb:local", "python3", "hexstrike_mcp.py",
        "--server", "http://hexstrike-server:8888"
      ]
    }
  }
}
```

**Understanding each argument:**
- `run -i --rm` — Interactive mode, remove container on exit (ephemeral MCP client)
- `--network mcpnet` — Connect to the same network as the server
- `--security-opt no-new-privileges` — Prevent privilege escalation inside the container
- `--cap-drop=ALL` — Drop all Linux capabilities for security hardening
- `hexstrike-bb:local` — The locally built Docker image
- `python3 hexstrike_mcp.py` — The MCP client script
- `--server http://hexstrike-server:8888` — Points to the persistent server via Docker DNS

> 📝 **Note:** If you already have other MCP servers configured (like BloodHound, Wazuh, Burp Suite, etc.), just add the `hexstrike` entry alongside them inside the existing `mcpServers` object.

### Restart Claude Desktop

Close and reopen Claude Desktop. The HexStrike tools should now appear in the tools list.

### Verify the Connection

In Claude Desktop, ask:

> "Check the HexStrike server health"

Claude will call the `server_health` tool and return the server status, version, uptime, available tools count, and system resource usage. If you get a response back, you're connected!

---

## Part 4: Available Tools (150+ Security Arsenal)

Once connected, you have access to an extensive toolkit organized into major categories. The number of tools actually available depends on what's installed in your HexStrike container.

### Core MCP Tools

| Tool | Description |
|------|-------------|
| `execute_command` | Execute any arbitrary command on the HexStrike server |
| `server_health` | Check server status, uptime, tool availability, and system resources |

### Network Reconnaissance (25+)

| Tool | Description |
|------|-------------|
| `nmap_scan` | Advanced port scanning with NSE scripts and service detection |
| `rustscan_scan` | Ultra-fast port scanner with intelligent rate limiting |
| `masscan_scan` | High-speed Internet-scale port scanning |
| `autorecon_scan` | Comprehensive automated reconnaissance |
| `amass_enum` | Advanced subdomain enumeration and OSINT |
| `subfinder_scan` | Fast passive subdomain discovery from multiple sources |
| `fierce_scan` | DNS reconnaissance and zone transfer testing |
| `theharvester_scan` | Email and subdomain harvesting |

### Web Application Security (40+)

| Tool | Description |
|------|-------------|
| `gobuster_scan` | Directory, file, and DNS enumeration |
| `ffuf_scan` | Fast web fuzzing with advanced filtering |
| `nuclei_scan` | Vulnerability scanning with 4,000+ templates |
| `nikto_scan` | Web server vulnerability scanner |
| `sqlmap_scan` | Automated SQL injection testing |
| `wpscan_scan` | WordPress security assessment |
| `httpx_scan` | HTTP probing and technology detection |
| `katana_scan` | Next-gen crawling with JavaScript support |
| `dalfox_scan` | Advanced XSS vulnerability scanning |

### Authentication & Password (12+)

| Tool | Description |
|------|-------------|
| `hydra_attack` | Network login cracker (50+ protocols) |
| `john_crack` | Password hash cracking with custom rules |
| `hashcat_crack` | GPU-accelerated password recovery |

### Binary Analysis & Reverse Engineering (25+)

| Tool | Description |
|------|-------------|
| `ghidra_analyze` | NSA's reverse engineering suite (headless) |
| `radare2_analyze` | Advanced reverse engineering framework |
| `gdb_debug` | GNU Debugger with exploit development |
| `checksec_check` | Binary security property analysis |
| `strings_extract` | Extract printable strings from binaries |
| `angr_analyze` | Binary analysis with symbolic execution |

### Cloud & Container Security (20+)

| Tool | Description |
|------|-------------|
| `prowler_assess` | AWS/Azure/GCP security assessment |
| `trivy_scan` | Container vulnerability scanning |
| `kube_hunter_scan` | Kubernetes penetration testing |

### OSINT & Bug Bounty (20+)

| Tool | Description |
|------|-------------|
| `sherlock_search` | Username investigation across 400+ platforms |
| `recon_ng_scan` | Web reconnaissance framework |
| `bugbounty_reconnaissance` | Automated bug bounty hunting workflows |
| `ctf_solve_challenge` | AI-assisted CTF challenge solving |

### AI Agents

| Agent | Description |
|-------|-------------|
| `IntelligentDecisionEngine` | Tool selection and parameter optimization |
| `BugBountyWorkflowManager` | End-to-end bug bounty workflows |
| `CTFWorkflowManager` | Automated CTF challenge solving |
| `CVEIntelligenceManager` | Real-time vulnerability intelligence |
| `AIExploitGenerator` | Automated exploit development |
| `VulnerabilityCorrelator` | Attack chain discovery |
| `TechnologyDetector` | Technology stack fingerprinting |

> 📝 This is not an exhaustive list — HexStrike AI provides **150+** tools. The `execute_command` tool also lets you run **any command** available in the container, giving you unlimited flexibility.

---

## Part 5: Example Conversations

Here's what it actually looks like to use HexStrike through Claude. All examples are against **authorized targets only** (owned systems, lab environments, or bug bounty programs in scope).

### Health Check and Capability Discovery
> **You:** Check if HexStrike is running and show me what tools are available.
>
> **Claude:** *[Calls server_health]* HexStrike AI v6.0 is healthy and operational. Uptime: 4.5 hours. 14 out of 127 tools are available:
> nmap, nuclei, ffuf, sqlmap, subfinder, httpx, katana, strings, objdump, checksec, tcpdump, tshark, curl, angr
>
> System resources look good — CPU at 0.1%, memory at 14.6%.

### Version Verification
> **You:** Run a quick capability check on nuclei, subfinder, and ffuf.
>
> **Claude:** *[Calls execute_command for each]*
> - ✅ **nuclei** — v3.3.5 (operational)
> - ✅ **subfinder** — v2.6.6 (operational)
> - ✅ **ffuf** — v2.1.0-dev (operational)
>
> All three ProjectDiscovery tools are fully functional and ready to go.

### Subdomain Enumeration
> **You:** I own example.com and I'd like to enumerate all subdomains using hexstrike.
>
> **Claude:** *[Calls subfinder with example.com target]*
> Subfinder discovered 47 subdomains for example.com. Let me probe which ones are live:
> *[Calls httpx to validate]*
> 31 of 47 subdomains are responding — 28 returning HTTP 200, 2 returning 301 redirects, and 1 returning 403. Want me to run nuclei against the live hosts?

### Chained Vulnerability Assessment
> **You:** Yes, scan all live hosts with nuclei for critical and high severity findings.
>
> **Claude:** *[Calls nuclei_scan with severity filters]*
> Nuclei completed scanning 31 hosts with 4,000+ templates. Results:
> - 🔴 **Critical:** 2 findings (CVE-2024-XXXX on api.example.com, exposed .env on staging.example.com)
> - 🟠 **High:** 5 findings (outdated Apache on 3 hosts, missing security headers on 2)
>
> The exposed .env file on staging is the most urgent — it could contain database credentials or API keys. Want me to investigate further with curl?

### SQL Injection Testing
> **You:** Test the login form at https://testsite.example.com/login for SQL injection.
>
> **Claude:** *[Calls sqlmap_scan with the target URL]*
> SQLMap completed its assessment. The `username` parameter is **injectable** via boolean-based blind injection. The backend appears to be MySQL 8.0.
>
> ⚠️ This is a confirmed vulnerability. I'd recommend documenting this finding and reporting it through the appropriate channel.

### CTF Challenge Assistance
> **You:** I'm working on a binary exploitation CTF challenge. The binary is at /tmp/challenge. Can you analyze it?
>
> **Claude:** *[Calls checksec_check on the binary]*
> Binary security properties:
> - NX: **Enabled** (no execute on stack)
> - PIE: **Disabled** (fixed addresses)
> - Stack Canary: **Disabled** (buffer overflow viable)
> - RELRO: **Partial**
>
> *[Calls strings_extract]* Found interesting strings including "admin_password", a format string "%s", and what appears to be a flag format "FLAG{...}".
>
> With no canary and no PIE, this looks like a classic buffer overflow challenge. Want me to use angr for symbolic execution to find the input that reaches the flag?

---

## Part 6: Multi-Tool Pipeline Workflows

The real power emerges when you combine HexStrike with your other MCP integrations:

### HexStrike → BloodHound Pipeline
```
You: Use nmap to scan the 10.10.14.0/24 network through HexStrike,
     then check BloodHound for any discovered hosts.
Claude: [Runs nmap via HexStrike — discovers 12 hosts]
        [Queries BloodHound for matching computer objects]
        Found 8 of 12 hosts in the BloodHound graph. 3 have paths
        to Domain Admin. WEBSRV01 has the shortest path at 4 hops.
```

### HexStrike → Wazuh Correlation
```
You: Run a nuclei scan against our web servers, then check Wazuh
     to see if the scan triggered any alerts.
Claude: [Runs nuclei via HexStrike against target list]
        [Queries Wazuh for alerts from the scan timeframe]
        The scan generated 23 IDS alerts in Wazuh. 19 were correctly
        classified as vulnerability scanning. 4 were missed — those
        represent detection gaps we should address.
```

### HexStrike → SysReptor Reporting
```
You: Take all critical and high findings from the nuclei scan and
     create findings in my SysReptor pentest report.
Claude: [Retrieves nuclei results from HexStrike]
        [Creates findings in SysReptor for each vulnerability]
        Created 7 findings in your report with severity ratings,
        affected hosts, and remediation recommendations.
```

### HexStrike → Burp Suite Handoff
```
You: HexStrike found a potential SQLi on the login page. Can you
     send a test request through Burp Suite for manual verification?
Claude: [Forwards the request through Burp Suite proxy]
        [Checks Burp proxy history for the response]
        Request captured in Burp Suite Repeater. The response confirms
        a 500 error with a SQL syntax error in the body — SQLi confirmed.
```

This is the vision — **AI as the connective tissue between your offensive security tools**, orchestrating complex workflows that would take hours to execute manually.

---

## Troubleshooting

### Claude Desktop Shows No HexStrike Tools

**Problem:** After adding the config, HexStrike tools don't appear in Claude Desktop.

**Solution:** Verify the Docker image exists and the network is correct:

```bash
# Check the image exists
docker images | grep hexstrike-bb

# Check the mcpnet network exists
docker network ls | grep mcpnet

# Test the MCP client manually
docker run -i --rm \
  --network mcpnet \
  hexstrike-bb:local python3 hexstrike_mcp.py \
  --server http://hexstrike-server:8888
```

Common issues:
- Docker image name mismatch (must be `hexstrike-bb:local`)
- `mcpnet` network doesn't exist (run `docker network create mcpnet`)
- HexStrike server container not running (check `docker ps`)

### "Connection Refused" to HexStrike Server

**Problem:** MCP client can't reach the HexStrike server on port 8888.

**Solution:** Verify the server container is running and on the correct network:

```bash
# Check if the server is running
docker ps --filter name=hexstrike-server

# Check the server is on mcpnet
docker network inspect mcpnet --format '{{range .Containers}}{{.Name}}: {{.IPv4Address}}{{"\n"}}{{end}}'

# Test the health endpoint directly
curl http://localhost:8888/health

# Check server logs
docker logs hexstrike-server --tail 50
```

If the server isn't on `mcpnet`, reconnect it:

```bash
docker network connect mcpnet hexstrike-server
```

### Low Tool Availability (e.g., 14/127)

**Problem:** Health check shows only 14 out of 127 tools available.

**Solution:** This is normal — the count reflects tools actually installed in the container. To add more tools:

```bash
# Enter the running container
docker exec -it hexstrike-server bash

# Install additional tools
apt update && apt install -y gobuster dirb nikto hydra john
# Or install Go-based tools
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
```

For a persistent solution, create a custom Dockerfile that pre-installs all desired tools, rebuild the image, and redeploy.

### Nmap Permission Denied

**Problem:** Nmap commands fail with permission errors inside the container.

**Solution:** Some nmap scan types require raw socket access. You may need to add network capabilities:

```bash
# Restart the server with NET_RAW capability
docker stop hexstrike-server
docker rm hexstrike-server
docker run -d \
  --name hexstrike-server \
  --network mcpnet \
  --restart unless-stopped \
  --cap-add=NET_RAW \
  -p 127.0.0.1:8888:8888 \
  hexstrike-bb:local \
  python3 hexstrike_server.py --port 8888
```

> ⚠️ Only add capabilities when necessary — the principle of least privilege still applies.

### Container Doesn't Survive Reboot

**Problem:** HexStrike server container isn't running after a reboot.

**Solution:** Verify the restart policy and Docker service:

```bash
# Check container restart policy
docker inspect hexstrike-server --format '{{.HostConfig.RestartPolicy.Name}}'
# Should return: unless-stopped

# Ensure Docker starts on boot
sudo systemctl is-enabled docker
# If not: sudo systemctl enable docker
```

---

## Quick Reference

### Start HexStrike Server
```bash
docker start hexstrike-server
```

### Stop HexStrike Server
```bash
docker stop hexstrike-server
```

### Check Status
```bash
docker ps --filter name=hexstrike
curl http://localhost:8888/health
```

### View Logs
```bash
docker logs hexstrike-server --tail 100
docker logs hexstrike-server -f  # Follow live
```

### Access Points
| Service | URL |
|---------|-----|
| HexStrike API | http://localhost:8888 |
| Health Check | http://localhost:8888/health |
| Telemetry | http://localhost:8888/api/telemetry |
| Cache Stats | http://localhost:8888/api/cache/stats |

### Test MCP Connection
Ask Claude: *"Check the HexStrike server health"*

---

## Security Considerations

- **Isolated Networking:** The `mcpnet` Docker bridge isolates HexStrike from your host network. Only containers on this network can communicate with the server API.
- **Security Hardening:** The MCP client container runs with `--no-new-privileges` and `--cap-drop=ALL`, preventing privilege escalation and capability abuse.
- **Localhost Binding:** The server port is bound to `127.0.0.1:8888`, not `0.0.0.0`, preventing LAN exposure.
- **Tool Access:** HexStrike provides access to powerful offensive security tools. Run it in isolated lab environments and never test systems without explicit written authorization.
- **Command Execution:** The `execute_command` tool can run arbitrary commands inside the container. Ensure the container has minimal access to sensitive host resources.
- **Authorization:** Always operate within the scope of authorized penetration testing engagements, bug bounty programs, or your own lab environments. HexStrike is designed for legitimate security testing only.
- **Container Updates:** Regularly update the HexStrike image and installed tools to patch known vulnerabilities in the testing tools themselves.

---

## Conclusion

You now have an AI-powered offensive security platform integrated directly into your Claude Desktop workflow. This setup lets you:

- Run 150+ professional security tools through natural conversation
- Chain reconnaissance, scanning, and exploitation into automated pipelines
- Leverage 12+ AI agents for intelligent tool selection and attack chain discovery
- Combine HexStrike with BloodHound, Wazuh, Burp Suite, and SysReptor for full-stack security assessments
- Execute bug bounty workflows and CTF challenges with AI assistance
- Maintain security isolation through Docker networking and capability controls

The days of context-switching between fifteen terminal tabs and manually piping output between tools are over. Describe your security testing objective to Claude, and HexStrike executes it.

### What's Next?

- Install additional tools inside the HexStrike container for broader coverage
- Combine HexStrike reconnaissance with BloodHound for internal network pivoting
- Feed HexStrike findings directly into SysReptor for automated report generation
- Use HexStrike + Wazuh to identify detection gaps in your monitoring
- Explore the AI agents for automated bug bounty and CTF workflows
- Keep an eye out for HexStrike v7.0 with 250+ tools and a native desktop client

---

## Resources

- [HexStrike AI v6.0](https://github.com/0x4m4/hexstrike-ai) — Advanced AI-powered penetration testing framework (150+ tools)
- [HexStrike Website](https://www.hexstrike.com/) — Official HexStrike platform
- [HexStrike Discord](https://discord.gg/BWnmrrSHbA) — Community support
- [MCP Protocol Specification](https://modelcontextprotocol.io/) — Learn about MCP
- [Claude Desktop](https://claude.ai/download) — Download Claude Desktop
- [Docker Documentation](https://docs.docker.com/) — Docker networking and container management
- [ProjectDiscovery Tools](https://github.com/projectdiscovery) — nuclei, subfinder, httpx, katana

---

## Acknowledgments

Special thanks to:
- **m0x4m4** for creating [HexStrike AI](https://github.com/0x4m4/hexstrike-ai) — an incredible offensive security automation platform
- **ProjectDiscovery** for nuclei, subfinder, httpx, katana, and the broader open-source security toolkit
- **Anthropic** for Claude and the Model Context Protocol
- The **bug bounty community** for pushing the boundaries of automated security testing
- The **open-source security community** for the tools that make platforms like HexStrike possible
- **You** for taking the time to check out this project

---

*Happy hacking, stay ethical, and may your recon always find what the scanners miss!* 🎯

**— Hackerobi**