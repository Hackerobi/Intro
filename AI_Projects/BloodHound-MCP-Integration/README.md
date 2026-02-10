# Integrating BloodHound CE with Claude AI: A Complete Guide

**Author:** Hackerobi  
**Date:** January 2026  
**Difficulty:** Intermediate  
**Time Required:** 45-60 minutes

---

## Introduction

Imagine telling your AI assistant: *"Show me all paths from JSMITH to Domain Admin"* — and watching it instantly query Neo4j, map out the attack chain, and explain the privilege escalation path in plain English. No Cypher queries to memorize, no manual graph navigation. This guide will show you how to connect **BloodHound Community Edition** to **Claude Desktop** using the **Model Context Protocol (MCP)**, giving Claude the ability to analyze Active Directory attack paths through natural conversation.

By the end of this guide, you'll have:
- A persistent BloodHound CE Docker deployment on custom ports (survives reboots)
- 75+ specialized AD analysis tools available in Claude Desktop
- AI-powered attack path discovery, privilege escalation mapping, and domain enumeration
- Natural language queries against your BloodHound Neo4j graph database
- The ability to identify Kerberoastable users, ESC1 ADCS vulnerabilities, WriteDacl misconfigurations, and more — all through conversation

### What is BloodHound CE?

[BloodHound Community Edition](https://github.com/SpecterOps/BloodHound) is the industry-standard tool for Active Directory security analysis. Built by SpecterOps, it uses graph theory to map relationships and attack paths within AD environments. BloodHound collects data about AD objects (users, groups, computers, GPOs, certificates) and stores it in a Neo4j graph database, revealing hidden privilege escalation paths that traditional tools miss.

It answers the question every pentester asks: *"How do I get from this low-privilege account to Domain Admin?"*

### What is BloodHound-MCP-AI?

[BloodHound-MCP-AI](https://github.com/MorDavid/BloodHound-MCP-AI) is the **first-ever BloodHound AI integration**, created by [MorDavid](https://github.com/MorDavid). It provides over 75 specialized MCP tools based on BloodHound CE Cypher queries, allowing security professionals to analyze Active Directory attack paths using natural language instead of writing complex Cypher queries manually.

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude talk to your favorite platforms — in this case, your BloodHound graph database full of Active Directory relationships.

### What You'll Need

- **Linux workstation** (this guide uses Pop!_OS, but Ubuntu/Debian will work)
- **Docker Engine** (Docker CE) with Compose plugin
- **Claude Desktop** application
- **Python 3.8+** and pip
- **BloodHound data** collected from an Active Directory environment (via SharpHound or similar collector)
- Basic familiarity with command line and Docker

---

## Architecture Overview

```
┌─────────────────┐    stdio      ┌───────────────────────────────┐   Bolt     ┌──────────────────────┐
│  Claude Desktop │◄─────────────►│  BloodHound-MCP-AI            │◄──────────►│  Neo4j Database      │
│                 │   JSON-RPC    │  (Python MCP Server)           │  bolt://   │  (Docker Container)  │
└─────────────────┘               │                               │  :17687    │                      │
                                  │  ┌─────────────────────────┐  │            │  ┌────────────────┐  │
                                  │  │ Domain Enumeration       │  │            │  │ AD Graph Data   │  │
                                  │  │ • Users, Groups          │  │            │  │ • Users         │  │
                                  │  │ • Computers, OUs         │  │            │  │ • Groups        │  │
                                  │  │ • GPOs, Domains          │  │            │  │ • Computers     │  │
                                  │  └─────────────────────────┘  │            │  │ • Relationships  │  │
                                  │  ┌─────────────────────────┐  │            │  └────────────────┘  │
                                  │  │ Attack Path Analysis      │  │            └──────────────────────┘
                                  │  │ • Shortest Paths          │  │
                                  │  │ • Privilege Escalation    │  │            ┌──────────────────────┐
                                  │  │ • Lateral Movement        │  │            │  BloodHound Web UI   │
                                  │  └─────────────────────────┘  │            │  (Docker Container)  │
                                  │  ┌─────────────────────────┐  │            │  http://localhost     │
                                  │  │ Kerberos & ADCS          │  │            │  :18080               │
                                  │  │ • Kerberoasting          │  │            └──────────────────────┘
                                  │  │ • AS-REP Roasting        │  │
                                  │  │ • ESC1-ESC8 Templates    │  │            ┌──────────────────────┐
                                  │  │ • Certificate Abuse      │  │            │  PostgreSQL           │
                                  │  └─────────────────────────┘  │            │  (Docker Container)  │
                                  │  ┌─────────────────────────┐  │            │  BloodHound app DB   │
                                  │  │ Custom Cypher Queries     │  │            └──────────────────────┘
                                  │  │ • Raw Neo4j access        │  │
                                  │  │ • Any Cypher query        │  │
                                  │  └─────────────────────────┘  │
                                  └───────────────────────────────┘
```

**How it works:**

1. BloodHound CE runs as a Docker Compose stack with three containers (app, Neo4j, PostgreSQL)
2. The MCP server connects directly to the Neo4j Bolt port to query the AD graph
3. Claude Desktop communicates with the MCP server via stdio transport
4. You ask Claude questions in plain English, Claude translates them into Cypher queries and returns the results
5. The BloodHound web UI remains available for visual graph exploration alongside Claude

**Key Design Decision — Custom Ports:** We deploy BloodHound on non-standard ports (18080, 17474, 17687) to avoid conflicts with other services that might be listening on the defaults. This is critical when running multiple Docker projects on the same host.

---

## Part 1: Deploying BloodHound CE (Persistent Docker Setup)

We want BloodHound to survive reboots and run on custom ports. Here's how to set that up properly.

### Step 1: Create the Project Directory

```bash
sudo mkdir -p /opt/bloodhound-ce
cd /opt/bloodhound-ce
```

### Step 2: Create the Docker Compose File

```bash
sudo nano docker-compose.yml
```

Paste the following:

```yaml
# /opt/bloodhound-ce/docker-compose.yml
services:
  app-db:
    image: docker.io/library/postgres:16
    container_name: bloodhound-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_USER=bloodhound
      - POSTGRES_PASSWORD=bloodhoundcommunityedition
      - POSTGRES_DB=bloodhound
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bloodhound -d bloodhound -h 127.0.0.1 -p 5432"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  graph-db:
    image: docker.io/library/neo4j:4.4
    container_name: bloodhound-neo4j
    restart: unless-stopped
    environment:
      - NEO4J_AUTH=neo4j/bloodhoundcommunityedition
      - NEO4J_dbms_allow__upgrade=true
    ports:
      - "0.0.0.0:17474:7474"   # Neo4j Web Interface (custom port)
      - "0.0.0.0:17687:7687"   # Neo4j Bolt (custom port) — MCP connects here
    volumes:
      - neo4j-data:/data
    healthcheck:
      test: ["CMD-SHELL", "wget -O /dev/null -q http://localhost:7474 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  bloodhound:
    image: docker.io/specterops/bloodhound:latest
    container_name: bloodhound-app
    restart: unless-stopped
    environment:
      - bhe_disable_cypher_complexity_limit=false
      - bhe_enable_cypher_mutations=false
      - bhe_graph_query_memory_limit=2
      - bhe_database_connection=user=bloodhound password=bloodhoundcommunityedition dbname=bloodhound host=app-db
      - bhe_neo4j_connection=neo4j://neo4j:bloodhoundcommunityedition@graph-db:7687/
      - bhe_graph_driver=neo4j
    ports:
      - "0.0.0.0:18080:8080"   # BloodHound Web UI (custom port)
    depends_on:
      app-db:
        condition: service_healthy
      graph-db:
        condition: service_healthy

volumes:
  postgres-data:
  neo4j-data:
```

### Port Mapping Summary

| Service | Default Port | Custom Port | Purpose |
|---------|--------------|-------------|---------|
| BloodHound Web UI | 8080 | **18080** | Web interface for graph visualization |
| Neo4j Web Interface | 7474 | **17474** | Neo4j browser for direct Cypher queries |
| Neo4j Bolt | 7687 | **17687** | Database connection — **MCP connects here** |

### Step 3: Deploy and Enable Persistence

```bash
cd /opt/bloodhound-ce
sudo docker compose up -d
```

The `restart: unless-stopped` directive ensures all three containers come back after a reboot automatically. No systemd service file needed.

### Step 4: Verify the Deployment

```bash
# Check all three containers are running
docker ps --filter name=bloodhound

# Expected output:
# bloodhound-app       Up      0.0.0.0:18080->8080/tcp
# bloodhound-neo4j     Up      0.0.0.0:17474->7474/tcp, 0.0.0.0:17687->7687/tcp
# bloodhound-postgres  Up      5432/tcp
```

### Step 5: Get the Initial Admin Password

```bash
docker logs bloodhound-app 2>&1 | grep "Initial Password"
```

Save this password — you'll need it to log into the BloodHound web portal at **http://localhost:18080**.

### Step 6: Upload BloodHound Data

1. Open **http://localhost:18080** in your browser
2. Log in with the admin credentials
3. Navigate to the **Upload** section
4. Upload your SharpHound collection ZIP file

Once the data is ingested, Neo4j is populated with your AD graph — and ready for MCP queries.

---

## Part 2: Setting Up the BloodHound MCP Server

### Step 1: Create the Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/Blood_MCP/MCP_Blood
cd ~/Documents/Docker_Projects/Blood_MCP/MCP_Blood
```

### Step 2: Clone the BloodHound-MCP-AI Repository

```bash
git clone https://github.com/MorDavid/BloodHound-MCP-AI.git
cd BloodHound-MCP-AI
```

### Step 3: Install Dependencies

```bash
pip install neo4j mcp
```

> 💡 **Pop!_OS Note:** If you get permission errors, use `pip install --break-system-packages neo4j mcp` or set up a virtual environment.

### Step 4: Verify the MCP Server File

```bash
ls -la BloodHound-MCP.py
# Should exist at:
# ~/Documents/Docker_Projects/Blood_MCP/MCP_Blood/BloodHound-MCP-AI/BloodHound-MCP.py
```

This single Python file contains all 75+ tools and the Neo4j connection logic.

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

### Add the BloodHound MCP Server

Edit your config to add the `bloodhound` entry:

```json
{
  "mcpServers": {
    "bloodhound": {
      "command": "/usr/bin/python3",
      "args": [
        "/home/YOUR_USERNAME/Documents/Docker_Projects/Blood_MCP/MCP_Blood/BloodHound-MCP-AI/BloodHound-MCP.py"
      ],
      "env": {
        "BLOODHOUND_URI": "bolt://localhost:17687",
        "BLOODHOUND_USERNAME": "neo4j",
        "BLOODHOUND_PASSWORD": "bloodhoundcommunityedition"
      }
    }
  }
}
```

> ⚠️ **Critical:** Note the custom port `17687` in the Bolt URI — this must match the port you set in the Docker Compose file. If you used the default port (7687), update accordingly.

> 📝 **Note:** If you already have other MCP servers configured (like Wazuh, Burp Suite, SysReptor, etc.), just add the `bloodhound` entry alongside them inside the existing `mcpServers` object.

### Restart Claude Desktop

Close and reopen Claude Desktop. The BloodHound tools should now appear in the tools list — all 75+ of them!

### Verify the Connection

In Claude Desktop, ask:

> "How many domain users do I have in BloodHound?"

Claude will call the `query_bloodhound` tool with a Cypher query and return the count. If you get a number back, you're connected!

---

## Part 4: Available Tools (75+ Specialized Queries)

Once connected, you have access to a comprehensive toolkit organized into several categories:

### Domain Enumeration
| Tool | Description |
|------|-------------|
| `query_bloodhound` | Execute any raw Cypher query against the Neo4j graph |
| `find_all_domain_users` | List all user accounts in the domain |
| `find_all_domain_computers` | List all computer objects |
| `find_all_domain_groups` | List all security and distribution groups |
| `find_all_ous` | List all Organizational Units |
| `find_all_gpos` | List all Group Policy Objects |
| `find_all_domains` | List all domains and trusts |
| `find_all_containers` | List all AD containers |

### Privilege Escalation & Attack Paths
| Tool | Description |
|------|-------------|
| `find_shortest_paths_to_domain_admins` | Map shortest attack paths to Domain Admins |
| `find_shortest_path` | Find shortest path between any two AD objects |
| `find_users_with_dcsync` | Identify users with DCSync privileges |
| `find_gpo_creators` | Find who can create GPOs |
| `find_laps_readers` | Identify accounts that can read LAPS passwords |
| `find_users_with_constrained_delegation` | Find constrained delegation misconfigurations |
| `find_users_with_unconstrained_delegation` | Find unconstrained delegation risks |

### Kerberos Security
| Tool | Description |
|------|-------------|
| `find_all_kerberoastable_users` | Find all accounts with SPNs (Kerberoastable) |
| `find_kerberoastable_tier_zero` | Find Kerberoastable accounts in Tier Zero |
| `find_asreproast_users` | Find accounts vulnerable to AS-REP Roasting |

### ADCS (Certificate Services) Analysis
| Tool | Description |
|------|-------------|
| `find_esc1_vulnerable_templates` | Find ESC1 vulnerable certificate templates |
| `find_certificate_enrollment_rights` | Check who can enroll in certificate templates |
| `find_certificate_authorities` | List all Certificate Authorities |

### Session & Logon Analysis
| Tool | Description |
|------|-------------|
| `find_sessions_for_user` | Find where a specific user has active sessions |
| `find_sessions_on_computer` | Find who's logged into a specific computer |
| `find_admin_sessions` | Find where admin accounts have active sessions |

### Group & Permission Analysis
| Tool | Description |
|------|-------------|
| `find_group_members` | List members of any group (recursive) |
| `find_foreign_group_members` | Find cross-domain group memberships |
| `find_local_admin_groups` | Map local admin group memberships |
| `find_rdp_groups` | Find who has RDP access to machines |

### Trust Analysis
| Tool | Description |
|------|-------------|
| `find_domain_trusts` | Map all domain trust relationships |
| `find_foreign_users` | Find users from trusted domains |

> 📝 This is not an exhaustive list — BloodHound-MCP-AI provides **75+** tools covering nearly every BloodHound CE Cypher query category. The `query_bloodhound` tool also lets you run **any custom Cypher query**, giving you unlimited flexibility.

---

## Part 5: Example Conversations

Here's what it actually looks like to use BloodHound through Claude. These examples use fictional domain data to illustrate the workflow:

### Count and List Domain Users
> **You:** How many domain users do I have in BloodHound?
>
> **Claude:** *[Calls query_bloodhound: `MATCH (u:User) RETURN count(u)`]* You have **11 domain users** in your BloodHound database.
>
> **You:** Can you list them for me?
>
> **Claude:** *[Calls query_bloodhound]* Here are your 11 domain users in YOURCOMPANY.LOCAL:
> DVADMIN, CERTADM, JSMITH, GUEST, KRBTGT, DEMOUSER, BACKUP$, APPSVC, IUSR, HELPDESK, SQLADMIN
>
> A few things that stand out — BACKUP$ has the `$` suffix suggesting it might be a machine account miscategorized as a user. DVADMIN and APPSVC are likely privileged accounts worth investigating.

### Discover Attack Paths from a Specific User
> **You:** What interesting privileges does JSMITH have?
>
> **Claude:** *[Queries for outbound permissions and multi-hop paths]*
>
> JSMITH has a path to **GenericWrite** on **WEBSRV01.YOURCOMPANY.LOCAL** via two routes:
> 1. JSMITH → MemberOfLocalGroup → LocalToComputer → GenericWrite on WEBSRV01
> 2. JSMITH → CanRDP → GenericWrite on WEBSRV01
>
> GenericWrite on a computer object allows you to write to the `msDS-AllowedToActOnBehalfOfOtherIdentity` attribute — that's Resource-Based Constrained Delegation abuse, potentially giving you code execution on the web server.

### Find the Path to Domain Admin
> **You:** See if there's another approach.
>
> **Claude:** *[Queries for shortest path to Domain Admins, Kerberoastable users, AS-REP Roasting, and ESC1]*
>
> Found a **6-hop path to Domain Admins:**
> ```
> JSMITH → MemberOf → DOMAIN USERS → MemberOf → USERS
>     → LocalToComputer → DC01.YOURCOMPANY.LOCAL (Domain Controller!)
>     → DCFor → YOURCOMPANY.LOCAL → Contains → ADMINISTRATORS
>     → WriteDacl → DOMAIN ADMINS
> ```
> The USERS group has LocalToComputer rights on the Domain Controller — that's a serious misconfiguration. From the DC context, you can abuse WriteDacl to grant yourself Domain Admin membership.

### Discover ADCS Vulnerabilities
> **You:** We have two interesting finds, let's look for another.
>
> **Claude:** *[Checks Kerberoasting, AS-REP Roasting, and ADCS]*
>
> 🔥 Found an **ESC1 Vulnerable Certificate Template!**
>
> Template: YOURTEMPLATE@YOURCOMPANY.LOCAL
> - enrolleesuppliessubject: **TRUE**
> - authenticationenabled: TRUE
> - requiresmanagerapproval: FALSE
>
> The ENROLLEE_SUPPLIES_SUBJECT flag lets an attacker control the Subject Alternative Name — meaning they can request a certificate as any user, including Domain Admin. Currently only Domain/Enterprise Admins can enroll, but let's check if there's a path for JSMITH to get enrollment rights...

### Custom Cypher Queries
> **You:** Run a custom query to find all users who haven't changed their password in over a year.
>
> **Claude:** *[Calls query_bloodhound: `MATCH (u:User) WHERE u.pwdlastset < (datetime().epochSeconds - 31536000) RETURN u.name, u.pwdlastset`]*
> Found 4 accounts with stale passwords...

---

## Part 6: Multi-Tool Pipeline Workflows

The real power emerges when you combine BloodHound MCP with your other security tool integrations:

### BloodHound → SysReptor Pipeline
```
You: Show me all Kerberoastable users from BloodHound, then create
     findings for each one in SysReptor.
Claude: [Queries BloodHound for Kerberoastable users]
        [Creates findings in SysReptor from template for each user]
        Found 3 Kerberoastable accounts. Created findings for each with
        the SPN details and risk assessment.
```

### BloodHound → Wazuh Correlation
```
You: Cross-reference the Domain Admin accounts from BloodHound with
     any failed logon alerts in Wazuh from the last 24 hours.
Claude: [Queries BloodHound for DA members]
        [Searches Wazuh for failed logon events matching those accounts]
        DVADMIN@YOURCOMPANY.LOCAL had 34 failed logon attempts from
        10.10.14.22 — possible brute force targeting a privileged account.
```

### BloodHound → Burp Suite Context
```
You: I found a web application running on WEBSRV01. What attack paths
     lead to that computer in BloodHound?
Claude: [Queries BloodHound for all paths to WEBSRV01.YOURCOMPANY.LOCAL]
        3 users can reach WEBSRV01 via different paths. JSMITH
        has GenericWrite via LocalToComputer. Compromising the web app
        on WEBSRV01 could provide a foothold for lateral movement.
```

This is the vision — **AI as the connective tissue between your security tools**, correlating data across platforms that would take hours to cross-reference manually.

---

## Troubleshooting

### Claude Desktop Shows No BloodHound Tools

**Problem:** After adding the config, BloodHound tools don't appear in Claude Desktop.

**Solution:** Check the Python path and script path are correct:

```bash
# Verify the MCP script exists
ls -la ~/Documents/Docker_Projects/Blood_MCP/MCP_Blood/BloodHound-MCP-AI/BloodHound-MCP.py

# Verify Python path
which python3
# Should return /usr/bin/python3

# Test the MCP server manually
python3 ~/Documents/Docker_Projects/Blood_MCP/MCP_Blood/BloodHound-MCP-AI/BloodHound-MCP.py
```

Common issues:
- Wrong Python path (use `which python3` to find yours)
- Missing directory in the path (check for `MCP_Blood` subdirectory)
- Missing dependencies (`pip install neo4j mcp`)

### "Connection Refused" on Neo4j

**Problem:** MCP server can't connect to the BloodHound Neo4j database.

**Solution:** Verify the Bolt port is accessible:

```bash
# Check if Neo4j is listening on the custom port
sudo ss -tlnp | grep 17687

# Test the Bolt connection directly
curl -s http://localhost:17474
# Should return the Neo4j browser page

# Verify the Docker container is running
docker ps --filter name=bloodhound-neo4j
```

Make sure the `BLOODHOUND_URI` in your Claude config matches your Docker Compose port mapping. If you used default ports, it should be `bolt://localhost:7687`.

### Empty Query Results

**Problem:** Queries return zero results even though BloodHound web UI shows data.

**Solution:** This usually means data hasn't been ingested yet:

1. Open **http://localhost:18080**
2. Upload your SharpHound collection ZIP
3. Wait for ingestion to complete
4. Try querying again

Also verify the Neo4j credentials match what's in your Docker Compose file.

### BloodHound Containers Don't Start After Reboot

**Problem:** After rebooting, BloodHound containers aren't running.

**Solution:** The `restart: unless-stopped` policy should handle this, but verify:

```bash
# Check container status
docker ps -a --filter name=bloodhound

# If stopped, start them
cd /opt/bloodhound-ce
sudo docker compose up -d

# Verify Docker is set to start on boot
sudo systemctl is-enabled docker
# If not: sudo systemctl enable docker
```

### Neo4j Memory Issues

**Problem:** Neo4j crashes or becomes unresponsive with large datasets.

**Solution:** Add memory constraints to the Docker Compose file:

```yaml
graph-db:
  environment:
    - NEO4J_dbms_memory_heap_initial__size=512m
    - NEO4J_dbms_memory_heap_max__size=1G
    - NEO4J_dbms_memory_pagecache_size=512m
```

---

## Quick Reference

### Start BloodHound
```bash
cd /opt/bloodhound-ce
sudo docker compose up -d
```

### Stop BloodHound
```bash
cd /opt/bloodhound-ce
sudo docker compose down
```

### Check Status
```bash
docker ps --filter name=bloodhound
```

### View Logs
```bash
# BloodHound app logs
docker logs bloodhound-app

# Neo4j logs
docker logs bloodhound-neo4j
```

### Access Points
| Service | URL |
|---------|-----|
| BloodHound Web UI | http://localhost:18080 |
| Neo4j Browser | http://localhost:17474 |
| Neo4j Bolt (MCP) | bolt://localhost:17687 |

### Test MCP Connection
Ask Claude: *"How many domain users are in BloodHound?"*

---

## Security Considerations

- **Neo4j Credentials:** The default credentials (`neo4j/bloodhoundcommunityedition`) are in the Docker Compose file. Change them for production use and update both the Docker Compose and Claude Desktop config.
- **Port Exposure:** The custom ports are bound to `0.0.0.0` for convenience. In production, bind to `127.0.0.1` to restrict access to localhost only.
- **BloodHound Data:** Your Neo4j database contains a complete map of your Active Directory environment — treat it as highly sensitive. Ensure your Docker volumes are on encrypted storage.
- **Authorization:** Always ensure you have proper authorization before collecting and analyzing Active Directory data. BloodHound-MCP-AI is designed for legitimate security assessments only.
- **API Access:** The MCP server has full read access to your BloodHound graph. Anyone with access to your Claude Desktop config can query your AD data.

---

## Conclusion

You now have AI-powered Active Directory attack path analysis integrated directly into your workflow. This setup lets you:

- Query your BloodHound graph using plain English instead of Cypher
- Discover privilege escalation paths through natural conversation
- Identify Kerberoastable accounts, ADCS vulnerabilities, and delegation misconfigurations instantly
- Combine AD analysis with your other security tools (Wazuh, Burp Suite, SysReptor) for comprehensive assessments
- Run any custom Cypher query when you need full flexibility

The days of memorizing Cypher syntax and manually clicking through graph nodes are over. Ask Claude what you want to know about your AD environment, and it handles the rest. You focus on the analysis and the exploit chains.

### What's Next?

- Explore the full 75+ tool catalog for deep-dive analysis categories
- Chain BloodHound findings directly into SysReptor for automated pentest reporting
- Correlate BloodHound attack paths with Wazuh alerts for detection gap analysis
- Build automated AD security posture assessments that run through Claude
- Use the custom Cypher query tool for edge cases and novel attack research

---

## Resources

- [BloodHound CE](https://github.com/SpecterOps/BloodHound) — Industry-standard Active Directory security analysis
- [BloodHound-MCP-AI](https://github.com/MorDavid/BloodHound-MCP-AI) — MCP server for BloodHound (75+ tools)
- [Neo4j](https://neo4j.com/) — Graph database powering BloodHound
- [SharpHound](https://github.com/BloodHoundAD/SharpHound) — BloodHound data collector
- [MCP Protocol Specification](https://modelcontextprotocol.io/) — Learn about MCP
- [Claude Desktop](https://claude.ai/download) — Download Claude Desktop

---

## Acknowledgments

Special thanks to:
- **SpecterOps** for building BloodHound — the tool that changed AD security forever
- **MorDavid** for creating [BloodHound-MCP-AI](https://github.com/MorDavid/BloodHound-MCP-AI) — the first-ever BloodHound AI integration
- **Anthropic** for Claude and the Model Context Protocol
- The **Active Directory security community** for continuously advancing offensive and defensive research
- **You** for taking the time to check out this project

---

*Happy hacking, stay curious, and may your attack paths always lead to Domain Admin!* 🩸

**— Hackerobi**
