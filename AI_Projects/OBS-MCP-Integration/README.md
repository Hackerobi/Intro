# Controlling OBS Studio with Claude AI: A Complete Guide to the OBS MCP Server

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Beginner-Intermediate  
**Time Required:** 15-30 minutes

---

## Introduction

Imagine telling your AI assistant: *"Switch to my webcam scene and start recording"* and watching OBS Studio respond instantly. This guide will show you how to connect **OBS Studio** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude full control over your streaming and recording setup.

By the end of this guide, you'll have:
- 100+ OBS control tools available in Claude Desktop
- AI-managed scene switching, source control, and audio management
- Voice-style control over streaming, recording, and virtual camera
- The ability to build and modify your entire OBS setup through conversation

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude talk to your applications — in this case, your entire OBS Studio instance.

### What You'll Need

- **OBS Studio** (v31+ with WebSocket server support)
- **Claude Desktop** application
- **Node.js 16+** (via NVM or system install)
- **Linux workstation** (this guide uses Pop!_OS/Ubuntu, but works on macOS/Windows too)

---

## Architecture Overview

```
┌─────────────────┐      stdio       ┌──────────────────┐    WebSocket    ┌─────────────────┐
│  Claude Desktop │◄────────────────►│  OBS MCP Server  │◄──────────────►│   OBS Studio    │
│                 │    JSON-RPC      │  (Node.js/npx)   │   ws://4455    │                 │
└─────────────────┘                  └──────────────────┘                └─────────────────┘
```

**How It Works:**

1. OBS Studio runs a WebSocket server (built-in since OBS 28+)
2. The OBS MCP server connects to OBS via WebSocket
3. Claude Desktop launches the MCP server and communicates via stdio
4. You talk to Claude, Claude controls OBS

---

## Part 1: Enable the OBS WebSocket Server

### Step 1: Open WebSocket Server Settings

1. Open **OBS Studio**
2. Go to **Tools → WebSocket Server Settings**
3. Check **Enable WebSocket server**
4. The default port is `4455` — leave it unless you have a conflict
5. Check **Enable Authentication**
6. Click **Show Connect Info** to reveal your password
7. **Copy the Server Password** — you'll need it for the config

> 📝 **Note:** Write down the password somewhere safe. You'll need it in Part 3.

### Step 2: Verify WebSocket is Active

You should see the WebSocket server settings showing:
- **Server Port:** 4455
- **Server Password:** (your generated password)

---

## Part 2: The NVM PATH Problem (Linux Users)

If you installed Node.js via **NVM** (Node Version Manager) — which is very common on Linux — Claude Desktop won't be able to find `npx`. This is because Claude Desktop doesn't load your shell profile, so NVM's paths aren't available.

### How to Check

```bash
which npx
# Output: /home/YOUR_USER/.nvm/versions/node/v24.13.0/bin/npx
```

If your `npx` is inside `.nvm`, you'll hit this issue. The solution is a **wrapper script**.

### Why Not Just Use the Full Path?

You might think setting the command to the full `npx` path would work, but `npx` itself needs the full NVM environment to resolve packages. The wrapper script ensures everything is properly initialized.

