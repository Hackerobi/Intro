# Integrating LitterBox Malware Analysis Sandbox with Claude AI: A Complete Guide

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Intermediate  
**Time Required:** 1-2 hours

---

## Introduction

Imagine telling your AI assistant: *"Upload this payload and run a full OPSEC analysis — tell me what's getting detected and why"* and getting back a comprehensive breakdown of YARA signatures, memory detections, ETW telemetry hits, and a prioritized improvement plan. That's what this guide will help you build.

**LitterBox** is a private malware analysis sandbox created by [BlackSnufkin](https://github.com/BlackSnufkin/LitterBox) that lets red teamers and security researchers test payloads against real detection mechanisms — without ever exposing them to external vendors like VirusTotal. Combined with Claude Desktop via MCP, you get an AI-powered analysis workflow that keeps everything in-house.

By the end of this guide, you'll have:
- A Windows 10 sandbox running via Docker + KVM on your Linux workstation
- 20+ malware analysis tools available through Claude Desktop
- AI-powered OPSEC recommendations for your payloads
- Static, dynamic, and BYOVD analysis at your fingertips

### What is LitterBox?

LitterBox provides a controlled sandbox environment designed for security professionals to:

- Test evasion techniques against modern detection mechanisms
- Validate detection signatures before field deployment
- Analyze malware behavior in an isolated environment
- Keep payloads in-house without exposing them to external security vendors
- Get AI-powered OPSEC analysis and improvement recommendations

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude interact with your security tools directly.

### What You'll Need

- **Linux workstation** (this guide uses Pop!_OS, but Ubuntu/Debian will work)
- **Docker Engine** (Docker CE) with Compose plugin
- **KVM hardware virtualization support** (Intel VT-x or AMD-V)
- **Claude Desktop** application
- **Python 3** with pip
- At least **8GB RAM** and **20GB free disk space**
- Basic familiarity with command line and Docker

---

## Architecture Overview

```
┌─────────────────┐     stdio      ┌──────────────────┐     HTTP      ┌─────────────────────────────────┐
│  Claude Desktop │◄──────────────►│  LitterBoxMCP.py │◄─────────────►│  LitterBox Flask Server         │
│                 │   JSON-RPC     │  (FastMCP/stdio)  │   REST API   │  (Windows 10 VM in Docker)      │
└─────────────────┘                └──────────────────┘               │                                 │
                                                                      │  ┌─────────────────────────┐    │
                                                                      │  │ Static Analysis          │    │
                                                                      │  │ • YARA Signatures        │    │
                                                                      │  │ • CheckPlz (AV Testing)  │    │
                                                                      │  │ • Stringnalyzer          │    │
                                                                      │  └─────────────────────────┘    │
                                                                      │  ┌─────────────────────────┐    │
                                                                      │  │ Dynamic Analysis         │    │
                                                                      │  │ • PE-Sieve               │    │
                                                                      │  │ • Moneta                 │    │
                                                                      │  │ • HollowsHunter          │    │
                                                                      │  │ • Hunt-Sleeping-Beacons  │    │
                                                                      │  │ • RedEdr (ETW)           │    │
                                                                      │  │ • Patriot                │    │
                                                                      │  └─────────────────────────┘    │
                                                                      │  ┌─────────────────────────┐    │
                                                                      │  │ BYOVD Analysis           │    │
                                                                      │  │ • HolyGrail              │    │
                                                                      │  │ • LOLDrivers DB          │    │
                                                                      │  │ • MS Block Policy Check  │    │
                                                                      │  └─────────────────────────┘    │
                                                                      └─────────────────────────────────┘
```

**How it works:**

1. Docker runs a Windows 10 virtual machine using KVM hardware virtualization
2. LitterBox Flask server runs inside the Windows VM on port 1337
3. The `LitterBoxMCP.py` server (running locally on your Linux host) connects to the Flask API
4. Claude Desktop communicates with `LitterBoxMCP.py` via stdio transport
5. You talk to Claude, Claude talks to LitterBox, LitterBox analyzes your payloads

**Ports Used:**

| Port | Service | Description |
|------|---------|-------------|
| 8006 | Web Viewer | Monitor Windows installation progress |
| 3389 | RDP | Remote desktop to the Windows VM |
| 1337 | LitterBox | Web UI and REST API |

---

## Part 1: Prerequisites — Docker and KVM

### Step 1: Install Docker Engine

If you already have Docker CE installed, skip to Step 2.

```bash
# Update package index
sudo apt update

# Install Docker prerequisites
sudo apt install -y ca-certificates curl gnupg

# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add the Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install -y docker-ce docker-ce-cli docker-compose-plugin

# Add your user to the docker group
sudo usermod -aG docker $USER
```

> ⚠️ **Pop!_OS Note:** If you already have `containerd` installed (common on Pop!_OS), you may get a conflict with `containerd.io`. This is fine — the existing `containerd` package works with Docker CE. If you hit this conflict, install without `containerd.io`:
> ```bash
> sudo apt install -y docker-ce docker-ce-cli docker-compose-plugin
> ```

> ⚠️ **Compose Command:** Use `docker compose` (with a space, the plugin version), NOT `docker-compose` (the standalone binary). The standalone version is deprecated and may not be installed.

### Step 2: Verify KVM Support

LitterBox runs Windows 10 inside Docker using KVM virtualization. Your CPU must support this:

```bash
sudo apt install -y cpu-checker
sudo kvm-ok
```

Expected output:
```
INFO: /dev/kvm exists
KVM acceleration can be used
```

If you don't see this, you need to enable Intel VT-x or AMD-V in your BIOS.

Also verify the required devices exist:
```bash
ls -la /dev/kvm
ls -la /dev/net/tun
```

### Step 3: Verify Docker is Working

```bash
docker --version
# Docker version 29.x.x or higher

docker compose version
# Docker Compose version v2.x.x
```

---

## Part 2: Installing LitterBox

### Step 1: Clone the Repository

```bash
mkdir -p ~/Documents/Docker_Projects/LitterBox_MCP
cd ~/Documents/Docker_Projects/LitterBox_MCP

git clone https://github.com/BlackSnufkin/LitterBox.git
cd LitterBox/Docker
```

### Step 2: Check for Port Conflicts

LitterBox uses port 3389 for RDP, which may already be in use:

```bash
sudo ss -tlnp | grep 3389
```

If port 3389 is occupied (common if you run xrdp or other RDP services), remap it:

```bash
# Remap RDP from 3389 to 3390
sed -i 's/- 3389:3389/- 3390:3389/g' docker-compose.yml
```

### Step 3: Start the Container

```bash
sudo docker compose up
```

> 📝 **First Run:** The initial startup takes **30-60 minutes** depending on your internet speed. Docker will:
> 1. Pull the `dockurr/windows` image (~135MB)
> 2. Boot a Windows 10 virtual machine
> 3. Automatically install LitterBox and all analysis tools
> 4. Start the Flask server on port 1337

You can monitor the installation progress at **http://localhost:8006** — this shows the Windows desktop in your browser so you can watch everything happening in real-time.

### Step 4: Verify LitterBox is Running

Once you see this in the Docker logs, LitterBox is ready:

```
Starting LitterBox Malware Analysis Platform...
 * Running on http://127.0.0.1:1337
 * Running on http://172.30.0.2:1337
```

Or visit **http://localhost:8006** and you should see the Windows desktop with a console showing the Flask server output.

---

## Part 3: Setting Up the MCP Client

The MCP client is what connects Claude Desktop to the LitterBox API. It consists of two Python files from the `GrumpyCats` package.

### Step 1: Create the MCP Server Directory

```bash
mkdir -p ~/Documents/Docker_Projects/LitterBox_MCP/MCP_Server
cd ~/Documents/Docker_Projects/LitterBox_MCP/MCP_Server
```

### Step 2: Copy the Client Files

```bash
# Copy the MCP server and CLI client
cp ~/Documents/Docker_Projects/LitterBox_MCP/LitterBox/GrumpyCats/grumpycat.py .
cp ~/Documents/Docker_Projects/LitterBox_MCP/LitterBox/GrumpyCats/LitterBoxMCP.py .
```

### Step 3: Fix the Module Import

`LitterBoxMCP.py` imports from `optimized_litterbox_client`, but the actual file is named `grumpycat.py`. Create a symlink:

```bash
ln -s grumpycat.py optimized_litterbox_client.py
```

### Step 4: Install Python Dependencies

```bash
pip install requests fastmcp mcp-server
```

> 📝 **Note:** On some systems you may need `pip install --break-system-packages`. On Pop!_OS, pip installs to `~/.local` by default, so this flag usually isn't needed.

### Step 5: Fix the Transport Mode (Critical!)

The MCP server ships configured for HTTP transport, but Claude Desktop requires **stdio** transport. This is a one-line fix:

```bash
cd ~/Documents/Docker_Projects/LitterBox_MCP/MCP_Server

# Change from HTTP server to stdio transport
sed -i 's/mcp.serve(host="0.0.0.0", port=50051)/mcp.run(transport="stdio")/' LitterBoxMCP.py
```

Verify the change:
```bash
tail -10 LitterBoxMCP.py
```

You should see:
```python
if __name__ == "__main__":
    try:
        logger.info("Starting LitterBox OPSEC MCP Server...")
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    finally:
        cleanup_on_exit()
```

### Step 6: Test the Connection

```bash
python3 grumpycat.py --url http://127.0.0.1:1337 health
```

Expected output:
```
Service is healthy
{
  "configuration": {
    "dynamic_analysis": {
      "hollows_hunter": true,
      "hsb": true,
      "moneta": true,
      "patriot": true,
      "pe_sieve": true,
      "rededr": true,
      "yara": true
    },
    "holygrail_analysis": true,
    "static_analysis": {
      "checkplz": true,
      "stringnalyzer": true,
      "yara": true
    }
  },
  "issues": [],
  "status": "ok",
  "upload_folder_accessible": true
}
```

All engines green, zero issues — you're ready for MCP integration.

> ⚠️ **Pop!_OS Note:** Use `python3` not `python`. Pop!_OS doesn't create a `python` symlink by default.

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

### Add the LitterBox MCP Server

Edit your config to add the `litterbox` entry:

```json
{
  "mcpServers": {
    "litterbox": {
      "command": "/usr/bin/python3",
      "args": [
        "/home/YOUR_USERNAME/Documents/Docker_Projects/LitterBox_MCP/MCP_Server/LitterBoxMCP.py"
      ],
      "env": {
        "PYTHONPATH": "/home/YOUR_USERNAME/Documents/Docker_Projects/LitterBox_MCP/MCP_Server"
      }
    }
  }
}
```

Replace `YOUR_USERNAME` with your actual username.

> 📝 **Note:** If you already have other MCP servers configured (like Wazuh, Burp Suite, etc.), just add the `litterbox` entry alongside them inside the existing `mcpServers` object.

### Restart Claude Desktop

Close and reopen Claude Desktop. The LitterBox tools should now appear in the tools list.

---

## Part 5: Available Tools

Once connected, you'll have access to **20+ malware analysis tools**:

### Payload Management
| Tool | Description |
|------|-------------|
| `upload_payload` | Upload a payload for comprehensive OPSEC analysis |
| `upload_kernel_driver` | Upload a kernel driver for BYOVD analysis |
| `list_analyzed_payloads` | List all analyzed payloads with OPSEC summary |
| `delete_payload` | Delete a payload and all associated results |

### Static Analysis
| Tool | Description |
|------|-------------|
| `analyze_static` | Run YARA signatures, PE structure analysis, import mapping |
| `get_file_info` | Get file metadata, entropy analysis, PE structure |
| `get_static_results` | Retrieve YARA matches, signatures, imports |

### Dynamic Analysis
| Tool | Description |
|------|-------------|
| `analyze_dynamic` | Run behavioral detection, runtime artifacts, process analysis |
| `get_dynamic_results` | Retrieve behavioral detections and runtime artifacts |
| `validate_pid` | Validate a process ID before dynamic analysis |
| `analyze_running_process` | Analyze a currently running process |

### BYOVD Analysis (HolyGrail)
| Tool | Description |
|------|-------------|
| `analyze_holygrail` | Run HolyGrail BYOVD analysis on kernel drivers |
| `get_holygrail_results` | Get BYOVD analysis results |

### Doppelganger Analysis
| Tool | Description |
|------|-------------|
| `run_blender_scan` | System-wide process scan for baseline comparison |
| `compare_with_blender` | Compare payload against system process baseline |
| `create_fuzzy_database` | Create fuzzy hash database for similarity analysis |
| `analyze_fuzzy_similarity` | Analyze payload similarity using fuzzy hashing |

### Reporting & Management
| Tool | Description |
|------|-------------|
| `get_comprehensive_results` | Get all available analysis results for a target |
| `generate_opsec_report` | Generate comprehensive OPSEC analysis report |
| `download_analysis_report` | Download analysis report to specified location |
| `check_sandbox_health` | Verify sandbox tools and engines are operational |
| `get_system_status` | Get comprehensive system health and analysis status |
| `cleanup_analysis_artifacts` | Clean up all testing artifacts and temporary files |

---

## Part 6: OPSEC Analysis Prompts

One of the most powerful features of the MCP integration is AI-powered OPSEC analysis. Here are some conversation starters:

### Detection Pattern Analysis
> **You:** Upload this payload and run a full analysis. Then tell me exactly what's getting detected and why.
>
> **Claude:** *[Uploads payload, runs static and dynamic analysis, then provides a breakdown of every YARA rule hit, memory detection, and ETW telemetry event with explanations of why each was triggered]*

### Evasion Effectiveness Assessment
> **You:** How effective are the evasion techniques in this payload? What's working and what's not?
>
> **Claude:** *[Analyzes results and categorizes evasion techniques by effectiveness — what successfully bypassed detection vs what got caught]*

### Attribution Risk Analysis
> **You:** Are there any fingerprints or patterns in this payload that could be used for attribution?
>
> **Claude:** *[Examines strings, metadata, compilation artifacts, and behavioral patterns that could link the payload to specific tools, frameworks, or operators]*

### OPSEC Improvement Plan
> **You:** Based on the analysis, give me a prioritized improvement roadmap for this payload.
>
> **Claude:** *[Generates a prioritized list of improvements ranked by impact, from quick wins to fundamental changes needed]*

### Deployment Readiness Check
> **You:** Is this payload ready for deployment? Give me a go/no-go assessment.
>
> **Claude:** *[Provides a deployment decision framework weighing detection risk, attribution risk, and operational requirements]*

### Driver BYOVD Assessment
> **You:** Upload this driver and check if it's viable for a BYOVD attack.
>
> **Claude:** *[Runs HolyGrail analysis checking against LOLDrivers database, Microsoft block policies, and dangerous import analysis]*

---

## Part 7: Analysis Workflow Example

Here's a typical end-to-end workflow:

### 1. Check Sandbox Health
```
You: Is the sandbox healthy and ready to go?
Claude: [Calls check_sandbox_health] All engines are operational — static analysis
        (YARA, CheckPlz, Stringnalyzer), dynamic analysis (PE-Sieve, Moneta,
        Patriot, HollowsHunter, RedEdr, Hunt-Sleeping-Beacons), and HolyGrail
        BYOVD are all green. Zero issues.
```

### 2. Upload a Payload
```
You: Upload the payload at /path/to/payload.exe and give it the name "test-implant"
Claude: [Calls upload_payload] Payload uploaded successfully. SHA256: abc123...
        Ready for analysis.
```

### 3. Run Static Analysis
```
You: Run static analysis on it.
Claude: [Calls analyze_static] Static analysis complete. Here's what I found:
        - 3 YARA rule matches
        - High entropy in .text section (possible packing)
        - Suspicious imports: VirtualAlloc, WriteProcessMemory...
```

### 4. Run Dynamic Analysis
```
You: Now run dynamic analysis.
Claude: [Calls analyze_dynamic] Dynamic analysis results:
        - PE-Sieve detected 2 modified memory regions
        - Moneta flagged suspicious memory allocation patterns
        - No sleeping beacon patterns detected
        - ETW captured 47 telemetry events...
```

### 5. Get OPSEC Report
```
You: Generate a full OPSEC report with recommendations.
Claude: [Calls generate_opsec_report] Here's your comprehensive OPSEC assessment
        with prioritized recommendations for improving evasion...
```

---

## Part 8: Sharing Payloads with the Sandbox

The Docker container mounts a shared folder between your Linux host and the Windows VM:

| Host Path | VM Path |
|-----------|----------|
| `~/Documents/Docker_Projects/LitterBox_MCP/LitterBox/Docker/share/` | `D:\` |

To analyze a local payload:
1. Copy it to the share folder on your host
2. Ask Claude to upload it from `D:\filename.exe` inside the VM
3. Or use the MCP `upload_payload` tool with the local path

---

## Troubleshooting

### `containerd.io` Package Conflict (Pop!_OS)

**Problem:** Docker CE installation fails with a conflict against the existing `containerd` package.

**Solution:** Pop!_OS ships with its own `containerd` package. This works fine with Docker CE — just skip `containerd.io`:
```bash
sudo apt install -y docker-ce docker-ce-cli docker-compose-plugin
```

### `docker-compose: command not found`

**Problem:** The standalone `docker-compose` binary isn't installed.

**Solution:** Use the Compose plugin instead:
```bash
# Use this (plugin, with a space):
docker compose up

# NOT this (standalone, with a hyphen):
docker-compose up
```

### Port 3389 Already in Use

**Problem:** RDP port conflicts with existing services.

**Solution:** Remap to a different port:
```bash
sed -i 's/- 3389:3389/- 3390:3389/g' docker-compose.yml
```

### `python: command not found`

**Problem:** Pop!_OS uses `python3`, not `python`.

**Solution:** Always use `python3`:
```bash
python3 grumpycat.py --url http://127.0.0.1:1337 health
```

### Module Import Error: `optimized_litterbox_client`

**Problem:** `LitterBoxMCP.py` tries to import `optimized_litterbox_client` but the file is named `grumpycat.py`.

**Solution:** Create a symlink:
```bash
cd ~/Documents/Docker_Projects/LitterBox_MCP/MCP_Server
ln -s grumpycat.py optimized_litterbox_client.py
```

### Claude Desktop Can't Connect to LitterBox

**Problem:** Tools appear in Claude Desktop but calls fail.

**Solutions:**
1. Verify the Docker container is running: `sudo docker compose ps`
2. Check LitterBox health: `python3 grumpycat.py --url http://127.0.0.1:1337 health`
3. Verify the transport fix was applied: `tail -5 LitterBoxMCP.py` should show `mcp.run(transport="stdio")`
4. Check `PYTHONPATH` is set in your Claude Desktop config

### MCP Server Uses HTTP Instead of stdio

**Problem:** The MCP server ships with `mcp.serve(host="0.0.0.0", port=50051)` which is HTTP mode, but Claude Desktop requires stdio.

**Solution:**
```bash
sed -i 's/mcp.serve(host="0.0.0.0", port=50051)/mcp.run(transport="stdio")/' LitterBoxMCP.py
```

### Windows VM Not Booting

**Problem:** Container starts but Windows doesn't appear at localhost:8006.

**Solutions:**
1. Verify KVM: `sudo kvm-ok`
2. Check device access: `ls -la /dev/kvm /dev/net/tun`
3. Check Docker logs: `sudo docker compose logs -f`
4. Ensure sufficient resources (8GB+ RAM recommended)

---

## Quick Reference

### Start LitterBox
```bash
cd ~/Documents/Docker_Projects/LitterBox_MCP/LitterBox/Docker
sudo docker compose up -d
```

### Stop LitterBox
```bash
cd ~/Documents/Docker_Projects/LitterBox_MCP/LitterBox/Docker
sudo docker compose down
```

### Check Health
```bash
python3 ~/Documents/Docker_Projects/LitterBox_MCP/MCP_Server/grumpycat.py --url http://127.0.0.1:1337 health
```

### View Windows Desktop
Open **http://localhost:8006** in your browser.

### RDP to Windows VM
```bash
# If port was remapped to 3390:
xfreerdp /v:localhost:3390 /u:Docker /p:yourpassword
```

### View Docker Logs
```bash
cd ~/Documents/Docker_Projects/LitterBox_MCP/LitterBox/Docker
sudo docker compose logs -f
```

---

## Security Considerations

- **Isolation:** The Windows VM runs inside Docker with KVM. Payloads execute inside the VM, not on your host.
- **Network:** Be cautious about payload network activity. Consider running the Docker container on an isolated network.
- **Shared Folder:** The `share/` directory is mounted as `D:\` in the VM. Don't store sensitive files there.
- **API Access:** LitterBox listens on localhost:1337 by default. Don't expose this to the network without authentication.
- **Cleanup:** Use the `cleanup_analysis_artifacts` tool regularly to remove analysis residue.

---

## Conclusion

You now have a fully private, AI-powered malware analysis sandbox running on your Linux workstation. This setup lets you:

- Analyze payloads without exposing them to external vendors
- Get AI-powered OPSEC recommendations through natural conversation
- Run static, dynamic, and BYOVD analysis from Claude Desktop
- Keep your red team tooling completely in-house

The combination of LitterBox's comprehensive detection engines with Claude's analytical capabilities creates a workflow that would have seemed like science fiction just a couple of years ago. Ask a question in plain English, get a detailed technical analysis back.

### What's Next?

- Combine LitterBox with your other MCP tools (Wazuh for blue team validation, BloodHound for attack path planning)
- Build custom YARA rules based on analysis results
- Create automated pre-deployment checklists
- Use fuzzy hashing to track payload lineage across iterations

---

## Resources

- [BlackSnufkin/LitterBox](https://github.com/BlackSnufkin/LitterBox) — Official repository
- [LitterBox Wiki](https://github.com/BlackSnufkin/LitterBox/wiki) — Advanced configuration guides
- [MCP Protocol Specification](https://modelcontextprotocol.io/) — Learn about MCP
- [Claude Desktop](https://claude.ai/download) — Download Claude Desktop
- [FastMCP Documentation](https://github.com/jlowin/fastmcp) — MCP Python framework

---

## Acknowledgments

Special thanks to:
- **BlackSnufkin** for creating LitterBox — an incredible tool for the offensive security community
- **Anthropic** for Claude and the Model Context Protocol
- **hasherezade** for PE-Sieve and HollowsHunter
- **Forrest Orr** for Moneta
- **joe-desimone** for Hunt-Sleeping-Beacons
- **dobin** for RedEdr
- The entire **offensive security community** for pushing the boundaries of what's possible

---

*Happy hunting, stay curious, and keep your payloads to yourself!* 🐱

**— Hackerobi**
