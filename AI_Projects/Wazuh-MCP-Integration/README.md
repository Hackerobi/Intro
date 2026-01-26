# Integrating Wazuh SIEM with Claude AI: A Complete Guide to the Wazuh MCP Server

**Author:** Hackerobi  
**Date:** January 2026  
**Difficulty:** Intermediate  
**Time Required:** 1-2 hours

---

## Introduction

Imagine asking your AI assistant: *"How many critical CVEs are in my network?"* and getting an instant, accurate answer pulled directly from your SIEM. This guide will show you how to connect **Wazuh SIEM** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude direct access to your security data.

By the end of this guide, you'll have:
- 29 security tools available in Claude Desktop
- Real-time access to alerts, vulnerabilities, and agent data
- The ability to generate security reports through natural conversation

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude talk to your security infrastructure.

### What You'll Need

- **Wazuh SIEM** (v4.8.0+) with Wazuh Indexer
- **Claude Desktop** application
- **Docker** and Docker Compose
- **Linux workstation** (this guide uses Pop!_OS/Ubuntu)
- Basic familiarity with command line

---

## Architecture Overview

```
┌─────────────────┐     stdio      ┌──────────────────┐     HTTP      ┌─────────────────┐
│  Claude Desktop │◄──────────────►│  Stdio Wrapper   │◄─────────────►│  MCP Server     │
│                 │   JSON-RPC     │  (Python)        │   JSON-RPC    │  (Docker)       │
└─────────────────┘                └──────────────────┘               └────────┬────────┘
                                                                               │
                                                            ┌──────────────────┼──────────────────┐
                                                            │                  │                  │
                                                            ▼                  ▼                  ▼
                                                    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                                                    │ Wazuh Manager│  │Wazuh Indexer │  │ Wazuh Agents │
                                                    │  (API:55000) │  │ (API:9200)   │  │              │
                                                    └──────────────┘  └──────────────┘  └──────────────┘
```

**Why a stdio wrapper?**

Claude Desktop communicates with MCP servers via stdio (standard input/output), but the Wazuh MCP Server runs as an HTTP service. The wrapper translates between these protocols.

---

## Part 1: Setting Up the Wazuh MCP Server

### Step 1: Clone the Repository

```bash
mkdir -p ~/Documents/Docker_Projects/Wazuh_MCP
cd ~/Documents/Docker_Projects/Wazuh_MCP

git clone https://github.com/gensecaihq/Wazuh-MCP-Server.git
cd Wazuh-MCP-Server
```

### Step 2: Create Your Environment File

Create a `.env` file with your Wazuh credentials:

```bash
cat > .env << 'EOF'
# Wazuh Manager Settings
WAZUH_HOST=192.168.40.50          # Your Wazuh Manager IP (NO https:// prefix!)
WAZUH_USER=mcp_user               # Wazuh API user
WAZUH_PASS=YourSecurePassword     # Wazuh API password
WAZUH_PORT=55000                  # Wazuh API port (default: 55000)
VERIFY_SSL=false                  # Set to true if using valid SSL certs

# Wazuh Indexer Settings (Required for vulnerability data in Wazuh 4.8+)
WAZUH_INDEXER_HOST=192.168.40.50  # Usually same as manager
WAZUH_INDEXER_PORT=9200           # Indexer port
WAZUH_INDEXER_USER=admin          # Indexer username
WAZUH_INDEXER_PASS=YourIndexerPassword  # Indexer password

# MCP Server Settings
MCP_HOST=0.0.0.0
MCP_PORT=3000
AUTH_MODE=none                    # Options: none, bearer, oauth
LOG_LEVEL=DEBUG
EOF
```

> ⚠️ **Critical Configuration Notes:**
> 
> 1. **WAZUH_HOST** - Do NOT include `https://` - the code adds it automatically
> 2. **VERIFY_SSL** - Not `WAZUH_VERIFY_SSL` - the code uses `VERIFY_SSL`
> 3. **WAZUH_INDEXER_PASS** - Not `WAZUH_INDEXER_PASSWORD` - must be `WAZUH_INDEXER_PASS`

### Step 3: Fix the Server Code (Critical Bug Fix)

There's a bug in the server code where it doesn't pass the indexer configuration to the Wazuh client. We need to patch it:

