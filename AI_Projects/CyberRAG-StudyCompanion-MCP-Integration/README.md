# Building a Cybersecurity Knowledge Base with AI: CyberRAG + StudyCompanion MCP Servers

**Author:** Hackerobi  
**Date:** February 2026  
**Difficulty:** Intermediate  
**Time Required:** 60-90 minutes

---

## Introduction

Imagine telling your AI assistant: *"Ingest the entire MITRE ATT&CK framework, all GTFOBins entries, OWASP cheatsheets, and hundreds of real bug bounty reports — then let me search across all of them with a single query."* And then later: *"Create a study note about Kerberoasting, generate flashcards, and show me where my knowledge gaps are."*

That's exactly what we built.

This guide walks you through creating **two custom MCP servers** from scratch that turn Claude Desktop into a cybersecurity knowledge engine:

- **CyberRAG** — Aggregates 10+ public cybersecurity sources into a unified, searchable vector database with 3,000+ knowledge items
- **StudyCompanion** — Your personal study assistant that tracks what you know, finds your weak spots, and generates flashcards and Q&A pairs

By the end of this guide, you'll have:
- 20 CyberRAG tools for ingesting, searching, and exporting cybersecurity knowledge
- 10 StudyCompanion tools for personal study management
- A vector database with semantic search across MITRE ATT&CK, GTFOBins, WADComs, OWASP, HackTricks, PayloadsAllTheThings, and multiple bug bounty sources
- RAG-optimized export for Open WebUI integration
- Flashcard generation, Q&A pairs, progress tracking, and gap analysis

### What Makes This Different?

There are plenty of cybersecurity resources out there. The problem isn't finding them — it's that they're scattered across dozens of GitHub repos, wikis, and websites. You end up with 15 browser tabs open, copy-pasting between tools, and losing track of what you've already studied.

CyberRAG solves this by **pulling everything into one place** and letting you search across all of it simultaneously. Ask about SQL injection and you get results from OWASP prevention guides, MITRE ATT&CK techniques, Bugcrowd severity ratings, HackerOne real-world reports, and HackTricks exploitation techniques — all in one query.

StudyCompanion solves the other half: **tracking what you actually know**. It auto-categorizes your notes across 15 cybersecurity domains, identifies gaps in your knowledge, and generates study materials so you can focus on what matters.

### What is MCP?

The Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external data sources and tools. Think of it as a universal adapter that lets Claude talk to your favorite platforms. In this case, we're building the platforms ourselves.

### What You'll Need

- **Linux workstation** (this guide uses Pop!_OS, but Ubuntu/Debian will work)
- **Docker Desktop** or Docker CE
- **Claude Desktop** application
- **Internet access** (for fetching public GitHub repositories during ingestion)
- Basic familiarity with command line and Docker

---

## Architecture Overview

