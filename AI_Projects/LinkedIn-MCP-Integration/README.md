# Integrating LinkedIn with Claude AI: A Complete Guide to the LinkedIn MCP Server

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Beginner-Intermediate  
**Time Required:** 20-30 minutes

---

## Introduction

Imagine managing your LinkedIn presence by simply asking: *"Post an update about my latest project"* or *"Who am I logged in as?"* and having it just happen. This guide will show you how to connect **LinkedIn's API** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude the ability to manage your LinkedIn profile and publish posts on your behalf.

By the end of this guide, you'll have:
- LinkedIn profile access directly from Claude Desktop
- The ability to create and publish LinkedIn posts through conversation
- A working OAuth 2.0 authentication flow with LinkedIn's OpenID Connect

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude interact with your favorite services — in this case, LinkedIn.

### What You'll Need

- **LinkedIn Developer Account** and a registered application
- **Claude Desktop** application
- **Node.js v18+** installed on your system
- **Linux workstation** (this guide uses Pop!_OS/Ubuntu — works on macOS/Windows too)
- Basic familiarity with command line and OAuth concepts

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Your Workstation                                   │
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────────────────────────────┐  │
│  │  Claude Desktop  │         │          LinkedIn API v2                  │  │
│  │                  │         │    (api.linkedin.com/v2/userinfo)         │  │
│  │                  │         │    (api.linkedin.com/v2/posts)            │  │
│  └────────┬─────────┘         └──────────────────▲───────────────────────┘  │
│           │                                       │                          │
│           │ stdio                                 │ HTTPS (OAuth Bearer)     │
│           ▼                                       │                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │          LinkedIn MCP Server (Node.js + TypeScript)                  │   │
│  │                                                                      │   │
│  │  • User Profile Info (OpenID Connect)                               │   │
│  │  • Create & Publish Posts                                           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**How It Works:**

1. You give Claude natural language instructions about LinkedIn
2. Claude translates them into MCP tool calls
3. The MCP server authenticates with LinkedIn's OAuth 2.0 API
4. Claude presents the results or confirms actions in a conversational format

---

## The Journey: Why We Built This

### What We Started With

We used the open-source [linkedin-mcp-server](https://github.com/syndicai/linkedin-mcp-server) as our base. It's a clean TypeScript MCP server that uses the `linkedin-api-client` npm package and supports two tools: `user-info` and `create-post`.

### What Broke

After setting up the server and LinkedIn app, we hit a **403 Forbidden** error:

```
[403 Forbidden] LinkedIn API error: Not enough permissions to access: me.GET.NO_VERSION
```

The original server was using LinkedIn's **legacy v1 API endpoint** (`/me` with v1-style projection parameters like `profilePicture(displayImage~digitalmediaAsset:playableStreams)`). LinkedIn deprecated this endpoint in favor of their **OpenID Connect** flow.

### The Root Cause

Our LinkedIn app had the **"Sign In with LinkedIn using OpenID Connect"** product enabled (Standard Tier), which grants access to the `/v2/userinfo` endpoint — but **not** the legacy `/me` endpoint with v1 projection parameters. The original MCP server code was hitting the wrong endpoint.

### The Fix

We rewrote both tools to use LinkedIn's modern API:

1. **`user-info`** → Now calls `/v2/userinfo` (OpenID Connect) instead of the legacy `/me` endpoint
2. **`create-post`** → Now gets the user's `sub` (member ID) from `/v2/userinfo` instead of `/me`, then creates the post via the `/posts` endpoint using the `linkedin-api-client`

This was a clean fix that required no additional OAuth scopes — just using the right endpoints for the products we already had enabled.

---

## Part 1: Setting Up Your LinkedIn Developer App

### Step 1: Create a LinkedIn App

1. Go to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/)
2. Click **Create App**
3. Fill in the details:
   - **App name:** Something like `Link_MCP`
   - **LinkedIn Page:** Select or create a company page
   - **App type:** Standalone app
4. Click **Create App**

### Step 2: Add Required Products

In your app's **Products** tab, add these products:

| Product | Tier | Why You Need It |
|---------|------|------------------|
| **Share on LinkedIn** | Default | Enables posting to LinkedIn (`w_member_social` scope) |
| **Sign In with LinkedIn using OpenID Connect** | Standard | Enables user info access (`openid`, `profile`, `email` scopes) |

> **Note:** "Sign In with LinkedIn using OpenID Connect" may require approval. "Share on LinkedIn" is typically available immediately.

### Step 3: Configure OAuth 2.0

1. Go to the **Auth** tab in your app settings
2. Under **OAuth 2.0 Scopes**, verify you have:
   - `openid`
   - `profile`
   - `email`
   - `w_member_social`
3. Add an **Authorized Redirect URL** (needed for the OAuth flow):
   ```
   http://localhost:3000/auth/callback
   ```