```bash
# Find the line that creates the WazuhConfig manually
grep -n "wazuh_config = WazuhConfig(" src/wazuh_mcp_server/server.py
```

Edit `src/wazuh_mcp_server/server.py` and find this section (around line 278):

```python
# BEFORE (buggy):
wazuh_config = WazuhConfig(
    wazuh_host=config.WAZUH_HOST,
    wazuh_user=config.WAZUH_USER,
    wazuh_pass=config.WAZUH_PASS,
    wazuh_port=config.WAZUH_PORT,
    verify_ssl=config.WAZUH_VERIFY_SSL
)
```

Replace it with:

```python
# AFTER (fixed):
wazuh_config = WazuhConfig.from_env()
```

This ensures the indexer configuration is properly loaded from environment variables.

You can also do this with sed:

```bash
# Delete the old multi-line config (lines 278-284)
sed -i '278,284d' src/wazuh_mcp_server/server.py

# Insert the fixed version
sed -i '277a wazuh_config = WazuhConfig.from_env()' src/wazuh_mcp_server/server.py
```

### Step 4: Build and Start the Docker Container

```bash
docker compose build
docker compose up -d
```

### Step 5: Verify the Server is Running

```bash
# Check health status
curl -s http://localhost:3000/health | jq '.services'
```

Expected output:
```json
{
  "wazuh_manager": "healthy",
  "wazuh_indexer": "healthy",
  "mcp": "healthy"
}
```

If `wazuh_indexer` shows `"not_configured"`, double-check your `.env` file for the correct variable names.

### Step 6: Test the MCP Endpoint

```bash
curl -s -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq '.result.tools | length'
```

Expected output: `29` (the number of available tools)

---

## Part 2: Exposing the Wazuh Indexer (Required for Vulnerability Data)

By default, the Wazuh Indexer only listens on localhost. To query vulnerability data, you need to expose port 9200.

### On Your Wazuh Server:

```bash
# Check current binding
sudo ss -tlnp | grep 9200
# Output: LISTEN ... 127.0.0.1:9200 ...

# Edit the indexer configuration
sudo nano /etc/wazuh-indexer/opensearch.yml

# Find and change:
network.host: "127.0.0.1"
# To:
network.host: "0.0.0.0"

# Open the firewall port
sudo ufw allow 9200/tcp

# Restart the indexer
sudo systemctl restart wazuh-indexer

# Verify it's listening on all interfaces
sudo ss -tlnp | grep 9200
# Output: LISTEN ... 0.0.0.0:9200 ...
```

### Test from Your Workstation:

```bash
curl -k -u 'admin:YourIndexerPassword' 'https://YOUR_WAZUH_IP:9200/'
```

You should see cluster information including `"cluster_name" : "wazuh-cluster"`.

> 🔒 **Security Note:** Only expose port 9200 on trusted networks. Consider using firewall rules to restrict access to specific IPs.

---

## Part 3: Creating the Stdio Wrapper

Claude Desktop communicates via stdio, but our MCP server uses HTTP. We need a wrapper to translate between them.

### Create the Wrapper Script:

```bash
cat > ~/Documents/Docker_Projects/Wazuh_MCP/Wazuh-MCP-Server/stdio_wrapper.py << 'WRAPPER'
#!/usr/bin/env python3
"""
Stdio wrapper for Wazuh MCP HTTP Server
Translates stdio JSON-RPC to HTTP calls with strict response formatting
"""
import sys
import json
import requests

MCP_URL = "http://localhost:3000/mcp"

def clean_response(response_data, request_id):
    """
    Clean response to match strict MCP JSON-RPC format.
    Claude Desktop is very strict about the format.
    """
    cleaned = {"jsonrpc": "2.0"}
    
    if request_id is not None:
        cleaned["id"] = request_id
    elif "id" in response_data and response_data["id"] is not None:
        cleaned["id"] = response_data["id"]
    
    if "error" in response_data and response_data["error"] is not None:
        # Clean error object too - remove null data field
        error = response_data["error"]
        if isinstance(error, dict) and "data" in error and error["data"] is None:
            error = {k: v for k, v in error.items() if v is not None}
        cleaned["error"] = error
    elif "result" in response_data:
        cleaned["result"] = response_data["result"]
    
    return cleaned

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
            
            # Notifications have no id - don't send response
            if "id" not in request or request.get("id") is None:
                # Still forward to server but don't output anything
                try:
                    requests.post(
                        MCP_URL,
                        json=request,
                        headers={
                            "Content-Type": "application/json",
                            "Origin": "http://localhost"
                        },
                        timeout=5
                    )
                except:
                    pass
                continue
            
            request_id = request.get("id")
            
            # Forward to HTTP server
            response = requests.post(
                MCP_URL,
                json=request,
                headers={
                    "Content-Type": "application/json",
                    "Origin": "http://localhost"
                },
                timeout=120
            )
            
            result = response.json()
            cleaned = clean_response(result, request_id)
            print(json.dumps(cleaned), flush=True)
            
        except requests.exceptions.Timeout:
            if 'request_id' in dir() and request_id is not None:
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32001, "message": "Request timed out"}
                }
                print(json.dumps(error_resp), flush=True)
        except json.JSONDecodeError as e:
            pass  # Silently ignore malformed input
        except Exception as e:
            if 'request_id' in dir() and request_id is not None:
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": str(e)}
                }
                print(json.dumps(error_resp), flush=True)

if __name__ == "__main__":
    main()
WRAPPER

chmod +x ~/Documents/Docker_Projects/Wazuh_MCP/Wazuh-MCP-Server/stdio_wrapper.py
```

