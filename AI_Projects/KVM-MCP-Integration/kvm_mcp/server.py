#!/usr/bin/env python3
"""
KVM MCP Server - Manage KVM/QEMU virtual machines through Claude Desktop.

A comprehensive MCP server for libvirt/QEMU/KVM VM management including:
- VM lifecycle (list, start, stop, reboot, delete)
- VM creation from ISO or existing disk images
- Network management (list, create, assign networks)
- Snapshot management (create, list, revert, delete)

Designed for Pop!_OS with virt-manager 4.0.0 / QEMU/KVM.
"""

import json
import logging
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import libvirt
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Logging (stderr only — stdout is reserved for MCP stdio transport)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("kvm_mcp")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LIBVIRT_URI = os.environ.get("KVM_MCP_LIBVIRT_URI", "qemu:///system")
DEFAULT_DISK_PATH = os.environ.get("KVM_MCP_DISK_PATH", "/var/lib/libvirt/images")
DEFAULT_ISO_PATH = os.environ.get("KVM_MCP_ISO_PATH", "/var/lib/libvirt/images")
DEFAULT_NETWORK = os.environ.get("KVM_MCP_DEFAULT_NETWORK", "default")
DEFAULT_MEMORY_MB = int(os.environ.get("KVM_MCP_DEFAULT_MEMORY", "2048"))
DEFAULT_VCPUS = int(os.environ.get("KVM_MCP_DEFAULT_VCPUS", "2"))
DEFAULT_DISK_SIZE_GB = int(os.environ.get("KVM_MCP_DEFAULT_DISK_SIZE", "40"))

# ---------------------------------------------------------------------------
# Module-level libvirt connection (set during lifespan)
# ---------------------------------------------------------------------------
_libvirt_conn = None

# ---------------------------------------------------------------------------
# Lifespan — open / close a single libvirt connection
# ---------------------------------------------------------------------------

@asynccontextmanager
async def app_lifespan(app):
    """Manage libvirt connection for the lifetime of the server."""
    global _libvirt_conn
    logger.info("Connecting to libvirt at %s …", LIBVIRT_URI)
    conn = libvirt.open(LIBVIRT_URI)
    if conn is None:
        logger.error("Failed to connect to libvirt")
        raise RuntimeError(f"Cannot connect to libvirt at {LIBVIRT_URI}")
    logger.info("Connected to libvirt — hypervisor version %s", conn.getVersion())
    _libvirt_conn = conn
    yield {"conn": conn}
    _libvirt_conn = None
    conn.close()
    logger.info("Libvirt connection closed.")


mcp = FastMCP("kvm_mcp", lifespan=app_lifespan)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_conn(ctx: Context) -> libvirt.virConnect:
    """Retrieve the shared libvirt connection."""
    global _libvirt_conn
    if _libvirt_conn is not None:
        return _libvirt_conn
    raise RuntimeError("Libvirt connection not initialized")


def _domain_state_str(state: int) -> str:
    """Convert libvirt domain state integer to human-readable string."""
    return {
        libvirt.VIR_DOMAIN_NOSTATE: "no state",
        libvirt.VIR_DOMAIN_RUNNING: "running",
        libvirt.VIR_DOMAIN_BLOCKED: "blocked",
        libvirt.VIR_DOMAIN_PAUSED: "paused",
        libvirt.VIR_DOMAIN_SHUTDOWN: "shutting down",
        libvirt.VIR_DOMAIN_SHUTOFF: "shutoff",
        libvirt.VIR_DOMAIN_CRASHED: "crashed",
        libvirt.VIR_DOMAIN_PMSUSPENDED: "suspended",
    }.get(state, "unknown")


