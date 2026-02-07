# Integrating Burp Suite with Claude AI: A Complete Guide to the Burp Suite MCP Server

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Intermediate  
**Time Required:** 30-45 minutes

---

## Introduction

Imagine conducting a penetration test where you can simply say: *"Test the login form for SQL injection"* and your AI assistant handles the payload generation, request crafting, and finding documentation. This guide will show you how to connect **Burp Suite Community Edition** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude direct control over your web security testing workflow.

By the end of this guide, you'll have:
- 22 security testing tools available in Claude Desktop
- AI-assisted vulnerability testing through Burp's proxy
- Automated finding management and report generation
- Guided penetration testing workflows (OWASP Top 10, API Security, etc.)

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude interact with your security tools.

### What You'll Need

- **Burp Suite Community Edition** (free version works!)
- **Claude Desktop** application
- **Docker** installed on your system
- **Linux workstation** (this guide uses Pop!_OS/Ubuntu)
- Basic familiarity with command line and web security concepts

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Your Linux Workstation                             │
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────────────────────────────┐  │
│  │  Claude Desktop  │         │       Burp Suite Community Edition       │  │
│  │                  │         │         (localhost:8087 proxy)           │  │
│  └────────┬─────────┘         └──────────────────▲───────────────────────┘  │
│           │                                       │                          │
│           │ stdio                                 │ HTTP Proxy               │
│           ▼                                       │                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Docker Container                                   │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │              Burp Suite MCP Server (Python)                    │  │   │
│  │  │                                                                │  │   │
│  │  │  • Target & Scope Management    • Finding Management           │  │   │
│  │  │  • Request Manipulation         • Report Generation            │  │   │
│  │  │  • Vulnerability Testing        • Workflow Automation          │  │   │
│  │  │  • Payload Encoding/Decoding    • Response Analysis            │  │   │
│  │  └────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**How It Works:**

1. You give Claude natural language instructions
2. Claude translates them into MCP tool calls
3. The MCP server sends requests through Burp's proxy
4. Burp captures all traffic in its Proxy History
5. Claude helps you analyze responses, record findings, and generate reports

---

## Part 1: Setting Up the Burp Suite MCP Server

### Step 1: Create Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/Burp_MCP/burpsuite-mcp-server
cd ~/Documents/Docker_Projects/Burp_MCP/burpsuite-mcp-server
```

### Step 2: Create the Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY burpsuite_server.py .

RUN mkdir -p /app/reports /app/findings /app/wordlists

COPY wordlists/ /app/wordlists/

RUN useradd -m -u 1000 mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

CMD ["python", "burpsuite_server.py"]
```

### Step 3: Create requirements.txt

```
mcp[cli]>=1.2.0
httpx>=0.27.0
aiofiles>=23.2.1
jinja2>=3.1.2
python-dateutil>=2.8.2
```

### Step 4: Create Wordlists

```bash
mkdir -p wordlists
```

**wordlists/common.txt:**
```
admin
login
dashboard
api
config
backup
test
dev
staging
.git
.env
robots.txt
sitemap.xml
wp-admin
wp-login
phpmyadmin
administrator
console
panel
portal
```

**wordlists/api-endpoints.txt:**
```
api
v1
v2
graphql
rest
swagger
docs
health
status
users
auth
login
logout
register
token
refresh
me
profile
settings
```

**wordlists/backup-files.txt:**
```
backup.sql
backup.zip
backup.tar.gz
database.sql
dump.sql
db.sql
.bak
.old
.backup
.copy
config.bak
web.config.bak
```

### Step 5: Build the Docker Image

```bash
docker build -t burpsuite-mcp-server .
```

---

## Part 2: Configuring Burp Suite

### Step 1: Configure the Proxy Listener

1. Open **Burp Suite Community Edition**
2. Go to **Proxy → Proxy settings**
3. Under **Proxy Listeners**, click **Add** (or edit the existing one)
4. Configure:
   - **Bind to port:** `8087` (or your preferred port)
   - **Bind to address:** Select **All interfaces**
5. Click **OK**
6. Ensure the listener checkbox is **enabled**

> **Note:** We use port 8087 to avoid conflicts with other services (like BloodHound which uses 8080).

### Step 2: Verify the Listener

```bash
ss -tlnp | grep 8087
```

You should see Burp listening on `0.0.0.0:8087`.

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

### Step 2: Add the Burp Suite MCP Server

Edit your `claude_desktop_config.json` and add the burpsuite entry:

```json
{
  "mcpServers": {
    "burpsuite": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--add-host=host.docker.internal:host-gateway",
        "-e", "BURP_PROXY_HOST=host.docker.internal",
        "-e", "BURP_PROXY_PORT=8087",
        "-v", "/home/YOUR_USERNAME/Documents/Docker_Projects/Burp_MCP/reports:/app/reports",
        "burpsuite-mcp-server"
      ]
    }
  }
}
```

Replace `YOUR_USERNAME` with your actual username.

### Step 3: Restart Claude Desktop

Close and reopen Claude Desktop. The Burp Suite tools should now be available.

---

## Part 4: Available Tools

Once connected, you'll have access to **22 security testing tools**:

### Target & Scope Management
| Tool | Description |
|------|-------------|
| `set_target` | Set the primary target URL for testing |
| `add_to_scope` | Add URL patterns to the testing scope |
| `get_scope` | View current scope configuration |