### Why This Wrapper is Necessary:

1. **Protocol Translation**: Claude Desktop uses stdio; the MCP server uses HTTP
2. **Response Cleaning**: The HTTP server returns `"error": null` which Claude Desktop's Zod validator rejects
3. **Notification Handling**: MCP notifications (no `id` field) shouldn't generate responses
4. **Origin Header**: The HTTP server requires an `Origin` header for CORS

### Test the Wrapper:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | python3 ~/Documents/Docker_Projects/Wazuh_MCP/Wazuh-MCP-Server/stdio_wrapper.py
```

Expected output (no `"error": null`):
```json
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26", ...}}
```

---

## Part 4: Configuring Claude Desktop

### Locate Your Config File:

```bash
# Linux
~/.config/Claude/claude_desktop_config.json

# macOS
~/Library/Application Support/Claude/claude_desktop_config.json

# Windows
%APPDATA%\Claude\claude_desktop_config.json
```

### Add the Wazuh MCP Server:

Edit your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "wazuh": {
      "command": "/usr/bin/python3",
      "args": [
        "/home/YOUR_USERNAME/Documents/Docker_Projects/Wazuh_MCP/Wazuh-MCP-Server/stdio_wrapper.py"
      ]
    }
  }
}
```

Replace `YOUR_USERNAME` with your actual username.

### Restart Claude Desktop

Close and reopen Claude Desktop. The Wazuh tools should now be available.

---

## Part 5: Available Tools

Once connected, you'll have access to **29 security tools**:

### Alert Management
| Tool | Description |
|------|-------------|
| `get_wazuh_alerts` | Retrieve alerts with filtering |
| `get_wazuh_alert_summary` | Get alert summary by field |
| `analyze_alert_patterns` | Identify trends and anomalies |
| `search_security_events` | Search across all Wazuh data |

### Agent Management
| Tool | Description |
|------|-------------|
| `get_wazuh_agents` | List all agents |
| `get_wazuh_running_agents` | List active agents |
| `check_agent_health` | Check specific agent health |
| `get_agent_processes` | Get running processes |
| `get_agent_ports` | Get open ports |
| `get_agent_configuration` | Get agent config |

### Vulnerability Management
| Tool | Description |
|------|-------------|
| `get_wazuh_vulnerabilities` | Get all vulnerabilities |
| `get_wazuh_critical_vulnerabilities` | Get critical CVEs |
| `get_wazuh_vulnerability_summary` | Get vuln statistics |

### Security Analysis
| Tool | Description |
|------|-------------|
| `analyze_security_threat` | AI-powered threat analysis |
| `check_ioc_reputation` | Check IoC reputation |
| `perform_risk_assessment` | Comprehensive risk assessment |
| `get_top_security_threats` | Top threats by frequency |
| `generate_security_report` | Generate security reports |
| `run_compliance_check` | PCI-DSS, HIPAA, NIST checks |