def _domain_info(domain: libvirt.virDomain) -> Dict[str, Any]:
    """Build a standard info dict for a domain."""
    state, max_mem, mem, vcpus, cpu_time = domain.info()
    # Gather network interfaces from XML
    networks = []
    try:
        xml = ET.fromstring(domain.XMLDesc(0))
        for iface in xml.findall(".//interface"):
            iface_info: Dict[str, Any] = {"type": iface.get("type")}
            src = iface.find("source")
            if src is not None:
                iface_info["source"] = src.get("network") or src.get("bridge") or src.get("dev")
            mac = iface.find("mac")
            if mac is not None:
                iface_info["mac"] = mac.get("address")
            networks.append(iface_info)
    except Exception:
        pass

    # Try to get IP addresses for running VMs
    ip_addresses = []
    if state == libvirt.VIR_DOMAIN_RUNNING:
        try:
            ifaces = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)
            for name, info in ifaces.items():
                for addr in info.get("addrs", []):
                    ip_addresses.append(f"{addr['addr']}/{addr['prefix']}")
        except Exception:
            # Fallback: try agent or ARP
            try:
                ifaces = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_ARP)
                for name, info in ifaces.items():
                    for addr in info.get("addrs", []):
                        ip_addresses.append(f"{addr['addr']}/{addr['prefix']}")
            except Exception:
                pass

    return {
        "name": domain.name(),
        "uuid": domain.UUIDString(),
        "id": domain.ID() if domain.isActive() else None,
        "state": _domain_state_str(state),
        "memory_mb": mem // 1024,
        "max_memory_mb": max_mem // 1024,
        "vcpus": vcpus,
        "autostart": bool(domain.autostart()),
        "persistent": bool(domain.isPersistent()),
        "networks": networks,
        "ip_addresses": ip_addresses,
    }


def _network_info(net: libvirt.virNetwork) -> Dict[str, Any]:
    """Build an info dict for a libvirt network."""
    info: Dict[str, Any] = {
        "name": net.name(),
        "uuid": net.UUIDString(),
        "active": net.isActive(),
        "autostart": net.autostart(),
        "persistent": net.isPersistent(),
        "bridge_name": None,
        "forward_mode": None,
        "ip_range": None,
        "dhcp_range": None,
    }
    try:
        xml = ET.fromstring(net.XMLDesc(0))
        bridge = xml.find("bridge")
        if bridge is not None:
            info["bridge_name"] = bridge.get("name")
        forward = xml.find("forward")
        if forward is not None:
            info["forward_mode"] = forward.get("mode")
        ip_elem = xml.find("ip")
        if ip_elem is not None:
            addr = ip_elem.get("address")
            netmask = ip_elem.get("netmask")
            prefix = ip_elem.get("prefix")
            if addr:
                info["ip_range"] = f"{addr}/{prefix}" if prefix else f"{addr}/{netmask}"
            dhcp = ip_elem.find("dhcp/range")
            if dhcp is not None:
                info["dhcp_range"] = f"{dhcp.get('start')} - {dhcp.get('end')}"
    except Exception:
        pass
    return info


def _format_table(headers: List[str], rows: List[List[str]]) -> str:
    """Simple Markdown table formatter."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    header_line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    data_lines = []
    for row in rows:
        data_lines.append("| " + " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) + " |")
    return "\n".join([header_line, sep_line] + data_lines)


def _xml_name_element(value: str) -> str:
    """Build an XML name element without the tag being stripped."""
    tag = chr(60) + "name" + chr(62)
    end = chr(60) + "/name" + chr(62)
    return f"  {tag}{value}{end}"


# ===================================================================
# TOOL INPUT MODELS
# ===================================================================

class VMNameInput(BaseModel):
    """Input requiring a VM name."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    vm_name: str = Field(..., description="Name of the virtual machine", min_length=1, max_length=200)


class StopVMInput(BaseModel):
    """Input for stopping a VM."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    vm_name: str = Field(..., description="Name of the virtual machine", min_length=1, max_length=200)
    force: bool = Field(default=False, description="Force power off (destroy) instead of graceful ACPI shutdown")


class CreateVMInput(BaseModel):
    """Input for creating a new VM."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Name for the new VM (e.g., 'win11_Pentest', 'kali_lab')", min_length=1, max_length=200)
    memory_mb: int = Field(default=DEFAULT_MEMORY_MB, description="RAM in MB", ge=256, le=1048576)
    vcpus: int = Field(default=DEFAULT_VCPUS, description="Number of virtual CPUs", ge=1, le=128)
    disk_size_gb: int = Field(default=DEFAULT_DISK_SIZE_GB, description="Disk size in GB", ge=1, le=10000)
    iso_path: Optional[str] = Field(default=None, description="Full path to ISO for installation")
    disk_path: Optional[str] = Field(default=None, description="Custom path for the VM disk image")
    os_variant: str = Field(default="generic", description="OS variant for virt-install (e.g., 'win11', 'win10', 'debian12', 'ubuntu24.04')")
    network: str = Field(default=DEFAULT_NETWORK, description="Libvirt network name or bridge name")
    network_type: str = Field(default="network", description="'network' for libvirt networks, 'bridge' for host bridges")
    boot: str = Field(default="cdrom", description="Boot device: 'cdrom' or 'hd'")
    graphics: str = Field(default="vnc", description="Graphics type: 'vnc', 'spice', or 'none'")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        invalid = set('!@#$%^&*()+={}[]|\\:;"\'<>?/ ')
        if any(c in invalid for c in v):
            raise ValueError("VM name contains invalid characters. Use alphanumeric, hyphens, and underscores only.")
        return v