### Step 4: Note Your Credentials

From the **Auth** tab, save:
- **Client ID**
- **Primary Client Secret**

> **⚠️ Security Note:** Never share your Client Secret publicly. If you accidentally expose it, immediately generate a new one from the app settings.

### Step 5: Generate an Access Token

You need a valid OAuth 2.0 access token. The server includes an auth flow, or you can use LinkedIn's [OAuth Token Generator](https://www.linkedin.com/developers/tools/oauth) for testing:

1. Go to your app → **Auth** tab → **OAuth 2.0 tools**
2. Request a token with scopes: `openid profile email w_member_social`
3. Complete the authorization flow
4. Copy the generated access token

> **⏰ Token Expiration:** LinkedIn access tokens expire after 60 days. You'll need to regenerate when they expire.

---

## Part 2: Setting Up the MCP Server

### Step 1: Create Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/Linkd_MCP
cd ~/Documents/Docker_Projects/Linkd_MCP
```

### Step 2: Clone and Install the Base Server

```bash
git clone https://github.com/syndicai/linkedin-mcp-server.git
cd linkedin-mcp-server
npm install
```

### Step 3: Create the Wrapper Script

Claude Desktop needs a shell script to launch the server with the correct Node.js path:

```bash
cat > linkedin-mcp-wrapper.sh << 'EOF'
#!/bin/bash
export PATH="/home/YOUR_USERNAME/.nvm/versions/node/v24.13.0/bin:$PATH"
exec /home/YOUR_USERNAME/Documents/Docker_Projects/Linkd_MCP/linkedin-mcp-server/node_modules/.bin/tsx /home/YOUR_USERNAME/Documents/Docker_Projects/Linkd_MCP/linkedin-mcp-server/src/stdio_index.ts
EOF
chmod +x linkedin-mcp-wrapper.sh
```

Replace `YOUR_USERNAME` with your actual username and adjust the Node.js version path to match your installation.

> **💡 Why a wrapper script?** Claude Desktop launches MCP servers as child processes. The wrapper ensures the correct Node.js version is on the PATH (especially important when using NVM) and launches the TypeScript server via `tsx`.

### Step 4: Replace the Server Code

This is the critical step. The original `src/stdio_index.ts` uses LinkedIn's deprecated v1 API. Replace it with our fixed version that uses OpenID Connect.

> **📄 The complete source code is included in this repository as [`stdio_index.ts`](./stdio_index.ts)**

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

### Step 2: Add the LinkedIn MCP Server

Add this to the `mcpServers` section of your config:

```json
"linkedin": {
    "command": "/home/YOUR_USERNAME/Documents/Docker_Projects/Linkd_MCP/linkedin-mcp-server/linkedin-mcp-wrapper.sh",
    "args": [],
    "env": {
        "LINKEDIN_ACCESS_TOKEN": "YOUR_ACCESS_TOKEN_HERE"
    }
}
```

Replace `YOUR_USERNAME` and `YOUR_ACCESS_TOKEN_HERE` with your actual values.

> **🔒 Security Tip:** Set restrictive permissions on your config file since it contains your access token:
> ```bash
> chmod 600 ~/.config/Claude/claude_desktop_config.json
> ```

### Step 3: Restart Claude Desktop

Close and reopen Claude Desktop. You should see the LinkedIn tools become available (look for the hammer icon showing 2 tools).

### Verifying the Connection

Check the MCP logs to confirm a successful connection:

```bash
# Linux
tail -f ~/.config/Claude/logs/mcp-server-linkedin.log
```

You should see:
```
LinkedIn MCP Server v0.3.0 running on stdio
```

---

## Part 4: Available Tools

Once connected, you'll have access to **2 LinkedIn management tools**:

| Tool | Description |
|------|-------------|
| `user-info` | Get the currently logged-in user's name, email, member ID, and profile picture |
| `create-post` | Create and publish a new post to LinkedIn with specified text content |

---

## Part 5: Example Conversations

### Get Your Profile Info
> **You:** Who am I logged in as on LinkedIn?
>
> **Claude:** *[Calls user-info]*
> You're logged in as Robert Garcia (robert787@protonmail.com), LinkedIn Member ID: dSeM0qXkC4.

### Create a Post
> **You:** Post an update on LinkedIn about my latest cybersecurity project
>
> **Claude:** *[Drafts the post for your review, then calls create-post]*
> Your post has been successfully created on LinkedIn!

### Draft Before Posting
> **You:** Help me write a LinkedIn post about AI in cybersecurity, but let me review it first
>
> **Claude:** *[Drafts the post and shows it to you]* Here's a draft — want me to publish it?
>
> **You:** Looks good, post it!
>
> **Claude:** *[Calls create-post]* Done! Your post is now live.

---

## Part 6: Troubleshooting

### "403 Forbidden — Not enough permissions to access: me.GET.NO_VERSION"

**Cause:** The server is using the legacy `/me` endpoint instead of `/v2/userinfo`.

**Solution:** Make sure you're using the updated `stdio_index.ts` from this guide. The fix switches from the deprecated v1 `/me` endpoint to the OpenID Connect `/v2/userinfo` endpoint.

### "LINKEDIN_ACCESS_TOKEN environment variable is required"

**Cause:** The access token isn't being passed to the server.

**Solution:**
1. Check your `claude_desktop_config.json` — make sure the `env` block contains your token
2. Ensure there are no extra spaces or line breaks in the token string
3. Restart Claude Desktop after making changes

### "401 Unauthorized"

**Cause:** Your access token has expired (LinkedIn tokens expire after 60 days).

**Solution:**
1. Go to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/)
2. Generate a new access token
3. Update your `claude_desktop_config.json` with the new token
4. Restart Claude Desktop

### Tools Not Appearing in Claude Desktop

**Solution:**
1. Check the MCP log: `~/.config/Claude/logs/mcp-server-linkedin.log`
2. Verify JSON syntax in your config file (use a JSON validator)
3. Make sure the wrapper script is executable: `chmod +x linkedin-mcp-wrapper.sh`
4. Make sure the paths in your config are absolute (no `~`)
5. Verify Node.js path in the wrapper script matches your installation
6. Restart Claude Desktop completely (not just reload)

### "Cannot find module 'tsx'"

**Cause:** Node modules aren't installed or the path is wrong.

**Solution:**
```bash
cd ~/Documents/Docker_Projects/Linkd_MCP/linkedin-mcp-server
npm install
```

---

## Part 7: Understanding the LinkedIn API Changes

For those curious about the technical details, here's what changed and why:

### The Legacy API (What Broke)

```
GET https://api.linkedin.com/v2/me?projection=(localizedFirstName,localizedLastName,localizedHeadline,profilePicture(displayImage~digitalmediaAsset:playableStreams))
```

This endpoint required the **"Sign In with LinkedIn v1"** product, which LinkedIn has been phasing out. The v1-style projection parameters (`displayImage~digitalmediaAsset:playableStreams`) are no longer supported for new apps.

### The Modern API (What Works)

```
GET https://api.linkedin.com/v2/userinfo
Authorization: Bearer {access_token}
```

This returns a standard OpenID Connect response:

```json
{
  "sub": "dSeM0qXkC4",
  "name": "Robert Garcia",
  "given_name": "Robert",
  "family_name": "Garcia",
  "picture": "https://media.licdn.com/...",
  "email": "robert787@protonmail.com",
  "email_verified": true
}
```

Clean, simple, and works with the **"Sign In with LinkedIn using OpenID Connect"** product that's available to all apps.

---

## Quick Reference

### Setup Commands
```bash
# Create project
mkdir -p ~/Documents/Docker_Projects/Linkd_MCP
cd ~/Documents/Docker_Projects/Linkd_MCP