```
┌─────────────────┐              ┌──────────────────────────────────────────────────┐
│  Claude Desktop │◄────────────►│  CyberRAG MCP Server (Docker)                    │
│                 │    stdio     │                                                  │
│  30 MCP Tools   │              │  ┌─────────────────┐  ┌───────────────────────┐  │
│                 │              │  │ Ingestion Layer  │  │ Search & Retrieval    │  │
│  • 20 CyberRAG │              │  │ • MITRE ATT&CK   │  │ • Semantic Search     │  │
│  • 10 Study    │              │  │ • GTFOBins        │  │ • Technique Lookup    │  │
│    Companion   │              │  │ • WADComs         │  │ • Attack Chain Map    │  │
│                 │              │  │ • HackTricks      │  │ • Topic Browser       │  │
│                 │              │  │ • OWASP Top 10    │  │                       │  │
│                 │              │  │ • OWASP Cheats    │  │ Export Layer          │  │
│                 │              │  │ • PayloadsAllThe  │  │ • Obsidian Markdown   │  │
│                 │              │  │ • Bug Bounty WU   │  │ • JSONL / QA Pairs    │  │
│                 │              │  │ • HackerOne Rpts  │  │ • Open WebUI RAG      │  │
│                 │              │  │ • HackerOne Tops  │  │                       │  │
│                 │              │  │ • HackerOne API   │  └───────────────────────┘  │
│                 │              │  │ • Bugcrowd VRT    │                            │
│                 │              │  └────────┬──────────┘                            │
│                 │              │           ▼                                       │
│                 │              │  ┌─────────────────────────────────────────────┐  │
│                 │              │  │              Storage Layer                  │  │
│                 │              │  │  SQLite (metadata) + ChromaDB (vectors)     │  │
│                 │              │  │  Docker Volume: cyberrag-data:/app/data     │  │
│                 │              │  └─────────────────────────────────────────────┘  │
│                 │              └──────────────────────────────────────────────────┘
│                 │
│                 │              ┌──────────────────────────────────────────────────┐
│                 │◄────────────►│  StudyCompanion MCP Server (Docker)              │
│                 │    stdio     │                                                  │
│                 │              │  ┌──────────────┐  ┌────────────────────────┐    │
│                 │              │  │ Note System   │  │ Study Tools            │    │
│                 │              │  │ • Add Notes   │  │ • Generate Q&A         │    │
│                 │              │  │ • Auto-Tag    │  │ • Create Flashcards    │    │
│                 │              │  │ • Search      │  │ • Track Progress       │    │
│                 │              │  │ • Summarize   │  │ • Find Gaps            │    │
│                 │              │  │ • Tag/Re-Tag  │  │ • Export Data          │    │
│                 │              │  └──────────────┘  └────────────────────────┘    │
│                 │              │                                                  │
│                 │              │  SQLite + ChromaDB                               │
│                 │              │  Docker Volume: studycompanion-data:/app/data    │
│                 │              └──────────────────────────────────────────────────┘
└─────────────────┘

                                ┌──────────────────────────────────────────────────┐
                                │  Open WebUI (Optional — Separate Host)           │
                                │                                                  │
                                │  Exported .md files uploaded as Knowledge Base    │
                                │  • Hybrid Search (BM25 + Vector)                 │
                                │  • Markdown Header Splitting                     │
                                │  • RAG-optimized chunking                        │
                                └──────────────────────────────────────────────────┘
```

**How it works:**

1. Both MCP servers run as Docker containers with persistent named volumes
2. Claude Desktop communicates via **stdio** transport (the most reliable on Linux)
3. CyberRAG fetches public cybersecurity data from GitHub repos, processes it, and stores it in SQLite (metadata) + ChromaDB (vector embeddings)
4. StudyCompanion stores your personal notes with auto-categorization and vector search
5. Optionally, CyberRAG exports RAG-optimized markdown for Open WebUI integration on another host

**Key Design Decisions:**
- **Built from scratch** — These aren't wrappers around existing MCP servers. We wrote every line of Python, designed the data models, and built the ingestion pipelines.
- **Docker containerized** — Each server is fully self-contained. No dependency conflicts, no system pollution.
- **Persistent volumes** — Your ingested data and study notes survive container restarts.
- **Content cleaning at ingestion** — HTML tags, image markdown, navigation boilerplate, and unicode noise are stripped before storage and embedding, so searches return clean, relevant content.

---

## Part 1: Building the CyberRAG Server