class CloneVMInput(BaseModel):
    """Input for cloning an existing VM."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    source_vm: str = Field(..., description="Name of the source VM to clone (must be shutoff)")
    new_name: str = Field(..., description="Name for the cloned VM")

    @field_validator("new_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        invalid = set('!@#$%^&*()+={}[]|\\:;"\'<>?/ ')
        if any(c in invalid for c in v):
            raise ValueError("VM name contains invalid characters.")
        return v


class DeleteVMInput(BaseModel):
    """Input for deleting a VM."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    vm_name: str = Field(..., description="Name of the virtual machine to delete")
    remove_storage: bool = Field(default=False, description="Also delete associated disk images")


class NetworkNameInput(BaseModel):
    """Input requiring a network name."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    network_name: str = Field(..., description="Name of the libvirt network")


class CreateNetworkInput(BaseModel):
    """Input for creating a new isolated libvirt network."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Network name (e.g., 'pentest_lab', 'ad_network')", min_length=1, max_length=100)
    subnet: str = Field(..., description="Subnet in CIDR notation (e.g., '10.10.10.0/24')")
    dhcp: bool = Field(default=True, description="Enable DHCP on this network")
    dhcp_start: Optional[str] = Field(default=None, description="DHCP range start. Auto-calculated if not set.")
    dhcp_end: Optional[str] = Field(default=None, description="DHCP range end. Auto-calculated if not set.")
    forward_mode: Optional[str] = Field(default=None, description="Forward mode: 'nat', 'route', 'bridge', or None for isolated")
    autostart: bool = Field(default=True, description="Auto-start the network on host boot")


class AttachNetworkInput(BaseModel):
    """Input for attaching a network interface to a VM."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    vm_name: str = Field(..., description="Name of the virtual machine")
    network: str = Field(..., description="Network or bridge name to attach")
    network_type: str = Field(default="network", description="'network' for libvirt networks, 'bridge' for host bridges")
    model: str = Field(default="virtio", description="NIC model: 'virtio', 'e1000', 'rtl8139'")


class DetachNetworkInput(BaseModel):
    """Input for detaching a network interface from a VM."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    vm_name: str = Field(..., description="Name of the virtual machine")
    mac_address: str = Field(..., description="MAC address of the interface to detach")


class SnapshotCreateInput(BaseModel):
    """Input for creating a VM snapshot."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    vm_name: str = Field(..., description="Name of the virtual machine")
    snapshot_name: str = Field(..., description="Name for the snapshot (e.g., 'pre_exploit', 'clean_state')")
    description: Optional[str] = Field(default=None, description="Optional description for the snapshot")


class SnapshotInput(BaseModel):
    """Input for snapshot operations (revert/delete)."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    vm_name: str = Field(..., description="Name of the virtual machine")
    snapshot_name: str = Field(..., description="Name of the snapshot")


# ===================================================================
# TOOLS — VM LIFECYCLE
# ===================================================================

