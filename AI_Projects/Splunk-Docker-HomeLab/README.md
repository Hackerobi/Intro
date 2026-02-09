# Deploying Splunk Enterprise in Docker: A Complete Home Lab Guide

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Beginner  
**Time Required:** 15-30 minutes

---

## Introduction

Every security professional needs a SIEM in their home lab. **Splunk Enterprise** is the industry standard for log management, threat detection, and operational intelligence — and running it in Docker means you can spin it up in minutes without touching your host system.

This guide walks you through deploying Splunk Enterprise in Docker with **full network isolation**, **persistent storage**, and **zero conflicts** with your existing containers. Whether you're practicing threat hunting, building detection rules, or feeding it data from Wazuh, this is your foundation.

By the end of this guide, you'll have:
- Splunk Enterprise running in an isolated Docker network
- Persistent volumes so your data survives container restarts
- The Web UI, management API, HEC, and forwarder ports all exposed and ready
- A `docker-compose.yml` for easy start/stop management

### What You'll Need

- **Docker** and Docker Compose installed
- **Linux workstation** (this guide uses Pop!_OS/Ubuntu)
- **8GB+ RAM** recommended (Splunk is hungry)
- Basic familiarity with the command line

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    Host Machine                          │
│                                                          │
│   ┌─────────────────────────────────────────────────┐    │
│   │              splunk-net (isolated)               │    │
│   │                                                  │    │
│   │   ┌──────────────────────────────────────────┐   │    │
│   │   │         Splunk Enterprise Container      │   │    │
│   │   │                                          │   │    │
│   │   │   Web UI ────────────► :8000 ──► :8090   │   │    │
│   │   │   REST API ──────────► :8089 ──► :8089   │   │    │
│   │   │   HEC ───────────────► :8088 ──► :8088   │   │    │
│   │   │   Forwarder Input ───► :9997 ──► :9997   │   │    │
│   │   │                                          │   │    │
│   │   │   /opt/splunk/var ──► splunk-var volume   │   │    │
│   │   │   /opt/splunk/etc ──► splunk-etc volume   │   │    │
│   │   └──────────────────────────────────────────┘   │    │
│   │                                                  │    │
│   └─────────────────────────────────────────────────┘    │
│                                                          │
│   Other containers (mcp-kali, wazuh-mcp, hexstrike...)   │
│   remain on default bridge — completely isolated         │
└──────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **Port 8090** maps to Splunk's internal port 8000 (because 8000 and 8080 were already in use by other containers)
- **splunk-net** is a dedicated Docker network — Splunk can't see or talk to your other containers unless you explicitly attach them
- **Named volumes** keep your indexed data and configuration persistent across restarts

---

## Part 1: Pre-Flight — Checking for Port Conflicts

Before deploying anything, check what's already running. This is critical when you have multiple Docker projects.

### List All Running Containers and Their Ports

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

### Check Specific Ports Splunk Needs

```bash
sudo ss -tlnp | grep -E '8000|8080|8089|8090|9997|8088'
```

Splunk uses these ports by default:

| Port | Purpose | Our Host Mapping |
|------|---------|------------------|
| 8000 | Splunk Web UI | **8090** (8000 was taken) |
| 8089 | Splunk Management / REST API | 8089 |
| 9997 | Forwarder Receiving | 9997 |
| 8088 | HTTP Event Collector (HEC) | 8088 |

> ⚠️ **In our environment**, ports 8000 (mcp-kali), 8080 (another container), and 18080 were already in use. That's why the Web UI is mapped to **8090** instead. Always check first!

---

## Part 2: Create the Isolated Network and Volumes