### Step 1: Create the Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/CyberRAG_MCP
cd ~/Documents/Docker_Projects/CyberRAG_MCP
```

### Step 2: Create the Files

You'll need exactly three files. Download them from the [`CyberRAG-MCP-Server/`](./CyberRAG-MCP-Server/) folder in this repository.

- **Dockerfile** — Container build instructions
- **requirements.txt** — Python dependencies
- **cyberrag_server.py** — The main server (~1,400 lines)

### Step 3: Verify Your Directory

```bash
ls ~/Documents/Docker_Projects/CyberRAG_MCP/
# Should show EXACTLY: Dockerfile  cyberrag_server.py  requirements.txt
```

> ⚠️ **Critical:** Make sure there are NO extra files in this directory. If you accidentally have `studycompanion_server.py` or other files in here, remove them before building.

### Step 4: Build the Docker Image

```bash
cd ~/Documents/Docker_Projects/CyberRAG_MCP
docker build --no-cache -t cyberrag-mcp:local .
```

### Step 5: Test the Container

```bash
echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}' | \
docker run -i --rm -v cyberrag-data:/app/data cyberrag-mcp:local
```

You should see JSON output with `"serverInfo":{"name":"CyberRAG"...}`.

---

## Part 2: Building the StudyCompanion Server

### Step 1: Create the Project Directory

```bash
mkdir -p ~/Documents/Docker_Projects/StudyCompanion_MCP
cd ~/Documents/Docker_Projects/StudyCompanion_MCP
```

### Step 2: Create the Files

Download from the [`StudyCompanion-MCP-Server/`](./StudyCompanion-MCP-Server/) folder in this repository.

- **Dockerfile** — Container build instructions
- **requirements.txt** — Python dependencies
- **studycompanion_server.py** — The main server (~580 lines)

### Step 3: Verify and Build

```bash
ls ~/Documents/Docker_Projects/StudyCompanion_MCP/
# Should show EXACTLY: Dockerfile  studycompanion_server.py  requirements.txt