@mcp.tool(
    name="kvm_list_vms",
    annotations={
        "title": "List Virtual Machines",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_list_vms(ctx: Context) -> str:
    """List all KVM/QEMU virtual machines with their state, resources, networks, and IP addresses."""
    conn = _get_conn(ctx)
    domains = conn.listAllDomains(0)
    if not domains:
        return "No virtual machines found."

    results = []
    for domain in domains:
        try:
            results.append(_domain_info(domain))
        except libvirt.libvirtError as e:
            logger.error("Error reading domain %s: %s", domain.name(), e)

    lines = [f"## Virtual Machines ({len(results)} total)\n"]
    headers = ["Name", "State", "RAM (MB)", "vCPUs", "Networks", "IPs", "Autostart"]
    rows = []
    for vm in results:
        net_str = ", ".join(n.get("source", "?") for n in vm["networks"]) or "none"
        ip_str = ", ".join(vm["ip_addresses"]) or "-"
        rows.append([
            vm["name"], vm["state"], str(vm["memory_mb"]), str(vm["vcpus"]),
            net_str, ip_str, "yes" if vm["autostart"] else "no",
        ])
    lines.append(_format_table(headers, rows))
    return "\n".join(lines)


@mcp.tool(
    name="kvm_vm_info",
    annotations={
        "title": "Get VM Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_vm_info(params: VMNameInput, ctx: Context) -> str:
    """Get detailed information about a specific virtual machine."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."
    info = _domain_info(domain)
    return json.dumps(info, indent=2)


@mcp.tool(
    name="kvm_start_vm",
    annotations={
        "title": "Start Virtual Machine",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_start_vm(params: VMNameInput, ctx: Context) -> str:
    """Start a shutoff virtual machine."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."
    if domain.isActive():
        return f"VM '{params.vm_name}' is already running."
    try:
        domain.create()
        return f"VM '{params.vm_name}' started successfully."
    except libvirt.libvirtError as e:
        return f"Error starting VM: {e}"


@mcp.tool(
    name="kvm_stop_vm",
    annotations={
        "title": "Stop Virtual Machine",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_stop_vm(params: StopVMInput, ctx: Context) -> str:
    """Stop a running virtual machine. Graceful ACPI shutdown by default, or force power off."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."
    if not domain.isActive():
        return f"VM '{params.vm_name}' is already stopped."
    try:
        if params.force:
            domain.destroy()
            return f"VM '{params.vm_name}' force powered off."
        else:
            domain.shutdown()
            return f"VM '{params.vm_name}' graceful shutdown initiated."
    except libvirt.libvirtError as e:
        return f"Error stopping VM: {e}"


@mcp.tool(
    name="kvm_reboot_vm",
    annotations={
        "title": "Reboot Virtual Machine",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_reboot_vm(params: VMNameInput, ctx: Context) -> str:
    """Reboot a running virtual machine via ACPI signal."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."
    if not domain.isActive():
        return f"Error: VM '{params.vm_name}' is not running."
    try:
        domain.reboot(0)
        return f"VM '{params.vm_name}' reboot initiated."
    except libvirt.libvirtError as e:
        return f"Error rebooting VM: {e}"


# ===================================================================
# TOOLS — VM CREATION & DELETION
# ===================================================================

@mcp.tool(
    name="kvm_create_vm",
    annotations={
        "title": "Create Virtual Machine",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_create_vm(params: CreateVMInput, ctx: Context) -> str:
    """Create a new KVM virtual machine using virt-install.

    Common os_variant values:
    - Windows: win11, win10, win2k22, win2k19
    - Linux: debian12, ubuntu24.04, fedora40, centos-stream9, kali-rolling
    - Generic: generic
    """
    disk_path = params.disk_path or os.path.join(DEFAULT_DISK_PATH, f"{params.name}.qcow2")
    if os.path.exists(disk_path):
        return f"Error: Disk image already exists at {disk_path}."

    cmd = [
        "virt-install",
        f"--connect={LIBVIRT_URI}",
        f"--name={params.name}",
        f"--memory={params.memory_mb}",
        f"--vcpus={params.vcpus}",
        f"--os-variant={params.os_variant}",
        f"--disk=path={disk_path},size={params.disk_size_gb},format=qcow2,bus=virtio",
        f"--graphics={params.graphics},listen=0.0.0.0",
        "--noautoconsole",
    ]

    if params.network_type == "bridge":
        cmd.append(f"--network=bridge={params.network},model=virtio")
    else:
        cmd.append(f"--network=network={params.network},model=virtio")

    if params.iso_path:
        if not os.path.exists(params.iso_path):
            return f"Error: ISO file not found at {params.iso_path}"
        cmd.append(f"--cdrom={params.iso_path}")
    else:
        cmd.append("--boot=hd")
        cmd.append("--import")

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        return f"Error creating VM:\n```\n{result.stderr.strip()}\n```\nCommand: {' '.join(cmd)}"

    return (
        f"VM '{params.name}' created successfully!\n\n"
        f"- **Disk**: {disk_path} ({params.disk_size_gb} GB)\n"
        f"- **RAM**: {params.memory_mb} MB\n"
        f"- **vCPUs**: {params.vcpus}\n"
        f"- **Network**: {params.network} ({params.network_type})\n"
        f"- **OS variant**: {params.os_variant}\n"
        f"- **Graphics**: {params.graphics}\n"
        f"{'- **ISO**: ' + params.iso_path if params.iso_path else '- Boot from disk'}\n\n"
        f"Use `kvm_list_vms` to verify, or connect via virt-manager/VNC."
    )


@mcp.tool(
    name="kvm_clone_vm",
    annotations={
        "title": "Clone Virtual Machine",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_clone_vm(params: CloneVMInput, ctx: Context) -> str:
    """Clone an existing VM (must be shutoff). Creates a full copy with new name, UUID, and MAC addresses."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.source_vm)
    except libvirt.libvirtError:
        return f"Error: Source VM '{params.source_vm}' not found."
    if domain.isActive():
        return f"Error: Source VM '{params.source_vm}' must be shutoff before cloning."

    cmd = [
        "virt-clone",
        f"--connect={LIBVIRT_URI}",
        f"--original={params.source_vm}",
        f"--name={params.new_name}",
        "--auto-clone",
    ]

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        return f"Error cloning VM:\n```\n{result.stderr.strip()}\n```"

    return f"VM '{params.source_vm}' cloned as '{params.new_name}' successfully.\n\nUse `kvm_list_vms` to see the new VM."


@mcp.tool(
    name="kvm_delete_vm",
    annotations={
        "title": "Delete Virtual Machine",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_delete_vm(params: DeleteVMInput, ctx: Context) -> str:
    """Delete (undefine) a virtual machine. Optionally remove its disk storage. Irreversible!"""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."
    if domain.isActive():
        return f"Error: VM '{params.vm_name}' is still running. Stop it first."

    try:
        if params.remove_storage:
            xml = ET.fromstring(domain.XMLDesc(0))
            disks = []
            for disk in xml.findall(".//disk[@device='disk']/source"):
                path = disk.get("file")
                if path:
                    disks.append(path)

            flags = libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE | libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA
            try:
                flags |= libvirt.VIR_DOMAIN_UNDEFINE_NVRAM
            except AttributeError:
                pass
            domain.undefineFlags(flags)

            removed = []
            for path in disks:
                try:
                    os.remove(path)
                    removed.append(path)
                except OSError as e:
                    logger.warning("Could not remove disk %s: %s", path, e)

            return f"VM '{params.vm_name}' deleted. Removed disks: {', '.join(removed) or 'none'}"
        else:
            domain.undefine()
            return f"VM '{params.vm_name}' undefined (disk images preserved)."
    except libvirt.libvirtError as e:
        return f"Error deleting VM: {e}"


# ===================================================================
# TOOLS — NETWORK MANAGEMENT
# ===================================================================

@mcp.tool(
    name="kvm_list_networks",
    annotations={
        "title": "List Libvirt Networks",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_list_networks(ctx: Context) -> str:
    """List all libvirt virtual networks and host bridge interfaces."""
    conn = _get_conn(ctx)
    networks = conn.listAllNetworks(0)

    lines = ["## Libvirt Virtual Networks\n"]
    if not networks:
        lines.append("No libvirt networks found.\n")
    else:
        headers = ["Name", "Active", "Autostart", "Mode", "Bridge", "Subnet", "DHCP Range"]
        rows = []
        for net in networks:
            info = _network_info(net)
            rows.append([
                info["name"],
                "yes" if info["active"] else "no",
                "yes" if info["autostart"] else "no",
                info["forward_mode"] or "isolated",
                info["bridge_name"] or "-",
                info["ip_range"] or "-",
                info["dhcp_range"] or "-",
            ])
        lines.append(_format_table(headers, rows))

    lines.append("\n\n## Host Bridge Interfaces\n")
    try:
        result = subprocess.run(
            ["ip", "-j", "link", "show", "type", "bridge"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            bridges = json.loads(result.stdout)
            br_headers = ["Name", "State", "MAC"]
            br_rows = [[br.get("ifname", "?"), br.get("operstate", "?"), br.get("address", "?")] for br in bridges]
            if br_rows:
                lines.append(_format_table(br_headers, br_rows))
            else:
                lines.append("No host bridges found.")
        else:
            lines.append("Could not enumerate host bridges.")
    except Exception:
        lines.append("Could not enumerate host bridges.")

    return "\n".join(lines)


@mcp.tool(
    name="kvm_network_info",
    annotations={
        "title": "Get Network Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_network_info(params: NetworkNameInput, ctx: Context) -> str:
    """Get detailed information about a specific libvirt network including its full XML definition."""
    conn = _get_conn(ctx)
    try:
        net = conn.networkLookupByName(params.network_name)
    except libvirt.libvirtError:
        return f"Error: Network '{params.network_name}' not found."
    info = _network_info(net)
    info["xml"] = net.XMLDesc(0)
    return json.dumps(info, indent=2)


@mcp.tool(
    name="kvm_create_network",
    annotations={
        "title": "Create Libvirt Network",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_create_network(params: CreateNetworkInput, ctx: Context) -> str:
    """Create a new libvirt virtual network (isolated, NAT, or routed)."""
    conn = _get_conn(ctx)
    try:
        conn.networkLookupByName(params.name)
        return f"Error: Network '{params.name}' already exists."
    except libvirt.libvirtError:
        pass

    try:
        import ipaddress
        network = ipaddress.IPv4Network(params.subnet, strict=False)
        gateway = str(list(network.hosts())[0])
        netmask = str(network.netmask)
        if params.dhcp:
            hosts = list(network.hosts())
            dhcp_start = params.dhcp_start or str(hosts[max(1, len(hosts) // 4)])
            dhcp_end = params.dhcp_end or str(hosts[-1])
        else:
            dhcp_start = dhcp_end = None
    except Exception as e:
        return f"Error parsing subnet '{params.subnet}': {e}"

    name_tag = chr(60) + "name" + chr(62) + params.name + chr(60) + "/name" + chr(62)
    xml_parts = ["<network>", f"  {name_tag}"]
    if params.forward_mode:
        xml_parts.append(f'  <forward mode="{params.forward_mode}"/>')
    xml_parts.append(f'  <bridge name="virbr-{params.name[:8]}" stp="on" delay="0"/>')
    xml_parts.append(f'  <ip address="{gateway}" netmask="{netmask}">')
    if params.dhcp and dhcp_start and dhcp_end:
        xml_parts.append(f'    <dhcp>')
        xml_parts.append(f'      <range start="{dhcp_start}" end="{dhcp_end}"/>')
        xml_parts.append(f'    </dhcp>')
    xml_parts.append(f'  </ip>')
    xml_parts.append(f'</network>')
    xml_str = "\n".join(xml_parts)

    try:
        net = conn.networkDefineXML(xml_str)
        if params.autostart:
            net.setAutostart(True)
        net.create()
        return (
            f"Network '{params.name}' created and started!\n\n"
            f"- **Subnet**: {params.subnet}\n"
            f"- **Gateway**: {gateway}\n"
            f"- **Mode**: {params.forward_mode or 'isolated'}\n"
            f"- **DHCP**: {dhcp_start} - {dhcp_end}\n"
            f"- **Autostart**: {'yes' if params.autostart else 'no'}"
        )
    except libvirt.libvirtError as e:
        return f"Error creating network: {e}"


@mcp.tool(
    name="kvm_start_network",
    annotations={
        "title": "Start Network",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_start_network(params: NetworkNameInput, ctx: Context) -> str:
    """Start an inactive libvirt network."""
    conn = _get_conn(ctx)
    try:
        net = conn.networkLookupByName(params.network_name)
    except libvirt.libvirtError:
        return f"Error: Network '{params.network_name}' not found."
    if net.isActive():
        return f"Network '{params.network_name}' is already active."
    try:
        net.create()
        return f"Network '{params.network_name}' started."
    except libvirt.libvirtError as e:
        return f"Error starting network: {e}"


@mcp.tool(
    name="kvm_stop_network",
    annotations={
        "title": "Stop Network",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_stop_network(params: NetworkNameInput, ctx: Context) -> str:
    """Stop an active libvirt network. VMs using this network will lose connectivity."""
    conn = _get_conn(ctx)
    try:
        net = conn.networkLookupByName(params.network_name)
    except libvirt.libvirtError:
        return f"Error: Network '{params.network_name}' not found."
    if not net.isActive():
        return f"Network '{params.network_name}' is already stopped."
    try:
        net.destroy()
        return f"Network '{params.network_name}' stopped."
    except libvirt.libvirtError as e:
        return f"Error stopping network: {e}"


@mcp.tool(
    name="kvm_delete_network",
    annotations={
        "title": "Delete Network",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_delete_network(params: NetworkNameInput, ctx: Context) -> str:
    """Delete (undefine) a libvirt network. Must be stopped first."""
    conn = _get_conn(ctx)
    try:
        net = conn.networkLookupByName(params.network_name)
    except libvirt.libvirtError:
        return f"Error: Network '{params.network_name}' not found."
    if net.isActive():
        return f"Error: Network '{params.network_name}' is still active. Stop it first."
    try:
        net.undefine()
        return f"Network '{params.network_name}' deleted."
    except libvirt.libvirtError as e:
        return f"Error deleting network: {e}"


@mcp.tool(
    name="kvm_attach_network",
    annotations={
        "title": "Attach Network Interface to VM",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_attach_network(params: AttachNetworkInput, ctx: Context) -> str:
    """Attach a new network interface to a VM. Works on both running and stopped VMs."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."

    if params.network_type == "bridge":
        iface_xml = f"""<interface type='bridge'>
  <source bridge='{params.network}'/>
  <model type='{params.model}'/>
</interface>"""
    else:
        iface_xml = f"""<interface type='network'>
  <source network='{params.network}'/>
  <model type='{params.model}'/>
</interface>"""

    try:
        flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
        if domain.isActive():
            flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE
        domain.attachDeviceFlags(iface_xml, flags)
        return f"Network interface ({params.network}) attached to VM '{params.vm_name}'."
    except libvirt.libvirtError as e:
        return f"Error attaching network: {e}"


@mcp.tool(
    name="kvm_detach_network",
    annotations={
        "title": "Detach Network Interface from VM",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_detach_network(params: DetachNetworkInput, ctx: Context) -> str:
    """Detach a network interface from a VM by its MAC address."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."

    xml = ET.fromstring(domain.XMLDesc(0))
    target_iface = None
    for iface in xml.findall(".//interface"):
        mac = iface.find("mac")
        if mac is not None and mac.get("address", "").lower() == params.mac_address.lower():
            target_iface = ET.tostring(iface, encoding="unicode")
            break

    if not target_iface:
        return f"Error: No interface with MAC address '{params.mac_address}' found on VM '{params.vm_name}'."

    try:
        flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
        if domain.isActive():
            flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE
        domain.detachDeviceFlags(target_iface, flags)
        return f"Interface with MAC {params.mac_address} detached from VM '{params.vm_name}'."
    except libvirt.libvirtError as e:
        return f"Error detaching network: {e}"


# ===================================================================
# TOOLS — SNAPSHOT MANAGEMENT
# ===================================================================

@mcp.tool(
    name="kvm_list_snapshots",
    annotations={
        "title": "List VM Snapshots",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_list_snapshots(params: VMNameInput, ctx: Context) -> str:
    """List all snapshots for a virtual machine."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."

    snapshots = domain.listAllSnapshots(0)
    if not snapshots:
        return f"No snapshots found for VM '{params.vm_name}'."

    lines = [f"## Snapshots for '{params.vm_name}' ({len(snapshots)} total)\n"]
    headers = ["Name", "Created", "State", "Description"]
    rows = []
    for snap in snapshots:
        try:
            xml = ET.fromstring(snap.getXMLDesc(0))
            name = xml.findtext("name", "?")
            desc = xml.findtext("description", "")
            creation_time = xml.findtext("creationTime", "")
            state = xml.findtext("state", "?")
            if creation_time:
                try:
                    creation_time = datetime.fromtimestamp(int(creation_time)).strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, OSError):
                    pass
            rows.append([name, creation_time, state, desc[:50]])
        except Exception:
            rows.append([snap.getName(), "?", "?", ""])
    lines.append(_format_table(headers, rows))
    return "\n".join(lines)


@mcp.tool(
    name="kvm_create_snapshot",
    annotations={
        "title": "Create VM Snapshot",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_create_snapshot(params: SnapshotCreateInput, ctx: Context) -> str:
    """Create a snapshot of a virtual machine. Works on both running and stopped VMs."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."

    desc = params.description or f"Snapshot created via KVM MCP on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    snap_name_el = _xml_name_element(params.snapshot_name).strip()
    snap_xml = f"""<domainsnapshot>
{snap_name_el}
</domainsnapshot>"""

    try:
        domain.snapshotCreateXML(snap_xml, 0)
        state = "running (disk+memory)" if domain.isActive() else "shutoff (disk only)"
        return (
            f"Snapshot '{params.snapshot_name}' created for VM '{params.vm_name}'.\n"
            f"- **VM state**: {state}\n"
            f"- **Description**: {desc}"
        )
    except libvirt.libvirtError as e:
        return f"Error creating snapshot: {e}"


@mcp.tool(
    name="kvm_revert_snapshot",
    annotations={
        "title": "Revert VM to Snapshot",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_revert_snapshot(params: SnapshotInput, ctx: Context) -> str:
    """Revert a virtual machine to a previous snapshot. The current state will be lost!"""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."
    try:
        snap = domain.snapshotLookupByName(params.snapshot_name, 0)
    except libvirt.libvirtError:
        return f"Error: Snapshot '{params.snapshot_name}' not found for VM '{params.vm_name}'."
    try:
        domain.revertToSnapshot(snap, 0)
        return f"VM '{params.vm_name}' reverted to snapshot '{params.snapshot_name}'."
    except libvirt.libvirtError as e:
        return f"Error reverting snapshot: {e}"


@mcp.tool(
    name="kvm_delete_snapshot",
    annotations={
        "title": "Delete VM Snapshot",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def kvm_delete_snapshot(params: SnapshotInput, ctx: Context) -> str:
    """Delete a snapshot from a virtual machine."""
    conn = _get_conn(ctx)
    try:
        domain = conn.lookupByName(params.vm_name)
    except libvirt.libvirtError:
        return f"Error: VM '{params.vm_name}' not found."
    try:
        snap = domain.snapshotLookupByName(params.snapshot_name, 0)
    except libvirt.libvirtError:
        return f"Error: Snapshot '{params.snapshot_name}' not found for VM '{params.vm_name}'."
    try:
        snap.delete(0)
        return f"Snapshot '{params.snapshot_name}' deleted from VM '{params.vm_name}'."
    except libvirt.libvirtError as e:
        return f"Error deleting snapshot: {e}"


# ===================================================================
# TOOLS — UTILITY
# ===================================================================

@mcp.tool(
    name="kvm_list_isos",
    annotations={
        "title": "List Available ISO Images",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_list_isos(ctx: Context) -> str:
    """List ISO images available in the configured ISO directory for VM installation."""
    search_paths = [DEFAULT_ISO_PATH, DEFAULT_DISK_PATH, "/var/lib/libvirt/images", "/iso"]
    seen = set()
    isos = []

    for base_path in search_paths:
        if not os.path.isdir(base_path):
            continue
        try:
            for entry in os.scandir(base_path):
                if entry.is_file() and entry.name.lower().endswith(".iso") and entry.path not in seen:
                    seen.add(entry.path)
                    stat = entry.stat()
                    isos.append({
                        "name": entry.name,
                        "path": entry.path,
                        "size_gb": round(stat.st_size / (1024**3), 2),
                    })
        except PermissionError:
            continue

    if not isos:
        return f"No ISO images found. Searched: {', '.join(search_paths)}"

    lines = [f"## Available ISO Images ({len(isos)} found)\n"]
    headers = ["Name", "Path", "Size (GB)"]
    rows = [[iso["name"], iso["path"], str(iso["size_gb"])] for iso in isos]
    lines.append(_format_table(headers, rows))
    return "\n".join(lines)


@mcp.tool(
    name="kvm_list_os_variants",
    annotations={
        "title": "List OS Variants",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def kvm_list_os_variants(ctx: Context) -> str:
    """List available OS variants for virt-install.

    Common variants: win11, win10, win2k22, win2k19, debian12, ubuntu24.04, fedora40, kali-rolling, generic.
    """
    try:
        result = subprocess.run(
            ["virt-install", "--os-variant", "list"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["osinfo-query", "os", "--fields=short-id,name"],
                capture_output=True, text=True, timeout=30
            )
        if result.returncode == 0:
            output = result.stdout.strip()
            lines = output.split("\n")
            if len(lines) > 100:
                return "\n".join(lines[:100]) + f"\n\n... ({len(lines) - 100} more variants.)"
            return output
        else:
            return "Could not list OS variants. Use 'generic' or common values like 'win11', 'debian12'."
    except FileNotFoundError:
        return "virt-install or osinfo-query not found. Use 'generic' for os_variant."


# ===================================================================
# ENTRYPOINT
# ===================================================================

if __name__ == "__main__":
    mcp.run()