### System Monitoring
| Tool | Description |
|------|-------------|
| `get_wazuh_statistics` | Comprehensive metrics |
| `get_wazuh_weekly_stats` | Weekly statistics |
| `get_wazuh_cluster_health` | Cluster health info |
| `get_wazuh_cluster_nodes` | Cluster node info |
| `get_wazuh_rules_summary` | Rules effectiveness |
| `get_wazuh_remoted_stats` | Agent communication stats |
| `get_wazuh_log_collector_stats` | Log collector stats |
| `search_wazuh_manager_logs` | Search manager logs |
| `get_wazuh_manager_error_logs` | Get error logs |
| `validate_wazuh_connection` | Test connectivity |

---

## Part 6: Example Conversations

Once everything is set up, you can have natural conversations with Claude about your security posture:

### Check Critical Vulnerabilities
> **You:** How many critical CVEs do I have in my network?
> 
> **Claude:** *[Calls get_wazuh_critical_vulnerabilities]* You have 24 critical CVEs across your network. The majority affect your pop-os workstation (18) and MAC-TH-LAB (6). The most concerning are CVE-2025-13836 affecting Python and several FFmpeg vulnerabilities...

### Generate a Security Report
> **You:** Generate a daily security report for my environment.
> 
> **Claude:** *[Calls generate_security_report]* Here's your daily security report...

### Check Agent Status
> **You:** Are all my agents online?
> 
> **Claude:** *[Calls get_wazuh_running_agents]* You have 2 active agents: SIEM (your manager running Ubuntu 24.04) and pop-os (your workstation running Pop!_OS 22.04). Both are healthy and reporting.

### Run Compliance Check
> **You:** Run a PCI-DSS compliance check on my environment.
> 
> **Claude:** *[Calls run_compliance_check]* Here are your PCI-DSS compliance results...

---

## Troubleshooting

### "wazuh_indexer": "not_configured"

**Cause:** The server code isn't reading indexer environment variables.

**Solution:** Apply the code fix in Part 1, Step 3 to use `WazuhConfig.from_env()`.

### Connection Refused on Port 9200

**Cause:** Wazuh Indexer is only listening on localhost.

**Solution:** Follow Part 2 to expose the indexer on all interfaces.

### Claude Desktop Shows "Tool execution failed"

**Cause:** Usually a timeout or response format issue.

**Solutions:**
1. Check Docker container is running: `docker compose ps`
2. Check container logs: `docker compose logs --tail=50`
3. Test the wrapper manually (see Part 3)

### "Origin header required" Error

**Cause:** The MCP server requires CORS headers.

**Solution:** Ensure the stdio wrapper includes the `Origin: http://localhost` header.

### Zod Validation Errors in Claude Desktop

**Cause:** Response includes `"error": null` or `"id": null`.

**Solution:** The stdio wrapper should strip null values. Verify the `clean_response` function is working.

### Double https:// in URL

**Cause:** Including `https://` in WAZUH_HOST.

**Solution:** Set `WAZUH_HOST=192.168.40.50` without any protocol prefix.

---

## Quick Reference

### Start the Server
```bash
cd ~/Documents/Docker_Projects/Wazuh_MCP/Wazuh-MCP-Server
docker compose up -d
```

### Check Server Health
```bash
curl -s http://localhost:3000/health | jq '.services'
```

### View Server Logs
```bash
docker compose logs -f
```

### Restart After Config Changes
```bash
docker compose down && docker compose up -d
```

### Test Wrapper Manually
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python3 ~/Documents/Docker_Projects/Wazuh_MCP/Wazuh-MCP-Server/stdio_wrapper.py | jq '.result.tools | length'
```

---

## Conclusion

You now have a fully functional integration between Wazuh SIEM and Claude Desktop. This setup allows you to:

- Query security data using natural language
- Get instant insights into vulnerabilities, alerts, and agent status
- Generate reports and run compliance checks conversationally
- Leverage AI to analyze security threats

The MCP protocol opens up exciting possibilities for security operations. As you use this integration, you'll find new ways to leverage Claude's capabilities for security analysis and response.

### What's Next?

- Add more MCP servers (Shodan, VirusTotal, etc.) for comprehensive threat intelligence
- Create custom prompts for routine security checks
- Build automated security workflows combining multiple tools

---

## Resources

- [Wazuh Documentation](https://documentation.wazuh.com/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)
- [gensecaihq/Wazuh-MCP-Server](https://github.com/gensecaihq/Wazuh-MCP-Server)

---

*Happy hunting! 🛡️*