### Request Manipulation
| Tool | Description |
|------|-------------|
| `send_request` | Send HTTP requests through Burp proxy |

### Reconnaissance & Scanning
| Tool | Description |
|------|-------------|
| `start_reconnaissance` | Begin automated discovery |
| `discover_directories` | Directory/file enumeration setup |
| `scan_vulnerabilities` | Configure vulnerability scans |

### Vulnerability Testing
| Tool | Description |
|------|-------------|
| `test_injection` | SQL/Command/LDAP/XPath/NoSQL injection testing |
| `test_xss` | Cross-site scripting testing (HTML/attribute/JS/URL contexts) |
| `test_authentication` | Authentication mechanism testing |

### Finding Management
| Tool | Description |
|------|-------------|
| `add_finding` | Record a security finding |
| `get_findings` | List all findings with filters |
| `get_finding_details` | View detailed finding information |
| `update_finding` | Update finding status/severity |

### Reporting
| Tool | Description |
|------|-------------|
| `generate_report` | Generate pentest report (Markdown/JSON) |

### Workflows
| Tool | Description |
|------|-------------|
| `run_workflow` | Execute predefined testing workflows |

**Available Workflows:**
- `quick_scan` - Fast security assessment (15-30 min)
- `owasp_top10` - OWASP Top 10 testing (2-4 hours)
- `api_security` - API security assessment (1-2 hours)
- `authentication` - Authentication testing (1-2 hours)

### Utilities
| Tool | Description |
|------|-------------|
| `encode_payload` | Encode payloads (URL, Base64, HTML, Hex) |
| `decode_payload` | Decode encoded payloads |
| `analyze_response` | Analyze HTTP responses for security issues |
| `get_session_status` | View current session statistics |
| `clear_session` | Reset all session data |

---

## Part 5: Example Conversations

### Set Up a Test
> **You:** Set my target to http://testphp.vulnweb.com
> 
> **Claude:** *[Calls set_target]* Target configured successfully! Primary Target: http://testphp.vulnweb.com.

### Send a Request Through Burp
> **You:** Send a GET request to the homepage
> 
> **Claude:** *[Calls send_request]* Request sent through Burp Proxy! Status: 200 OK. Server: nginx/1.19.0, X-Powered-By: PHP/5.6.40...

### Test for Vulnerabilities
> **You:** Test the artist parameter on /artists.php for SQL injection
> 
> **Claude:** *[Calls test_injection]* Here are the SQL injection payloads to test: `' OR '1'='1`, `' OR '1'='1'--`, `1' ORDER BY 1--`...

### Record a Finding
> **You:** Add a high severity finding for the SQL injection we found
> 
> **Claude:** *[Calls add_finding]* Finding recorded! ID: FINDING-20260206-0001, Severity: HIGH

### Generate a Report
> **You:** Generate a penetration test report
> 
> **Claude:** *[Calls generate_report]* Report generated! Format: Markdown, saved to /app/reports/

### Run a Workflow
> **You:** Run the OWASP Top 10 workflow
> 
> **Claude:** *[Calls run_workflow]* Starting OWASP Top 10 Assessment! This will guide you through all 10 categories...

---

## Part 6: Troubleshooting

### "Cannot connect to Burp proxy"

**Cause:** Burp Suite isn't running or the proxy isn't configured correctly.

**Solution:**
1. Ensure Burp Suite is running
2. Verify the proxy listener is on port 8087
3. Make sure "All interfaces" is selected
4. Check: `ss -tlnp | grep 8087`

### Docker Container Can't Reach Host

**Cause:** Docker networking issue on Linux.

**Solution:** The `--add-host=host.docker.internal:host-gateway` flag handles this. If issues persist:

```bash
# Get your host IP
ip addr show docker0 | grep inet
# Use that IP instead of host.docker.internal
```

### Tools Not Appearing in Claude Desktop

**Solution:**
1. Check image exists: `docker images | grep burpsuite`
2. Test container: `docker run --rm -it burpsuite-mcp-server`
3. Verify JSON syntax in config
4. Restart Claude Desktop completely

### Python Encoding Errors

**Solution:** Ensure the server file starts with:
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
```

---

## Part 7: Security Considerations

### Only Test Authorized Targets

This tool is for **authorized security testing only**. Always have:
- Written permission to test
- A defined scope
- Understanding of rules of engagement

### Protect Your Findings

- Keep reports secure
- Don't commit findings to public repos
- Clear sessions after engagements

---

## Quick Reference

### Start Testing
```bash
# 1. Start Burp Suite Community Edition
# 2. Ensure proxy listening on port 8087 (all interfaces)
# 3. Open Claude Desktop
# 4. Ask Claude to set your target
```

### Docker Commands
```bash
docker images | grep burpsuite          # Check image
docker build -t burpsuite-mcp-server .  # Rebuild
docker logs <container_id>              # View logs
```

### Common Claude Commands
```
"Set my target to https://example.com"
"Send a request to /api/users"
"Test the search parameter for XSS"
"Add a finding for the vulnerability"
"Generate a report"
"Run the API security workflow"
```

---

## Resources

- [Burp Suite Documentation](https://portswigger.net/burp/documentation)
- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)

---

*Happy hacking! Always test responsibly and with authorization.* 🔒

**— Hackerobi**