### Step 1: Create a Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/Docker_Splunk
cd ~/Documents/Docker_Projects/Docker_Splunk
```

### Step 2: Create the Docker Network

```bash
docker network create splunk-net
```

This creates a bridge network that is completely separate from the default Docker bridge. Your existing containers (mcp-kali, wazuh-mcp, hexstrike, etc.) won't be able to reach Splunk, and Splunk won't be able to reach them.

### Step 3: Create Persistent Volumes

```bash
docker volume create splunk-var
docker volume create splunk-etc
```

| Volume | Mounts To | Contains |
|--------|-----------|----------|
| `splunk-var` | `/opt/splunk/var` | Indexed data, logs, crash dumps |
| `splunk-etc` | `/opt/splunk/etc` | Configuration files, apps, saved searches |

These volumes persist even if you destroy and recreate the container. Your data is safe.

---

## Part 3: Deploy with Docker Compose

Using Docker Compose instead of a long `docker run` command avoids copy-paste issues and makes management much easier.

### Step 1: Create the docker-compose.yml

Save this file in `~/Documents/Docker_Projects/Docker_Splunk/docker-compose.yml`:

```yaml
services:
  splunk:
    image: splunk/splunk:latest
    container_name: splunk
    hostname: splunk
    restart: unless-stopped
    networks:
      - splunk-net
    ports:
      - "8090:8000"   # Splunk Web UI → http://localhost:8090
      - "8089:8089"   # Splunk management/REST API
      - "9997:9997"   # Forwarder receiving port
      - "8088:8088"   # HTTP Event Collector (HEC)
    volumes:
      - splunk-var:/opt/splunk/var
      - splunk-etc:/opt/splunk/etc
    environment:
      - SPLUNK_START_ARGS=--accept-license
      - SPLUNK_GENERAL_TERMS=--accept-sgt-current-at-splunk-com
      - SPLUNK_PASSWORD=Password01@!!!!

networks:
  splunk-net:
    name: splunk-net
    external: true

volumes:
  splunk-var:
    external: true
  splunk-etc:
    external: true
```

> ⚠️ **License Acceptance:** Starting with Splunk 10.x, you must include both `SPLUNK_START_ARGS=--accept-license` AND `SPLUNK_GENERAL_TERMS=--accept-sgt-current-at-splunk-com`. Without both, Splunk will not start. This indicates acceptance of the [Splunk General Terms](https://www.splunk.com/en_us/legal/splunk-general-terms.html).

> 🔒 **Password Requirements:** Must be 8+ characters. Change `Password01@!!!!` to something secure for anything beyond a home lab.

### Step 2: Start Splunk

```bash
cd ~/Documents/Docker_Projects/Docker_Splunk
docker compose up -d
```

### Step 3: Wait for Healthy Status

```bash
docker ps --filter name=splunk
```

Splunk takes **2-3 minutes** to fully initialize on first boot. Watch for the STATUS column to change from `starting` to `healthy`:

```
NAMES    STATUS                  PORTS
splunk   Up 2 minutes (healthy)  0.0.0.0:8088->8088/tcp, 0.0.0.0:8089->8089/tcp, 0.0.0.0:8090->8000/tcp, 0.0.0.0:9997->9997/tcp
```

### Step 4: Access the Web UI

Open your browser and navigate to:

**http://localhost:8090**

Login with:
- **Username:** `admin`
- **Password:** `Password01@!!!!` (or whatever you set in the compose file)

---

## Part 4: Verify Everything is Isolated

### Confirm Network Isolation

```bash
# Show which networks your containers are on
docker inspect splunk --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}'
# Output: splunk-net