cd ~/Documents/Docker_Projects/StudyCompanion_MCP
docker build --no-cache -t studycompanion-mcp:local .
```

> ⚠️ **Common Mistake:** If you see `COPY cyberrag_server.py .` in the build output, you have the wrong Dockerfile. The StudyCompanion Dockerfile should say `COPY studycompanion_server.py .`

---

## Part 3: Configuring Claude Desktop

### Add Both Servers

Edit `~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "cyberrag": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "cyberrag-data:/app/data", "cyberrag-mcp:local"]
    },
    "studycompanion": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "studycompanion-data:/app/data", "studycompanion-mcp:local"]
    }
  }
}
```

Restart Claude Desktop. You should see **30 new tools** — 20 from CyberRAG and 10 from StudyCompanion.

---

## Part 4: CyberRAG — Available Tools (20)

### Ingestion Tools (12)

| Tool | Source | Items |
|------|--------|-------|
| `ingest_mitre_attack` | [MITRE CTI](https://github.com/mitre/cti) | ~703 ATT&CK techniques |
| `ingest_gtfobins` | [GTFOBins](https://github.com/GTFOBins/GTFOBins.github.io) | ~469 Unix binaries |
| `ingest_wadcoms` | [WADComs](https://github.com/WADComs/WADComs.github.io) | ~100 Windows/AD commands |
| `ingest_hacktricks` | [HackTricks](https://github.com/HackTricks-wiki/hacktricks) | 54+ pentesting guides |
| `ingest_owasp` | [OWASP Top 10](https://github.com/OWASP/Top10) / [Cheatsheets](https://github.com/OWASP/CheatSheetSeries) | 18 + 109 pages |
| `ingest_payloads` | [PayloadsAllTheThings](https://github.com/swisskyrepo/PayloadsAllTheThings) | Payloads by category |
| `ingest_bugbounty_writeups` | [Awesome Bugbounty Writeups](https://github.com/devanshbatham/Awesome-Bugbounty-Writeups) | ~637 writeups |
| `ingest_hackerone_reports` | [HackerOne Reports](https://github.com/reddelexc/hackerone-reports) | 200+ disclosed reports |
| `ingest_hackerone_tops` | [HackerOne Reports](https://github.com/reddelexc/hackerone-reports) | 307 top reports |
| `ingest_hackerone_api` | HackerOne API | Requires credentials |
| `ingest_bugcrowd_taxonomy` | [Bugcrowd VRT](https://github.com/bugcrowd/vulnerability-rating-taxonomy) | ~539 severity ratings |

### Search, Export & Management (8)

| Tool | Description |
|------|-------------|
| `search_knowledge` | Semantic vector search across ALL sources |
| `browse_topics` | Browse sources, categories, and item counts |
| `get_technique` | MITRE ATT&CK lookup by ID or keyword |
| `get_attack_chain` | Map tactic-to-technique relationships |
| `export_obsidian` | Export as Obsidian markdown with wiki-links |
| `export_rag_dataset` | Export as JSONL or Q&A pairs |
| `export_openwebui` | Export RAG-optimized markdown for Open WebUI |
| `list_sources` / `refresh_source` | Manage ingested data |

---

## Part 5: StudyCompanion — Available Tools (10)

| Tool | Description |
|------|-------------|
| `add_note` | Save notes with auto-categorization across 15 cybersec domains and auto-tagging |
| `tag_content` | Re-tag or manually add tags to existing notes |
| `search_notes` | Semantic search across personal study notes |
| `generate_qa` | Generate Q&A pairs from a note for self-testing |
| `create_flashcards` | Build flashcard decks by topic (Anki-exportable) |
| `summarize_topic` | Synthesize everything you know about a topic |
| `track_progress` | Dashboard showing coverage across 15 categories |
| `find_gaps` | Identify weak areas and recommend study order |
| `export_study_data` | Export notes/QA/flashcards as JSONL or Obsidian markdown |
| `link_to_source` | Link notes to CyberRAG knowledge entries |

### The 15 Study Categories

`active-directory` · `web-exploitation` · `privilege-escalation` · `reconnaissance` · `enumeration` · `network-security` · `cryptography` · `malware-analysis` · `forensics` · `cloud-security` · `wireless-security` · `social-engineering` · `post-exploitation` · `defense-evasion` · `scripting-automation`

---

## Part 6: Example Conversations

### Populating Your Knowledge Base

> **You:** Ingest the MITRE ATT&CK enterprise framework, GTFOBins, WADComs, and the OWASP cheatsheets.
>
> **Claude:** ✅ Ingested 703 MITRE techniques, 469 GTFOBins, 100 WADComs, and 109 OWASP cheatsheets. Knowledge base: 1,381 items.

### Cross-Source Search

> **You:** Search for SUID privilege escalation techniques.
>
> **Claude:** Found results across multiple sources:
> 1. **GTFOBins: unzip** — SUID bit preservation for shell escalation (0.65)
> 2. **MITRE T1548.001 — Setuid and Setgid** — Adversary SUID abuse (0.62)
> 3. **GTFOBins: unsquashfs** — SUID extraction for privesc (0.61)

### Personal Study

> **You:** Add a study note about Kerberoasting — targets service accounts with SPNs, use Rubeus or Impacket, crack with hashcat 13100.
>
> **Claude:** ✅ Note saved — Category: active-directory — Tags: kerberoasting, rubeus, encryption, active-directory

> **You:** Where are my knowledge gaps?
>
> **Claude:** Missing 12 categories. Recommended study order: 1. web-exploitation, 2. privilege-escalation, 3. network-security

---

## Part 7: Open WebUI Integration (Optional)

Export your knowledge base for RAG-powered conversations on another host.

### Export and Transfer

```bash
# 1. In Claude Desktop: "Export all knowledge as Open WebUI markdown, max 5000 items"
# 2. Copy from Docker volume:
mkdir -p ~/Documents/CyberRAG_Export
docker run --rm -v cyberrag-data:/data -v ~/Documents/CyberRAG_Export:/out \
  alpine sh -c "cp -r /data/exports/openwebui_*/* /out/"