> 💡 **macOS/Windows users:** If you installed Node.js via the official installer (not NVM), you can skip the wrapper script and use `npx` directly in the config. Jump to [Part 3 Alternative Config](#alternative-config-no-wrapper-needed).

---

## Part 3: Setting Up the MCP Server

### Step 1: Create Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/OBS_MCP
cd ~/Documents/Docker_Projects/OBS_MCP
```

### Step 2: Create the Wrapper Script

```bash
cat > obs-mcp-wrapper.sh << 'EOF'
#!/bin/bash
export PATH="/home/YOUR_USER/.nvm/versions/node/YOUR_NODE_VERSION/bin:$PATH"
export OBS_WEBSOCKET_PASSWORD="YOUR_OBS_PASSWORD"
export OBS_WEBSOCKET_URL="ws://localhost:4455"
exec npx -y obs-mcp@latest
EOF

chmod +x obs-mcp-wrapper.sh
```

**Replace the placeholders:**

| Placeholder | How to Find It |
|-------------|---------------|
| `YOUR_USER` | Run `whoami` |
| `YOUR_NODE_VERSION` | Run `node --version` (e.g., `v24.13.0`) |
| `YOUR_OBS_PASSWORD` | From OBS WebSocket Server Settings → Show Connect Info |

**Example with real values:**

```bash
cat > obs-mcp-wrapper.sh << 'EOF'
#!/bin/bash
export PATH="/home/obi1/.nvm/versions/node/v24.13.0/bin:$PATH"
export OBS_WEBSOCKET_PASSWORD="1OAAmJKxrH3Leb2R"
export OBS_WEBSOCKET_URL="ws://localhost:4455"
exec npx -y obs-mcp@latest
EOF

chmod +x obs-mcp-wrapper.sh
```

### Step 3: Test the Wrapper

```bash
./obs-mcp-wrapper.sh
```

**Expected output:**
```
Initialized MCP tools
OBS MCP Server running on stdio
Connecting to OBS WebSocket...
Connected to OBS WebSocket server
Identified with OBS WebSocket server
Connected to OBS WebSocket server
```

If you see this, everything is working. Press `Ctrl+C` to stop.

### Common Errors at This Stage

| Error | Cause | Fix |
|-------|-------|-----|
| `command not found: npx` | Wrong Node.js path in wrapper | Check `which npx` and update the PATH line |
| `Password required for authentication` | Password not set or wrong | Verify OBS_WEBSOCKET_PASSWORD matches OBS |
| `Connection refused` | OBS isn't running or wrong port | Start OBS first, check port 4455 |
| `ECONNREFUSED` | OBS WebSocket server not enabled | Enable it in Tools → WebSocket Server Settings |

---

## Part 4: Configuring Claude Desktop

### Step 1: Edit Your Config File

```bash
# Linux
nano ~/.config/Claude/claude_desktop_config.json

# macOS
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json

# Windows
notepad %APPDATA%\Claude\claude_desktop_config.json
```

### Step 2: Add the OBS MCP Server Entry

Add this to your `mcpServers` section:

```json
"obs": {
    "command": "/home/YOUR_USER/Documents/Docker_Projects/OBS_MCP/obs-mcp-wrapper.sh",
    "args": []
}
```

**Full example** (if this is your only MCP server):

```json
{
    "mcpServers": {
        "obs": {
            "command": "/home/YOUR_USER/Documents/Docker_Projects/OBS_MCP/obs-mcp-wrapper.sh",
            "args": []
        }
    }
}
```

### Alternative Config (No Wrapper Needed)

If your `npx` is in the system PATH (macOS/Windows with standard Node.js install):

```json
{
    "mcpServers": {
        "obs": {
            "command": "npx",
            "args": ["-y", "obs-mcp@latest"],
            "env": {
                "OBS_WEBSOCKET_PASSWORD": "YOUR_OBS_PASSWORD",
                "OBS_WEBSOCKET_URL": "ws://localhost:4455"
            }
        }
    }
}
```

### Step 3: Restart Claude Desktop

1. **Quit Claude Desktop completely** (check system tray too)
2. **Make sure OBS Studio is running** with WebSocket enabled
3. **Start Claude Desktop**

> ⚠️ **Important:** OBS must be running BEFORE Claude Desktop starts, since the MCP server connects to OBS on launch.

---

## Part 5: Available Tools

Once connected, you have access to **100+ tools** organized by category:

### General Operations
| Tool | Description |
|------|-------------|
| `obs-get-version` | Get OBS version and WebSocket info |
| `obs-get-stats` | Get OBS performance statistics |
| `obs-get-hotkey-list` | List all available hotkeys |
| `obs-trigger-hotkey-by-name` | Trigger a specific hotkey |
| `obs-get-studio-mode` | Check if Studio Mode is enabled |
| `obs-set-studio-mode` | Enable/disable Studio Mode |

### Scene Management
| Tool | Description |
|------|-------------|
| `obs-get-scene-list` | List all scenes |
| `obs-get-current-scene` | Get the active scene |
| `obs-set-current-scene` | Switch to a different scene |
| `obs-create-scene` | Create a new scene |
| `obs-remove-scene` | Delete a scene |
| `obs-get-preview-scene` | Get Studio Mode preview scene |
| `obs-set-preview-scene` | Set Studio Mode preview scene |

### Source & Input Control
| Tool | Description |
|------|-------------|
| `obs-get-input-list` | List all inputs/sources |
| `obs-create-input` | Add a new source |
| `obs-remove-input` | Remove a source |
| `obs-get-input-settings` | Get source settings |
| `obs-set-input-settings` | Modify source settings |
| `obs-get-special-inputs` | Get desktop/mic audio sources |

### Scene Item Manipulation
| Tool | Description |
|------|-------------|
| `obs-get-scene-items` | List items in a scene |
| `obs-create-scene-item` | Add a source to a scene |
| `obs-remove-scene-item` | Remove an item from a scene |
| `obs-set-scene-item-enabled` | Show/hide a scene item |
| `obs-get-scene-item-transform` | Get position/scale/crop |
| `obs-set-scene-item-transform` | Set position/scale/crop/rotation |

### Audio Control
| Tool | Description |
|------|-------------|
| `obs-get-input-volume` | Get volume level |
| `obs-set-input-volume` | Set volume (dB or multiplier) |
| `obs-get-input-mute` | Check mute status |
| `obs-set-input-mute` | Mute/unmute a source |
| `obs-toggle-input-mute` | Toggle mute |
| `obs-get-input-audio-balance` | Get audio balance |
| `obs-set-input-audio-balance` | Set audio balance (L/R) |
| `obs-get-input-audio-sync-offset` | Get audio sync offset |
| `obs-set-input-audio-sync-offset` | Set audio sync offset |
| `obs-get-input-audio-monitor-type` | Get monitoring type |
| `obs-set-input-audio-monitor-type` | Set monitoring type |

### Streaming
| Tool | Description |
|------|-------------|
| `obs-get-stream-status` | Check if streaming |
| `obs-start-stream` | Start streaming |
| `obs-stop-stream` | Stop streaming |
| `obs-toggle-stream` | Toggle streaming |
| `obs-send-stream-caption` | Send live captions (CEA-608) |

### Recording
| Tool | Description |
|------|-------------|
| `obs-get-record-status` | Check recording status |
| `obs-start-record` | Start recording |
| `obs-stop-record` | Stop recording |
| `obs-toggle-record` | Toggle recording |
| `obs-pause-record` | Pause recording |
| `obs-resume-record` | Resume recording |
| `obs-split-record-file` | Split into new file |
| `obs-create-record-chapter` | Add chapter marker |
| `obs-get-record-directory` | Get recording save path |
| `obs-set-record-directory` | Change recording save path |

### Virtual Camera
| Tool | Description |
|------|-------------|
| `obs-get-virtual-cam-status` | Check virtual camera status |
| `obs-start-virtual-cam` | Start virtual camera |
| `obs-stop-virtual-cam` | Stop virtual camera |
| `obs-toggle-virtual-cam` | Toggle virtual camera |

### Transitions
| Tool | Description |
|------|-------------|
| `obs-get-transition-list` | List available transitions |
| `obs-get-current-transition` | Get active transition |
| `obs-set-current-transition` | Change transition type |
| `obs-get-transition-duration` | Get transition duration |
| `obs-set-transition-duration` | Set transition duration |
| `obs-trigger-transition` | Trigger a transition |

### Filters
| Tool | Description |
|------|-------------|
| `obs-get-source-filter-list` | List filters on a source |
| `obs-create-source-filter` | Add a filter to a source |
| `obs-remove-source-filter` | Remove a filter |
| `obs-set-source-filter-enabled` | Enable/disable a filter |
| `obs-set-source-filter-settings` | Modify filter settings |

### Media Control
| Tool | Description |
|------|-------------|
| `obs-get-media-input-status` | Get media playback status |
| `obs-trigger-media-input-action` | Play/pause/stop/restart media |
| `obs-set-media-input-cursor` | Seek to position |
| `obs-offset-media-input-cursor` | Skip forward/backward |

### Screenshots & Projectors
| Tool | Description |
|------|-------------|
| `obs-get-source-screenshot` | Capture a screenshot (Base64) |
| `obs-save-source-screenshot` | Save screenshot to file |
| `obs-open-source-projector` | Open a source projector |
| `obs-open-video-mix-projector` | Open a video mix projector |

### Replay Buffer
| Tool | Description |
|------|-------------|
| `obs-get-replay-buffer-status` | Check replay buffer status |
| `obs-start-replay-buffer` | Start replay buffer |
| `obs-stop-replay-buffer` | Stop replay buffer |
| `obs-save-replay-buffer` | Save replay |
| `obs-get-last-replay-buffer-replay` | Get last saved replay path |

### Configuration & Profiles
| Tool | Description |
|------|-------------|
| `obs-get-scene-collection-list` | List scene collections |
| `obs-set-current-scene-collection` | Switch scene collection |
| `obs-get-profile-list` | List profiles |
| `obs-set-current-profile` | Switch profile |
| `obs-get-video-settings` | Get resolution/FPS settings |
| `obs-set-video-settings` | Change resolution/FPS |
| `obs-get-stream-service-settings` | Get stream key/server |
| `obs-set-stream-service-settings` | Set stream key/server |

---

## Part 6: Example Conversations

### Basic Scene Control
> **You:** What scenes do I have in OBS?
>
> **Claude:** *[Calls obs-get-scene-list]* You have one scene called "Main Monitor" which is currently active.

> **You:** Create a new scene called "Webcam Only"
>
> **Claude:** *[Calls obs-create-scene]* Done! I've created a new scene called "Webcam Only". Want me to switch to it?

### Streaming Control
> **You:** Am I currently streaming?
>
> **Claude:** *[Calls obs-get-stream-status]* No, you're not currently streaming. Want me to start?

> **You:** Start streaming
>
> **Claude:** *[Calls obs-start-stream]* You're now live! Streaming has started.

### Recording
> **You:** Start recording and add a chapter marker called "Intro"
>
> **Claude:** *[Calls obs-start-record, then obs-create-record-chapter]* Recording started! I've also added a chapter marker labeled "Intro".

### Audio Management
> **You:** Mute my microphone
>
> **Claude:** *[Calls obs-get-special-inputs, then obs-set-input-mute]* Your microphone is now muted.

> **You:** Set my desktop audio to 80%
>
> **Claude:** *[Calls obs-set-input-volume]* Desktop audio volume set to 80%.

### Scene Setup
> **You:** Set up my OBS for a tutorial recording — I want my screen capture with a small webcam in the bottom right
>
> **Claude:** *[Creates scene, adds sources, sets transforms]* I've set up your tutorial scene with screen capture as the main source and your webcam positioned in the bottom-right corner at 25% scale.

### Performance Check
> **You:** How's OBS performing right now?
>
> **Claude:** *[Calls obs-get-stats]* OBS is running smoothly — CPU usage is at 3.2%, no dropped frames, rendering at 60 FPS with 0 lagged frames.

---

## Part 7: Troubleshooting

### `spawn npx ENOENT`

**Cause:** Claude Desktop can't find `npx` because NVM paths aren't loaded.

**Solution:** Use the wrapper script approach (Part 3). Make sure the Node.js path in the wrapper matches your actual NVM installation:

```bash
which npx
# Copy this path's directory into the wrapper's PATH export
```

### `Password required for authentication but not provided`

**Cause:** The environment variable isn't being passed to the `obs-mcp` process.

**Solution:** Use the wrapper script which explicitly exports the password before launching.

### `ECONNREFUSED` or `Connection refused`

**Cause:** OBS isn't running or WebSocket server isn't enabled.

**Solution:**
1. Start OBS Studio first
2. Verify WebSocket is enabled: Tools → WebSocket Server Settings
3. Check the port: `ss -tlnp | grep 4455`

### Tools Load But Commands Fail

**Cause:** OBS was closed after Claude Desktop started.

**Solution:** Restart Claude Desktop with OBS already running.

### Script Not Found (`ENOENT` on wrapper path)

**Cause:** The path in `claude_desktop_config.json` doesn't match where the script actually is.

**Solution:** Use the full absolute path. Verify with:

```bash
ls -la /full/path/to/obs-mcp-wrapper.sh
```

---

## Part 8: Use Cases Beyond Streaming

### Security Demo Recording

As a cybersecurity professional, this integration is perfect for recording demonstrations:

```
"Start recording, switch to my terminal scene, and add a chapter marker called 'Nmap Scan'"
"Switch to the browser scene and mark a new chapter 'Web App Testing'"
"Stop recording"
```

### CTF Content Creation

Record your CTF walkthroughs hands-free:

```
"Create scenes for: Terminal, Browser, Notes, and Webcam"
"Start recording on the Terminal scene"
"Switch to Notes scene" (when explaining methodology)
"Add a chapter marker 'Flag Found'"
```

### Training Videos

Build training content without touching OBS:

```
"Set up a picture-in-picture layout with my screen and webcam"
"Start the virtual camera so I can use it in Zoom"
"Set the transition to a 500ms fade"
```

---

## Quick Reference

### Startup Checklist
```
1. ✅ Open OBS Studio
2. ✅ Verify WebSocket server is enabled (Tools → WebSocket Server Settings)
3. ✅ Start Claude Desktop
4. ✅ Ask Claude: "Get my OBS version" to verify connection
```

### Common Commands
```
"What scenes do I have?"
"Switch to [scene name]"
"Start/stop recording"
"Start/stop streaming"
"Mute/unmute my mic"
"Take a screenshot"
"Create a new scene called [name]"
"What's my OBS performance like?"
```

### File Locations
```bash
# Wrapper script
~/Documents/Docker_Projects/OBS_MCP/obs-mcp-wrapper.sh

# Claude Desktop config (Linux)
~/.config/Claude/claude_desktop_config.json

# Claude Desktop config (macOS)
~/Library/Application Support/Claude/claude_desktop_config.json
```

---

## Resources

- [OBS Studio](https://obsproject.com/)
- [OBS WebSocket Protocol](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md)
- [obs-mcp GitHub Repository](https://github.com/royshil/obs-mcp)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)

---

## Credits

- **Roy Shilkrot** ([@royshil](https://github.com/royshil)) for creating the [obs-mcp](https://github.com/royshil/obs-mcp) server
- **Anthropic** for Claude and the Model Context Protocol
- The **OBS Project** for an incredible open-source streaming tool

---

*Lights, camera, AI action!* 🎬

**— Hackerobi**