# Clone and install
git clone https://github.com/syndicai/linkedin-mcp-server.git
cd linkedin-mcp-server
npm install

# Create wrapper script
chmod +x linkedin-mcp-wrapper.sh

# Test manually
LINKEDIN_ACCESS_TOKEN=your_token_here npx tsx src/stdio_index.ts
```

### Common Claude Commands
```
"Who am I logged in as on LinkedIn?"
"Create a LinkedIn post about [topic]"
"Post this to LinkedIn: [your content]"
"Draft a LinkedIn post about [topic] for my review"
```

### File Locations
```
Server:   ~/Documents/Docker_Projects/Linkd_MCP/linkedin-mcp-server/src/stdio_index.ts
Wrapper:  ~/Documents/Docker_Projects/Linkd_MCP/linkedin-mcp-server/linkedin-mcp-wrapper.sh
Config:   ~/.config/Claude/claude_desktop_config.json
Logs:     ~/.config/Claude/logs/mcp-server-linkedin.log
```

### LinkedIn Developer Portal
```
App Settings:  https://www.linkedin.com/developers/apps
OAuth Tools:   https://www.linkedin.com/developers/tools/oauth
API Docs:      https://learn.microsoft.com/en-us/linkedin/
```

---

## Resources

- [LinkedIn Developer Portal](https://www.linkedin.com/developers/)
- [LinkedIn OpenID Connect Documentation](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2)
- [LinkedIn Posts API Documentation](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)
- [linkedin-mcp-server (base project)](https://github.com/syndicai/linkedin-mcp-server)
- [linkedin-api-client (npm)](https://www.npmjs.com/package/linkedin-api-client)

---

*Happy networking! Use these tools to share your work, connect with your community, and build your professional presence — all through conversation.* 💼

**— Hackerobi**