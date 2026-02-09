# Integrating KVM/QEMU Virtual Machine Management with Claude AI: A Complete Guide

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Intermediate  
**Time Required:** 30-45 minutes

---

## Introduction

Imagine telling your AI assistant: *"Create an isolated pentest network on 10.10.10.0/24, spin up a Kali VM and a Windows target from my templates, snapshot them both as clean states, and start them up"* — and watching your entire lab environment materialize in seconds. This guide will show you how to connect **KVM/QEMU** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude direct control over your virtual machine infrastructure.

By the end of this guide, you'll have:
- 21 VM management tools available in Claude Desktop
- Full VM lifecycle control (create, start, stop, reboot, clone, delete)
- Network management for segmented lab environments
- Snapshot management for saving and reverting VM states
- ISO discovery and OS variant support for creating new VMs
- The ability to build entire pentest lab environments through natural conversation

### What is KVM/QEMU?

[KVM](https://www.linux-kvm.org/) (Kernel-based Virtual Machine) is the Linux kernel's built-in hypervisor. Combined with [QEMU](https://www.qemu.org/) for hardware emulation and [libvirt](https://libvirt.org/) for management, it provides enterprise-grade virtualization that's free, open-source, and deeply integrated into Linux.

If you're using **virt-manager** (Virtual Machine Manager) on Linux, you're already using KVM/QEMU/libvirt under the hood.

### What is the KVM MCP Server?

The KVM MCP Server is a custom-built MCP server that exposes libvirt's full VM management capabilities as MCP tools. Built with Python's FastMCP framework and libvirt-python bindings, it lets Claude:

- List, start, stop, and manage VMs
- Create VMs from ISO images with full customization
- Clone existing VMs (perfect for template-based lab deployment)
- Create and manage isolated networks for lab segmentation
- Hot-plug and remove network interfaces
- Create, revert, and manage snapshots
- Discover available ISOs and OS variants

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude talk to your favorite platforms — in this case, your hypervisor.

### What You'll Need

- **Linux workstation** (this guide uses Pop!_OS, but Ubuntu/Debian will work)
- **KVM/QEMU with libvirt** installed and running
- **virt-manager** (Virtual Machine Manager) — recommended but not required
- **Python 3.10+** with venv support
- **Claude Desktop** application
- Basic familiarity with command line and virtual machines

---

## Architecture Overview

```
┌─────────────────┐    stdio     ┌──────────────────────────────┐   libvirt    ┌──────────────────────┐
│  Claude Desktop │◄────────────►│  KVM MCP Server              │◄────────────►│  libvirtd            │
│                 │   JSON-RPC   │  (FastMCP + libvirt-python)   │   API        │  (QEMU/KVM)          │
└─────────────────┘              │                              │              │                      │
                                 │  ┌────────────────────────┐  │              │  ┌────────────────┐  │
                                 │  │ VM Lifecycle            │  │              │  │ Virtual Machines│  │
                                 │  │ • List / Info           │  │              │  │ • Kali Linux    │  │
                                 │  │ • Start / Stop          │  │              │  │ • Windows 10/11│  │
                                 │  │ • Reboot / Delete       │  │              │  │ • Win Server    │  │
                                 │  │ • Create / Clone        │  │              │  │ • pfSense       │  │
                                 │  └────────────────────────┘  │              │  └────────────────┘  │
                                 │  ┌────────────────────────┐  │              │  ┌────────────────┐  │
                                 │  │ Network Management      │  │              │  │ Virtual Networks│  │
                                 │  │ • Create Isolated Nets  │  │              │  │ • vnet-adlab    │  │
                                 │  │ • NAT / Bridge          │  │              │  │ • vnet-lan      │  │
                                 │  │ • Attach / Detach NICs  │  │              │  │ • vnet-egress   │  │
                                 │  └────────────────────────┘  │              │  │ • br0 (LAN)     │  │
                                 │  ┌────────────────────────┐  │              │  └────────────────┘  │
                                 │  │ Snapshot Management     │  │              │  ┌────────────────┐  │
                                 │  │ • Create Snapshots      │  │              │  │ Storage         │  │
                                 │  │ • Revert to Snapshot    │  │              │  │ • qcow2 disks   │  │
                                 │  │ • List / Delete          │  │              │  │ • ISO images    │  │
                                 │  └────────────────────────┘  │              │  └────────────────┘  │
                                 └──────────────────────────────┘              └──────────────────────┘
```

**How it works:**

1. The KVM MCP Server runs as a native Python process on your host
2. It connects to libvirtd via the `qemu:///system` URI
3. Claude Desktop communicates with the server via stdio transport
4. The server translates Claude's requests into libvirt API calls and virt-install commands
5. You talk to Claude, Claude manages your VMs

**Key Design Decision — Native Python (not Docker):** Unlike most of our MCP integrations, this server runs natively on the host because it needs direct access to libvirt's Unix socket and system-level tools like `virt-install` and `virt-clone`. Running inside Docker would require privileged mode and device passthrough, which defeats the purpose.

---

## Part 1: Prerequisites

### Step 1: Verify KVM/QEMU is Installed

```bash
# Check if KVM is available
kvm-ok
# INFO: /dev/kvm exists
# KVM acceleration can be used

# Check libvirt is running
sudo systemctl status libvirtd
# ● libvirtd.service - Virtualization daemon
#   Active: active (running)

# Check virt-manager version
virt-manager --version
# 4.0.0
```

If KVM isn't installed:

```bash
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients \
    bridge-utils virt-manager virtinst libvirt-dev pkg-config python3-dev
```

### Step 2: Verify Your User is in the libvirt Group

```bash
groups | grep libvirt
```

If not:

```bash
sudo usermod -aG libvirt $USER
# Log out and back in for changes to take effect
```

### Step 3: Verify You Have VMs

```bash
virsh list --all
```

You should see your existing VMs. If you're starting fresh, that's fine too — Claude will help you create them!

---

## Part 2: Building the KVM MCP Server

### Step 1: Create the Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/KVM_MCP
cd ~/Documents/Docker_Projects/KVM_MCP
```

### Step 2: Create the Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install 'mcp[server]>=1.6.0' 'libvirt-python>=8.0.0' 'pydantic>=2.0.0'
```

> ⚠️ **Note:** `libvirt-python` requires the `libvirt-dev` system package to compile. If the install fails, run: `sudo apt install libvirt-dev pkg-config python3-dev`

### Step 4: Create the Package Structure

```bash
mkdir -p kvm_mcp
touch kvm_mcp/__init__.py
```

### Step 5: Create the Server

Create `kvm_mcp/server.py` with the full server code. The server implements 21 tools across four categories:

**VM Lifecycle (5 tools):**
- `kvm_list_vms` — List all VMs with state, resources, networks, and IPs
- `kvm_vm_info` — Detailed info on a specific VM
- `kvm_start_vm` — Start a shutoff VM
- `kvm_stop_vm` — Graceful shutdown or force power-off
- `kvm_reboot_vm` — Reboot a running VM

**VM Creation & Deletion (3 tools):**
- `kvm_create_vm` — Create new VMs from ISO with full customization
- `kvm_clone_vm` — Clone existing VMs (great for template-based deployment)
- `kvm_delete_vm` — Remove VMs with optional disk cleanup

**Network Management (7 tools):**
- `kvm_list_networks` — List all libvirt networks AND host bridges
- `kvm_network_info` — Detailed network info including XML definition
- `kvm_create_network` — Create isolated, NAT, or routed networks
- `kvm_start_network` / `kvm_stop_network` — Network lifecycle
- `kvm_delete_network` — Remove networks
- `kvm_attach_network` — Hot-plug a NIC onto a VM
- `kvm_detach_network` — Remove a NIC by MAC address

**Snapshot Management (4 tools):**
- `kvm_list_snapshots` — List all snapshots for a VM
- `kvm_create_snapshot` — Create disk+memory snapshots
- `kvm_revert_snapshot` — Revert to a previous state
- `kvm_delete_snapshot` — Clean up old snapshots

**Utility (2 tools):**
- `kvm_list_isos` — Discover available ISO images
- `kvm_list_os_variants` — List valid OS variants for virt-install

The full server code is available in this repository. Key implementation details:

- **FastMCP with Context injection** — Every tool receives the libvirt connection via `ctx: Context`, backed by lifespan management
- **Module-level connection** — The libvirt connection is stored as a module global during lifespan startup, bypassing SDK attribute path differences
- **Pydantic v2 validation** — All inputs are validated with Field constraints
- **Tool annotations** — Every tool has `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint` set correctly
- **virt-install/virt-clone** — VM creation and cloning use subprocess calls to these battle-tested tools

### Step 6: Test the Server

```bash
cd ~/Documents/Docker_Projects/KVM_MCP
PYTHONPATH=. .venv/bin/python kvm_mcp/server.py
```

You should see:
```
2026-02-09 16:20:31,683 [INFO] kvm_mcp: Connecting to libvirt at qemu:///system …
2026-02-09 16:20:31,685 [INFO] kvm_mcp: Connected to libvirt — hypervisor version 6002000
```

Press `Ctrl+C` to stop. If you see the "Connected to libvirt" message, the server is working!

---

## Part 3: Configuring Claude Desktop

### The Config Entry

Add this to your `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kvm": {
      "command": "/home/YOUR_USERNAME/Documents/Docker_Projects/KVM_MCP/.venv/bin/python",
      "args": ["/home/YOUR_USERNAME/Documents/Docker_Projects/KVM_MCP/kvm_mcp/server.py"],
      "env": {
        "PYTHONPATH": "/home/YOUR_USERNAME/Documents/Docker_Projects/KVM_MCP",
        "KVM_MCP_LIBVIRT_URI": "qemu:///system",
        "KVM_MCP_DISK_PATH": "/var/lib/libvirt/images",
        "KVM_MCP_ISO_PATH": "/path/to/your/iso/directory",
        "KVM_MCP_DEFAULT_NETWORK": "default"
      }
    }
  }
}
```

> 📝 **Important Notes:**
> - Replace `YOUR_USERNAME` with your actual username
> - Replace `/path/to/your/iso/directory` with where you keep your ISO files
> - We use `PYTHONPATH` instead of `cwd` because Claude Desktop on Linux doesn't reliably honor the `cwd` field
> - The server runs as a direct Python script (not `-m module`) for maximum compatibility

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KVM_MCP_LIBVIRT_URI` | `qemu:///system` | Libvirt connection URI |
| `KVM_MCP_DISK_PATH` | `/var/lib/libvirt/images` | Default disk image directory |
| `KVM_MCP_ISO_PATH` | `/var/lib/libvirt/images` | ISO image search directory |
| `KVM_MCP_DEFAULT_NETWORK` | `default` | Default network for new VMs |
| `KVM_MCP_DEFAULT_MEMORY` | `2048` | Default RAM in MB |
| `KVM_MCP_DEFAULT_VCPUS` | `2` | Default vCPU count |
| `KVM_MCP_DEFAULT_DISK_SIZE` | `40` | Default disk size in GB |

### Restart Claude Desktop

Close and reopen Claude Desktop. The KVM tools should now appear in the tools list.

---

## Part 4: Lessons Learned (The Hard Part)

This section documents the issues we hit and how we solved them — so you don't have to.

### Lesson 1: Module Discovery vs Direct Script Execution

**Problem:** Using `-m kvm_mcp.server` in the args resulted in `ModuleNotFoundError: No module named 'kvm_mcp'` even with `cwd` set correctly.

**Why:** Claude Desktop on Linux doesn't reliably honor the `cwd` (current working directory) config field. Python's `-m` flag requires the module to be findable in `sys.path`, which depends on the working directory.

**Solution:** Use the direct script path in `args` and set `PYTHONPATH` in the environment:
```json
"args": ["/full/path/to/kvm_mcp/server.py"],
"env": {
    "PYTHONPATH": "/full/path/to/project/root"
}
```

### Lesson 2: FastMCP Lifespan Context Injection

**Problem:** Tools crashed with `'NoneType' object has no attribute 'request_context'` when trying to access the libvirt connection from the lifespan context.

**Why:** FastMCP requires the `Context` type annotation to inject the context object. Using `ctx=None` as a default parameter means FastMCP never injects anything.

**Solution:** Import and type-hint `Context` properly:
```python
from mcp.server.fastmcp import FastMCP, Context

@mcp.tool()
async def my_tool(ctx: Context) -> str:  # NOT ctx=None
    ...
```

### Lesson 3: Lifespan State Attribute Paths

**Problem:** Even with proper `Context` injection, accessing `ctx.request_context.lifespan_state["conn"]` threw `AttributeError: 'RequestContext' object has no attribute 'lifespan_state'`.

**Why:** Different versions of the MCP SDK use different attribute paths for accessing lifespan state.

**Solution:** Store the connection as a module-level global during lifespan startup, bypassing the SDK attribute path entirely:
```python
_libvirt_conn = None

@asynccontextmanager
async def app_lifespan(app):
    global _libvirt_conn
    conn = libvirt.open(LIBVIRT_URI)
    _libvirt_conn = conn
    yield {"conn": conn}
    _libvirt_conn = None
    conn.close()

def _get_conn(ctx: Context):
    if _libvirt_conn is not None:
        return _libvirt_conn
    raise RuntimeError("Libvirt connection not initialized")
```

### Lesson 4: Lifespan Function Signature

**Problem:** Server crashed with `TypeError: app_lifespan() takes 0 positional arguments but 1 was given`.

**Why:** FastMCP passes the app instance as the first argument to the lifespan function.

**Solution:** Accept the `app` parameter:
```python
@asynccontextmanager
async def app_lifespan(app):  # NOT app_lifespan()
    ...
```

### Lesson 5: Native Python, Not Docker

**Problem:** Unlike our other MCP integrations (Wazuh, Burp Suite, LitterBox), we couldn't containerize this server easily.

**Why:** The server needs direct access to:
- libvirt's Unix socket (`/var/run/libvirt/libvirt-sock`)
- System tools (`virt-install`, `virt-clone`, `virsh`)
- Host networking for bridge enumeration
- Disk images and ISOs on the host filesystem

**Solution:** Run natively in a Python virtual environment. This is actually simpler than Docker for this use case — no volume mounts, no device passthrough, no privileged containers.

---

## Part 5: Usage Examples

Once connected, here are some things you can do:

### List Your Lab

> "Show me all my virtual machines"

Claude returns a formatted table with VM names, states, memory, CPUs, networks, and IPs.

### Build a Pentest Lab Network

> "Create an isolated network called pentest_lab on subnet 10.10.10.0/24 with DHCP"

Claude creates the network using libvirt's XML API.

### Spin Up a VM from ISO

> "Create a new Kali VM called kali_engagement with 4GB RAM, 4 CPUs, booting from my kali ISO on the pentest_lab network"

Claude finds the ISO, runs virt-install with the right parameters.

### Clone a Template

> "Clone win10_Template as win10_target"

Claude uses virt-clone to create a full copy with new UUID and MAC addresses.

### Snapshot Before Exploitation

> "Snapshot win10_target as pre_exploit"

Claude creates a snapshot capturing the full VM state.

### Revert After Testing

> "Revert win10_target to the pre_exploit snapshot"

Claude reverts the VM to its clean state instantly.

### Network Segmentation

> "Attach the pentest_lab network to kali_engagement and win10_target"

Claude hot-plugs NICs onto both VMs.

### Full Lab Teardown

> "Stop all VMs on the pentest_lab network, delete the snapshots, and remove the network"

Claude orchestrates the entire teardown sequence.

---

## Part 6: Available Tools Reference

### VM Lifecycle (5 tools)
| Tool | Description | Destructive |
|------|-------------|-------------|
| `kvm_list_vms` | List all VMs with state, resources, networks, IPs | No |
| `kvm_vm_info` | Detailed info for a specific VM | No |
| `kvm_start_vm` | Start a shutoff VM | No |
| `kvm_stop_vm` | Graceful ACPI shutdown or force power-off | Yes |
| `kvm_reboot_vm` | Reboot a running VM via ACPI | No |

### VM Creation & Deletion (3 tools)
| Tool | Description | Destructive |
|------|-------------|-------------|
| `kvm_create_vm` | Create new VM from ISO with full customization | No |
| `kvm_clone_vm` | Clone existing VM (must be shutoff) | No |
| `kvm_delete_vm` | Delete VM with optional disk removal | Yes |

### Network Management (7 tools)
| Tool | Description | Destructive |
|------|-------------|-------------|
| `kvm_list_networks` | List all libvirt networks and host bridges | No |
| `kvm_network_info` | Detailed network info with XML definition | No |
| `kvm_create_network` | Create isolated, NAT, or routed network | No |
| `kvm_start_network` | Start an inactive network | No |
| `kvm_stop_network` | Stop an active network | Yes |
| `kvm_delete_network` | Delete a network (must be stopped) | Yes |
| `kvm_attach_network` | Hot-plug a NIC onto a VM | No |
| `kvm_detach_network` | Remove a NIC by MAC address | Yes |

### Snapshot Management (4 tools)
| Tool | Description | Destructive |
|------|-------------|-------------|
| `kvm_list_snapshots` | List all snapshots for a VM | No |
| `kvm_create_snapshot` | Create disk+memory snapshot | No |
| `kvm_revert_snapshot` | Revert to a previous snapshot | Yes |
| `kvm_delete_snapshot` | Delete a snapshot | Yes |

### Utility (2 tools)
| Tool | Description | Destructive |
|------|-------------|-------------|
| `kvm_list_isos` | Discover available ISO images | No |
| `kvm_list_os_variants` | List valid OS variants for virt-install | No |

---

## Troubleshooting

### "Cannot connect to libvirt"

```bash
# Check libvirtd is running
sudo systemctl status libvirtd

# Check your user is in the libvirt group
groups | grep libvirt

# Test connection manually
virsh -c qemu:///system list --all
```

### "Permission denied" errors

```bash
sudo usermod -aG libvirt $USER
# Log out and back in
```

### "virt-install not found"

```bash
sudo apt install virtinst
```

### "ModuleNotFoundError: No module named 'kvm_mcp'"

Make sure you're using the direct script path with PYTHONPATH, not `-m kvm_mcp.server`. See Lesson 1 above.

### Server crashes with Context/lifespan errors

Make sure all tool functions use `ctx: Context` (not `ctx=None`). See Lessons 2 and 3 above.

### Networks not showing

```bash
# List libvirt networks
virsh net-list --all

# Start the default network if inactive
virsh net-start default
virsh net-autostart default
```

---

## Why This Matters for Cybersecurity

Virtual machine management is the backbone of every pentest lab, training environment, and malware analysis sandbox. Being able to:

- **Spin up isolated networks** with a sentence instead of clicking through virt-manager
- **Clone templates** to rapidly deploy target environments
- **Snapshot before exploitation** and revert in seconds
- **Orchestrate entire lab environments** through natural conversation

...turns what used to be 15-30 minutes of GUI clicking into a 30-second conversation. When you're running multiple engagements or studying for certifications, that time adds up.

Combined with our other MCP integrations (Wazuh for SIEM, BloodHound for AD analysis, Burp Suite for web testing, SysReptor for reporting), this creates a fully AI-orchestrated pentest workflow from infrastructure to deliverables.

---

## Connect With Me

- 🐦 Twitter/X: [@hackerobi](https://twitter.com/hackerobi)
- 💼 LinkedIn: [Hackerobi](https://linkedin.com/in/hackerobi)
- 🎮 CTFtime: [Hackerobi](https://ctftime.org/user/hackerobi)

Have questions? Found a bug? Want to share your own setup? **Open an issue or submit a PR!**

---

## Acknowledgments

Special thanks to:
- The **libvirt** team for building the industry-standard virtualization API
- The **QEMU** project for incredible open-source hardware emulation
- **steveydevey** for the [kvm-mcp](https://github.com/steveydevey/kvm-mcp) reference implementation that inspired this project's direction
- **Anthropic** for Claude and the Model Context Protocol
- The **MCP Python SDK** team for FastMCP
- The **cybersecurity community** for always being willing to help and share
- **You** for taking the time to check out this project

---

*Happy hacking, stay curious, and never stop learning!* 🛡️

**— Hackerobi**
