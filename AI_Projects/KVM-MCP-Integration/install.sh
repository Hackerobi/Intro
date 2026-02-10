#!/bin/bash
# KVM MCP Server - Installation Script for Pop!_OS / Ubuntu / Debian
# Run this from the KVM-MCP-Integration directory

set -e

echo "╔══════════════════════════════════════════════╗"
echo "║        KVM MCP Server - Setup Script         ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Check prerequisites
echo "[1/6] Checking prerequisites..."

if ! command -v virsh &> /dev/null; then
    echo "  ❌ libvirt/virsh not found. Installing..."
    sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virt-manager
else
    echo "  ✅ libvirt/virsh found"
fi

if ! command -v virt-install &> /dev/null; then
    echo "  ❌ virt-install not found. Installing..."
    sudo apt install -y virtinst
else
    echo "  ✅ virt-install found"
fi

if ! command -v python3 &> /dev/null; then
    echo "  ❌ Python 3 not found!"
    exit 1
else
    echo "  ✅ Python $(python3 --version | cut -d' ' -f2) found"
fi

if ! groups | grep -q libvirt; then
    echo "  ⚠️  Adding user to libvirt group..."
    sudo usermod -aG libvirt $USER
    echo "  ⚠️  You may need to log out and back in for group changes to take effect."
fi

if ! systemctl is-active --quiet libvirtd; then
    echo "  ⚠️  Starting libvirtd..."
    sudo systemctl enable --now libvirtd
fi

echo ""
echo "[2/6] Checking libvirt-dev headers for libvirt-python..."
if ! dpkg -l | grep -q libvirt-dev; then
    echo "  Installing libvirt-dev..."
    sudo apt install -y libvirt-dev pkg-config python3-dev
else
    echo "  ✅ libvirt-dev found"
fi

echo ""
echo "[3/6] Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "  ✅ Virtual environment created"
else
    echo "  ✅ Virtual environment already exists"
fi

echo ""
echo "[4/6] Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "  ✅ Dependencies installed"

echo ""
echo "[5/6] Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ✅ Created .env from template (edit as needed)"
else
    echo "  ✅ .env already exists"
fi

echo ""
echo "[6/6] Testing libvirt connection..."
python3 -c "
import libvirt
conn = libvirt.open('qemu:///system')
if conn:
    domains = conn.listAllDomains(0)
    print(f'  ✅ Connected to libvirt - {len(domains)} VMs found')
    conn.close()
else:
    print('  ❌ Failed to connect to libvirt')
    exit(1)
"

INSTALL_DIR=$(pwd)
VENV_PYTHON="${INSTALL_DIR}/.venv/bin/python"
SERVER_SCRIPT="${INSTALL_DIR}/kvm_mcp/server.py"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║           Setup Complete! 🎉                 ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "📁 Server location: ${INSTALL_DIR}"
echo "🐍 Virtual env: ${INSTALL_DIR}/.venv"
echo ""
echo "To test the server manually:"
echo "  PYTHONPATH=${INSTALL_DIR} ${VENV_PYTHON} ${SERVER_SCRIPT}"
echo ""
echo "Add this to your Claude Desktop config (~/.config/Claude/claude_desktop_config.json):"
echo ""
cat << EOF
{
  "mcpServers": {
    "kvm": {
      "command": "${VENV_PYTHON}",
      "args": ["${SERVER_SCRIPT}"],
      "env": {
        "PYTHONPATH": "${INSTALL_DIR}",
        "KVM_MCP_LIBVIRT_URI": "qemu:///system",
        "KVM_MCP_DISK_PATH": "/var/lib/libvirt/images",
        "KVM_MCP_ISO_PATH": "/var/lib/libvirt/images",
        "KVM_MCP_DEFAULT_NETWORK": "default"
      }
    }
  }
}
EOF
echo ""