# Compare with another container
docker inspect mcp-kali --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}'
# Output: bridge
```

Different networks = complete isolation. Splunk can't reach your other containers and vice versa.

### Confirm Volumes are Persistent

```bash
docker volume inspect splunk-var --format '{{.Mountpoint}}'
docker volume inspect splunk-etc --format '{{.Mountpoint}}'
```

---

## Part 5: Daily Management

### Start Splunk
```bash
cd ~/Documents/Docker_Projects/Docker_Splunk
docker compose up -d
```

### Stop Splunk
```bash
docker compose down
```

### View Logs
```bash
docker compose logs -f
```

### Restart After Config Changes
```bash
docker compose restart
```

### Check Container Health
```bash
docker ps --filter name=splunk
```

### Shell Into the Container
```bash
docker exec -it splunk bash
```

### Check Splunk Status from Inside
```bash
docker exec -it splunk /opt/splunk/bin/splunk status
```

---

## Part 6: Feeding Data into Splunk

Now that Splunk is running, here are the most common ways to get data into it.

### Option 1: HTTP Event Collector (HEC)

HEC is exposed on port **8088**. Enable it in the Splunk Web UI:

1. Go to **Settings → Data Inputs → HTTP Event Collector**
2. Click **Global Settings** and enable HEC
3. Create a new token

Then send data:

```bash
curl -k https://localhost:8088/services/collector/event \
  -H "Authorization: Splunk YOUR_HEC_TOKEN" \
  -d '{"event": "Hello from the command line!", "sourcetype": "manual"}'
```

### Option 2: Splunk Universal Forwarder

If you want to forward logs from other machines or VMs, set up a Universal Forwarder pointed at port **9997**:

```bash
# On the forwarder machine
./splunk add forward-server YOUR_HOST_IP:9997
```

### Option 3: Upload Files Directly

In the Splunk Web UI:
1. Go to **Settings → Add Data**
2. Choose **Upload**
3. Select your log file (JSON, CSV, syslog, etc.)

### Option 4: Monitor Docker Logs

You can mount Docker's log directory into Splunk for monitoring other container logs — but that would require attaching the container to those networks, which breaks our isolation model. For a home lab, HEC or file upload is usually simpler.

---

## Troubleshooting

### Port Already in Use

**Cause:** Another container or service is using the port.

**Solution:** Check with `sudo ss -tlnp | grep PORT_NUMBER` and remap in docker-compose.yml:
```yaml
ports:
  - "NEW_PORT:8000"  # Change left side only
```

### Container Keeps Restarting

**Cause:** Usually a password issue or license not accepted.

**Solution:**
```bash
docker compose logs --tail=50
```
Look for password requirement errors or license acceptance messages.

### "Container name already in use"

**Cause:** A stopped container with the same name exists.

**Solution:**
```bash
docker rm splunk
# or force remove if running
docker rm -f splunk
```

### Splunk Web UI Not Loading

**Cause:** Container hasn't finished starting yet.

**Solution:** Wait for `(healthy)` status. First boot can take 3+ minutes. Check with:
```bash
docker ps --filter name=splunk
```

### Out of Memory

**Cause:** Splunk is resource-intensive.

**Solution:** Ensure your host has at least 8GB RAM. You can also limit container resources in docker-compose.yml:
```yaml
services:
  splunk:
    deploy:
      resources:
        limits:
          memory: 4G
```

---

## Quick Reference

| Action | Command |
|--------|---------|
| Start Splunk | `docker compose up -d` |
| Stop Splunk | `docker compose down` |
| View logs | `docker compose logs -f` |
| Check health | `docker ps --filter name=splunk` |
| Shell access | `docker exec -it splunk bash` |
| Web UI | http://localhost:8090 |
| Login | `admin` / `Password01@!!!!` |

---

## What's Next?

- 🔗 **Connect Wazuh to Splunk** — Forward Wazuh alerts into Splunk for centralized visibility
- 🛡️ **Build Detection Rules** — Create custom correlation searches and alerts
- 📊 **Create Dashboards** — Visualize your home lab's security posture
- 🤖 **Splunk + MCP Integration** — Query Splunk through Claude AI (coming soon)
- 📥 **Ingest Cloud Logs** — Pull in AWS CloudTrail, Azure, or GCP logs

---

## Resources

- [Splunk Docker Hub](https://hub.docker.com/r/splunk/splunk/)
- [Splunk Docker Documentation](https://splunk.github.io/docker-splunk/)
- [Splunk Enterprise Documentation](https://docs.splunk.com/Documentation/Splunk/latest)
- [Splunk General Terms](https://www.splunk.com/en_us/legal/splunk-general-terms.html)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

---

*The foundation is set. Time to start hunting. 🛡️*

**— Hackerobi**