# 3. Transfer to Open WebUI host:
scp -r ~/Documents/CyberRAG_Export/ user@<OPENWEBUI_IP>:~/CyberRAG_Export/
```

### Upload and Configure

1. **Workspace → Knowledge → Create Collection → "CyberRAG"**
2. Upload all `.md` files
3. **Admin → Settings → Documents:** Chunk Size: 2000, Overlap: 200, Min Size: 1000, Markdown Header Splitting: ON, Hybrid Search: ON

---

## Part 8: Results

| Metric | Count |
|--------|-------|
| Total MCP Tools | 30 |
| Knowledge Sources | 12 |
| Total Knowledge Items | 3,094+ |
| Lines of Python | ~2,800 |
| Study Categories | 15 |

### Cross-Source Search in Action

Search for "SQL injection prevention" → results from OWASP prevention guide (0.72), injection cheatsheet (0.66), and input validation guide (0.59).

Search for "Kerberoasting" → MITRE T1558 (0.64), T1558.003 (0.61), and WADComs Kerbrute command (0.61).

**One query. Multiple sources. No tab-switching.**

---

## Part 9: Combining with Other MCP Tools

### BloodHound + CyberRAG
> Found Kerberoastable accounts → CyberRAG provides MITRE technique details + WADComs exploitation commands

### Wazuh + CyberRAG
> Pull alerts → cross-reference with MITRE ATT&CK techniques for context and detection guidance

### SysReptor + StudyCompanion
> Learn something during an engagement → study note + finding in the report, in one conversation

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No tools appear in Claude | Check `~/.config/Claude/logs/mcp-server-cyberrag.log` |
| StudyCompanion shows CyberRAG tools | Wrong Dockerfile — verify `COPY studycompanion_server.py .` |
| Ingestion returns 0 items | GitHub repo structure changed — check API response |
| Docker RST_STREAM error | `systemctl --user restart docker-desktop` then `docker builder prune -f` |
| Corrupted Dockerfile | Verify with `file Dockerfile` — should say "ASCII text" |
| First ingestion is slow | Normal — ChromaDB downloads 80MB embedding model on first use |

---

## Lessons Learned

1. **GTFOBins files have no `.md` extension** — `bash` not `bash.md`
2. **OWASP Top 10 needs `2021/docs/en/`** — not `2021/docs/`
3. **HackTricks moved to `src/` prefix** — `pentesting-web` became `src/pentesting-web`
4. **Python f-string nesting breaks before 3.12** — extract dict access to variable
5. **FastMCP removed `description` kwarg** — use `FastMCP("Name")` only
6. **Docker file corruption** — always verify with `file Dockerfile`
7. **Wrong file in wrong build context** — each Docker folder needs exactly 3 files

---

## Resources

- [MITRE ATT&CK](https://attack.mitre.org/) · [GTFOBins](https://gtfobins.github.io/) · [WADComs](https://wadcoms.github.io/) · [HackTricks](https://book.hacktricks.xyz/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/) · [OWASP Cheatsheets](https://cheatsheetseries.owasp.org/) · [PayloadsAllTheThings](https://github.com/swisskyrepo/PayloadsAllTheThings)
- [HackerOne](https://hackerone.com/hacktivity) · [Bugcrowd VRT](https://bugcrowd.com/vulnerability-rating-taxonomy) · [Open WebUI](https://github.com/open-webui/open-webui)
- [ChromaDB](https://www.trychroma.com/) · [MCP Protocol](https://modelcontextprotocol.io/) · [Claude Desktop](https://claude.ai/download) · [FastMCP](https://github.com/jlowin/fastmcp)

---

## Acknowledgments

Special thanks to **MITRE Corporation**, **GTFOBins** and **WADComs** contributors, **OWASP**, **Carlos Polop** (HackTricks), **swisskyrepo** (PayloadsAllTheThings), the **HackerOne** and **Bugcrowd** communities, **Anthropic** (Claude + MCP), the **ChromaDB** team, and the **cybersecurity community** for the "pay it forward" culture that makes projects like this possible.

---

*Happy hacking, stay curious, and build something that makes the next person's journey easier!* 🛡️

**— Hackerobi**