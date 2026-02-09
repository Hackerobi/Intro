#!/usr/bin/env python3
"""CyberRAG MCP Server - Cybersecurity Knowledge Base Aggregator"""
import os
import sys
import json
import logging
import hashlib
import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Configure logging to stderr (stdout is for MCP communication)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("cyberrag")

# === CONFIGURATION ===
DATA_DIR = Path(os.environ.get("CYBERRAG_DATA_DIR", "/app/data"))
SQLITE_PATH = DATA_DIR / "sqlite" / "cyberrag.db"
CHROMADB_DIR = str(DATA_DIR / "chromadb")
OBSIDIAN_DIR = DATA_DIR / "obsidian_export"
EXPORTS_DIR = DATA_DIR / "exports"

# Ensure directories exist
for d in [DATA_DIR / "sqlite", DATA_DIR / "chromadb", OBSIDIAN_DIR, EXPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === MCP SERVER ===
mcp = FastMCP("CyberRAG")

# === SQLITE SETUP ===
def get_db():
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL,
        category TEXT DEFAULT '',
        subcategory TEXT DEFAULT '',
        tags TEXT DEFAULT '[]',
        mitre_id TEXT DEFAULT '',
        url TEXT DEFAULT '',
        content_hash TEXT DEFAULT '',
        created_at TEXT DEFAULT '',
        updated_at TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sources (
        name TEXT PRIMARY KEY,
        last_ingested TEXT DEFAULT '',
        item_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ready'
    )""")
    conn.commit()
    return conn

# === CHROMADB SETUP ===
_collection = None

def get_collection():
    global _collection
    if _collection is None:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=CHROMADB_DIR)
            _collection = client.get_or_create_collection(
                name="cyberrag",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB collection ready: {_collection.count()} items")
        except Exception as e:
            logger.error(f"ChromaDB init error: {e}")
            return None
    return _collection

# === HELPER FUNCTIONS ===
def content_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]

def clean_for_rag(text):
    """Clean content for optimal RAG embedding quality - removes noise that wastes tokens."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove image markdown references (can't be embedded meaningfully)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove common navigation/boilerplate
    text = re.sub(r'(?i)(table of contents|back to top|click here to|read more\.\.\.)', '', text)
    # Normalize unicode whitespace
    text = re.sub(r'[\xa0\u200b\u2028\u2029]', ' ', text)
    # Remove zero-width characters
    text = re.sub(r'[\u200b-\u200f\u2060\ufeff]', '', text)
    return text.strip()

def store_knowledge(item_id, title, content, source, category="", subcategory="", tags=None, mitre_id="", url=""):
    if tags is None:
        tags = []
    now = datetime.now(timezone.utc).isoformat()
    # Clean content for RAG quality before storage
    content = clean_for_rag(content)
    c_hash = content_hash(content)
    truncated = content[:15000]

    conn = get_db()
    try:
        conn.execute("""INSERT OR REPLACE INTO knowledge
            (id, title, content, source, category, subcategory, tags, mitre_id, url, content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_id, title, truncated, source, category, subcategory, json.dumps(tags), mitre_id, url, c_hash, now, now))
        conn.commit()
    finally:
        conn.close()

    collection = get_collection()
    if collection:
        try:
            collection.upsert(
                ids=[item_id],
                documents=[truncated[:8000]],
                metadatas=[{
                    "title": title,
                    "source": source,
                    "category": category,
                    "subcategory": subcategory,
                    "mitre_id": mitre_id,
                    "url": url
                }]
            )
        except Exception as e:
            logger.error(f"ChromaDB upsert error: {e}")

def update_source(name, count):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute("""INSERT OR REPLACE INTO sources (name, last_ingested, item_count, status)
            VALUES (?, ?, ?, 'complete')""", (name, now, count))
        conn.commit()
    finally:
        conn.close()

async def fetch_json(url):
    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

async def fetch_text(url):
    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

# === INGESTION TOOLS ===

@mcp.tool()
async def ingest_mitre_attack(domain: str = "enterprise") -> str:
    """Ingest MITRE ATT&CK framework techniques and tactics from the official STIX data. Domain can be enterprise, mobile, or ics."""
    try:
        url = f"https://raw.githubusercontent.com/mitre/cti/master/{domain}-attack/{domain}-attack.json"
        logger.info(f"Fetching MITRE ATT&CK {domain}...")
        data = await fetch_json(url)

        count = 0
        for obj in data.get("objects", []):
            if obj.get("type") == "attack-pattern" and not obj.get("revoked", False):
                ext_refs = obj.get("external_references", [])
                mitre_id = ""
                url_ref = ""
                for ref in ext_refs:
                    if ref.get("source_name") == "mitre-attack":
                        mitre_id = ref.get("external_id", "")
                        url_ref = ref.get("url", "")
                        break

                name = obj.get("name", "Unknown")
                desc = obj.get("description", "No description available.")
                phases = [p.get("phase_name", "") for p in obj.get("kill_chain_phases", [])]
                platforms = obj.get("x_mitre_platforms", [])

                full_content = f"# {name}\n\n**MITRE ID:** {mitre_id}\n"
                full_content += f"**Tactics:** {', '.join(phases)}\n"
                full_content += f"**Platforms:** {', '.join(platforms)}\n\n"
                full_content += desc

                item_id = f"mitre-{mitre_id}" if mitre_id else f"mitre-{content_hash(name)}"
                tags = phases + platforms + ["mitre-attack", domain]

                store_knowledge(
                    item_id=item_id,
                    title=f"{mitre_id} - {name}" if mitre_id else name,
                    content=full_content,
                    source="mitre-attack",
                    category="attack-pattern",
                    subcategory=phases[0] if phases else "",
                    tags=tags,
                    mitre_id=mitre_id,
                    url=url_ref
                )
                count += 1

        update_source("mitre-attack", count)
        return f"✅ Ingested {count} MITRE ATT&CK techniques from {domain} domain."
    except Exception as e:
        logger.error(f"MITRE ingest error: {e}")
        return f"❌ Error ingesting MITRE ATT&CK: {str(e)}"


@mcp.tool()
async def ingest_gtfobins(max_items: str = "500") -> str:
    """Ingest GTFOBins - Unix binaries that can be used for privilege escalation and security bypasses."""
    try:
        max_n = int(max_items)
        api_url = "https://api.github.com/repos/GTFOBins/GTFOBins.github.io/contents/_gtfobins"
        logger.info("Fetching GTFOBins index...")
        files = await fetch_json(api_url)

        count = 0
        for f in files[:max_n]:
            if f.get("type") != "file":
                continue
            binary_name = f["name"].replace(".md", "")
            try:
                raw_url = f["download_url"]
                if not raw_url:
                    continue
                content = await fetch_text(raw_url)

                functions = []
                for match in re.findall(r"functions:\s*\n((?:\s+-\s+\w+\n?)+)", content):
                    functions.extend(re.findall(r"-\s+(\w+)", match))

                tags = ["gtfobins", "privilege-escalation", "linux"] + functions
                item_id = f"gtfo-{binary_name}"

                store_knowledge(
                    item_id=item_id,
                    title=f"GTFOBins: {binary_name}",
                    content=content,
                    source="gtfobins",
                    category="privilege-escalation",
                    subcategory=functions[0] if functions else "misc",
                    tags=tags,
                    url=f"https://gtfobins.github.io/gtfobins/{binary_name}/"
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to fetch {binary_name}: {e}")
                continue

        update_source("gtfobins", count)
        return f"✅ Ingested {count} GTFOBins entries."
    except Exception as e:
        logger.error(f"GTFOBins ingest error: {e}")
        return f"❌ Error ingesting GTFOBins: {str(e)}"


@mcp.tool()
async def ingest_hacktricks(section: str = "pentesting-web") -> str:
    """Ingest HackTricks pentesting guides from GitHub. Sections: pentesting-web, linux-hardening, windows-hardening, network-services-pentesting, generic-methodologies-and-resources."""
    try:
        api_url = f"https://api.github.com/repos/HackTricks-wiki/hacktricks/contents/src/{section}"
        logger.info(f"Fetching HackTricks section: {section}...")
        files = await fetch_json(api_url)

        count = 0
        for f in files:
            if f.get("type") != "file" or not f["name"].endswith(".md"):
                continue
            try:
                content = await fetch_text(f["download_url"])
                topic = f["name"].replace(".md", "").replace("-", " ").title()
                item_id = f"ht-{section}-{content_hash(f['name'])}"

                store_knowledge(
                    item_id=item_id,
                    title=f"HackTricks: {topic}",
                    content=content,
                    source="hacktricks",
                    category=section,
                    subcategory=topic.lower(),
                    tags=["hacktricks", section, "pentesting"],
                    url=f["html_url"]
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to fetch {f['name']}: {e}")
                continue

        update_source(f"hacktricks-{section}", count)
        return f"✅ Ingested {count} HackTricks pages from {section}."
    except Exception as e:
        logger.error(f"HackTricks ingest error: {e}")
        return f"❌ Error ingesting HackTricks: {str(e)}"


@mcp.tool()
async def ingest_owasp(resource: str = "top10") -> str:
    """Ingest OWASP resources. Resource options: top10, cheatsheets."""
    try:
        if resource == "top10":
            api_url = "https://api.github.com/repos/OWASP/Top10/contents/2021/docs/en"
            source_name = "owasp-top10"
        elif resource == "cheatsheets":
            api_url = "https://api.github.com/repos/OWASP/CheatSheetSeries/contents/cheatsheets"
            source_name = "owasp-cheatsheets"
        else:
            return f"❌ Unknown resource: {resource}. Use 'top10' or 'cheatsheets'."

        logger.info(f"Fetching OWASP {resource}...")
        files = await fetch_json(api_url)

        count = 0
        for f in files:
            if not f["name"].endswith(".md"):
                continue
            try:
                content = await fetch_text(f["download_url"])
                topic = f["name"].replace(".md", "").replace("_", " ").replace("-", " ").title()
                item_id = f"owasp-{resource}-{content_hash(f['name'])}"

                store_knowledge(
                    item_id=item_id,
                    title=f"OWASP: {topic}",
                    content=content,
                    source=source_name,
                    category="web-security",
                    subcategory=resource,
                    tags=["owasp", resource, "web-security", "appsec"],
                    url=f["html_url"]
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to fetch {f['name']}: {e}")
                continue

        update_source(source_name, count)
        return f"✅ Ingested {count} OWASP {resource} pages."
    except Exception as e:
        logger.error(f"OWASP ingest error: {e}")
        return f"❌ Error ingesting OWASP: {str(e)}"


@mcp.tool()
async def ingest_payloads(category: str = "SQL Injection") -> str:
    """Ingest PayloadsAllTheThings exploit content by category. Categories include: SQL Injection, XSS Injection, Command Injection, Directory Traversal, Server Side Request Forgery, XXE Injection, and many more."""
    try:
        cat_path = category.replace(" ", "%20")
        api_url = f"https://api.github.com/repos/swisskyrepo/PayloadsAllTheThings/contents/{cat_path}"
        logger.info(f"Fetching PayloadsAllTheThings: {category}...")
        files = await fetch_json(api_url)

        count = 0
        for f in files:
            if not f["name"].endswith(".md"):
                continue
            try:
                content = await fetch_text(f["download_url"])
                topic = f["name"].replace(".md", "").replace("-", " ").title()
                fname = f["name"]
                item_id = f"payload-{content_hash(category + '-' + fname)}"

                store_knowledge(
                    item_id=item_id,
                    title=f"Payload: {category} - {topic}",
                    content=content,
                    source="payloads-all-the-things",
                    category="exploits",
                    subcategory=category.lower(),
                    tags=["payloads", category.lower().replace(" ", "-"), "exploit", "offensive"],
                    url=f["html_url"]
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to fetch {f['name']}: {e}")
                continue

        update_source(f"payloads-{category.lower().replace(' ', '-')}", count)
        return f"✅ Ingested {count} payload files from {category}."
    except Exception as e:
        logger.error(f"Payloads ingest error: {e}")
        return f"❌ Error ingesting PayloadsAllTheThings: {str(e)}"


@mcp.tool()
async def ingest_wadcoms(max_items: str = "500") -> str:
    """Ingest WADComs - Windows/Active Directory interactive cheat sheet with attack commands for enumeration, exploitation, and lateral movement. Similar to GTFOBins but for Windows/AD environments."""
    try:
        max_n = int(max_items)
        api_url = "https://api.github.com/repos/WADComs/WADComs.github.io/contents/_wadcoms"
        logger.info("Fetching WADComs index...")
        files = await fetch_json(api_url)

        count = 0
        for f in files[:max_n]:
            if f.get("type") != "file" or not f["name"].endswith(".md"):
                continue
            try:
                content = await fetch_text(f["download_url"])
                tool_name = f["name"].replace(".md", "")

                # Parse YAML frontmatter for structured metadata
                description = ""
                command = ""
                items = []
                services = []
                os_info = []
                attack_type = []

                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        frontmatter = parts[1]
                        # Extract fields from YAML
                        desc_match = re.search(r'description:\s*\|\s*\n(.*?)(?=\n\w|\ncommand:)', frontmatter, re.DOTALL)
                        if desc_match:
                            description = desc_match.group(1).strip()
                        cmd_match = re.search(r'command:\s*\|\s*\n(.*?)(?=\n\w|\Z)', frontmatter, re.DOTALL)
                        if cmd_match:
                            command = cmd_match.group(1).strip()
                        items_match = re.search(r'items:\s*\n((?:\s*-\s*.+\n?)+)', frontmatter)
                        if items_match:
                            items = re.findall(r'-\s*(.+)', items_match.group(1))
                        services_match = re.search(r'services:\s*\n((?:\s*-\s*.+\n?)+)', frontmatter)
                        if services_match:
                            services = re.findall(r'-\s*(.+)', services_match.group(1))
                        os_match = re.search(r'OS:\s*\n((?:\s*-\s*.+\n?)+)', frontmatter)
                        if os_match:
                            os_info = re.findall(r'-\s*(.+)', os_match.group(1))
                        attack_match = re.search(r'attack_type:\s*\n((?:\s*-\s*.+\n?)+)', frontmatter)
                        if attack_match:
                            attack_type = re.findall(r'-\s*(.+)', attack_match.group(1))

                # Build rich content for embedding
                rich_content = f"# WADComs: {tool_name}\n\n"
                if description:
                    rich_content += f"## Description\n{description}\n\n"
                if command:
                    rich_content += f"## Command\n```\n{command}\n```\n\n"
                if items:
                    rich_content += f"## Tools\n{', '.join(items)}\n\n"
                if services:
                    rich_content += f"## Services\n{', '.join(services)}\n\n"
                if os_info:
                    rich_content += f"## OS\n{', '.join(os_info)}\n\n"
                if attack_type:
                    rich_content += f"## Attack Type\n{', '.join(attack_type)}\n\n"

                tags = ["wadcoms", "active-directory", "windows"] + [i.lower().strip() for i in items[:5]] + [s.lower().strip() for s in services[:5]] + [a.lower().strip() for a in attack_type[:3]]
                item_id = f"wadcoms-{content_hash(tool_name)}"

                store_knowledge(
                    item_id=item_id,
                    title=f"WADComs: {tool_name}",
                    content=rich_content if rich_content.strip() != f"# WADComs: {tool_name}" else content,
                    source="wadcoms",
                    category="active-directory",
                    subcategory=attack_type[0].lower().strip() if attack_type else "general",
                    tags=tags,
                    url=f["html_url"]
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to fetch WADComs {f['name']}: {e}")
                continue

        update_source("wadcoms", count)
        return f"✅ Ingested {count} WADComs entries (Windows/AD attack commands)."
    except Exception as e:
        logger.error(f"WADComs ingest error: {e}")
        return f"❌ Error ingesting WADComs: {str(e)}"


# === BUG BOUNTY INGESTION TOOLS ===

@mcp.tool()
async def ingest_bugbounty_writeups() -> str:
    """Ingest Awesome-Bugbounty-Writeups - curated collection of hundreds of bug bounty writeup links organized by vulnerability type (XSS, CSRF, SQLi, SSRF, IDOR, RCE, LFI, etc.)."""
    try:
        url = "https://raw.githubusercontent.com/devanshbatham/Awesome-Bugbounty-Writeups/master/README.md"
        logger.info("Fetching Awesome-Bugbounty-Writeups...")
        content = await fetch_text(url)

        # Parse sections and links
        current_section = "general"
        count = 0
        section_items = {}

        for line in content.split("\n"):
            line = line.strip()
            # Detect section headers
            if line.startswith("## "):
                current_section = line.replace("## ", "").strip()
                if current_section not in section_items:
                    section_items[current_section] = []
            # Detect writeup links
            elif line.startswith("- [") and "](http" in line:
                match = re.match(r'-\s*\[([^\]]+)\]\(([^)]+)\)', line)
                if match:
                    title = match.group(1)
                    link = match.group(2)
                    section_items.setdefault(current_section, []).append((title, link))

        # Store each section as a knowledge item with all its writeup links
        for section, items in section_items.items():
            if not items:
                continue
            writeup_list = "\n".join([f"- [{t}]({u})" for t, u in items])
            full_content = f"# Bug Bounty Writeups: {section}\n\n"
            full_content += f"**{len(items)} curated writeups for {section}**\n\n"
            full_content += writeup_list

            # Map section names to vuln type tags
            section_lower = section.lower()
            tags = ["bugbounty", "writeup", "disclosure"]
            for keyword in ["xss", "csrf", "sqli", "sql injection", "ssrf", "idor", "rce", "lfi", "rfi", "xxe", "clickjacking", "subdomain takeover", "dos", "authentication bypass", "cors", "race condition", "android"]:
                if keyword in section_lower:
                    tags.append(keyword.replace(" ", "-"))

            item_id = f"bb-writeup-{content_hash(section)}"
            store_knowledge(
                item_id=item_id,
                title=f"Bug Bounty Writeups: {section}",
                content=full_content,
                source="awesome-bugbounty-writeups",
                category="bug-bounty",
                subcategory=section.lower(),
                tags=tags,
                url="https://github.com/devanshbatham/Awesome-Bugbounty-Writeups"
            )
            count += 1

            # Also store individual writeups for granular search
            for title, link in items:
                ind_id = f"bb-writeup-{content_hash(title + link)}"
                ind_content = f"# {title}\n\n**Category:** {section}\n**URL:** {link}\n\nBug bounty writeup covering {section} vulnerability type."
                store_knowledge(
                    item_id=ind_id,
                    title=title,
                    content=ind_content,
                    source="awesome-bugbounty-writeups",
                    category="bug-bounty",
                    subcategory=section.lower(),
                    tags=tags + [t.lower() for t in title.split()[:5]],
                    url=link
                )
                count += 1

        update_source("awesome-bugbounty-writeups", count)
        return f"✅ Ingested {count} bug bounty writeups across {len(section_items)} vulnerability categories."
    except Exception as e:
        logger.error(f"Bugbounty writeups ingest error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def ingest_hackerone_reports(max_items: str = "200") -> str:
    """Ingest full disclosed HackerOne bug bounty reports from the community archive (1000+ reports covering XSS, RCE, SSRF, IDOR, SQLi, and more)."""
    try:
        max_n = int(max_items)
        api_url = "https://api.github.com/repos/marcotuliocnd/bugbounty-disclosed-reports/contents/reports"
        logger.info("Fetching HackerOne disclosed reports index...")
        files = await fetch_json(api_url)

        count = 0
        for f in files[:max_n]:
            if not f["name"].endswith(".md"):
                continue
            try:
                content = await fetch_text(f["download_url"])
                # Parse report ID and title from filename: 1234567_Title_Here.md
                fname = f["name"].replace(".md", "")
                parts = fname.split("_", 1)
                report_id = parts[0] if parts[0].isdigit() else ""
                report_title = parts[1].replace("_", " ") if len(parts) > 1 else fname

                # Auto-detect vulnerability type from content
                content_lower = content.lower()
                tags = ["hackerone", "bug-bounty", "disclosed"]
                vuln_types = {
                    "xss": ["xss", "cross-site scripting", "script injection"],
                    "sqli": ["sql injection", "sqli", "sql query"],
                    "ssrf": ["ssrf", "server-side request forgery"],
                    "idor": ["idor", "insecure direct object"],
                    "rce": ["rce", "remote code execution", "command injection"],
                    "csrf": ["csrf", "cross-site request forgery"],
                    "lfi": ["lfi", "local file inclusion", "path traversal", "directory traversal"],
                    "xxe": ["xxe", "xml external entity"],
                    "open-redirect": ["open redirect", "url redirect"],
                    "info-disclosure": ["information disclosure", "sensitive data", "data exposure"],
                    "auth-bypass": ["authentication bypass", "authorization bypass", "access control"],
                    "subdomain-takeover": ["subdomain takeover"],
                    "dos": ["denial of service", "dos", "redos"],
                    "race-condition": ["race condition", "toctou"],
                    "deserialization": ["deserialization", "insecure deserialization"],
                    "ssti": ["template injection", "ssti"],
                    "graphql": ["graphql"],
                    "cors": ["cors", "cross-origin"],
                    "upload": ["file upload", "unrestricted upload"],
                    "prototype-pollution": ["prototype pollution"]
                }
                detected_category = "general"
                for vuln_tag, keywords in vuln_types.items():
                    for kw in keywords:
                        if kw in content_lower:
                            tags.append(vuln_tag)
                            if detected_category == "general":
                                detected_category = vuln_tag
                            break

                item_id = f"h1-report-{report_id}" if report_id else f"h1-report-{content_hash(fname)}"
                store_knowledge(
                    item_id=item_id,
                    title=f"HackerOne: {report_title}",
                    content=content,
                    source="hackerone-disclosed",
                    category=detected_category,
                    subcategory="disclosed-report",
                    tags=list(set(tags)),
                    url=f"https://hackerone.com/reports/{report_id}" if report_id else f["html_url"]
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to fetch report {f['name']}: {e}")
                continue

        update_source("hackerone-disclosed", count)
        return f"✅ Ingested {count} disclosed HackerOne reports."
    except Exception as e:
        logger.error(f"HackerOne reports ingest error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def ingest_hackerone_tops() -> str:
    """Ingest top-rated HackerOne reports organized by bug type (XSS, SQLi, SSRF, RCE, CSRF, IDOR, etc.) - 27 categories with ranked reports including upvotes and bounty amounts."""
    try:
        api_url = "https://api.github.com/repos/reddelexc/hackerone-reports/contents/tops_by_bug_type"
        logger.info("Fetching HackerOne tops by bug type...")
        files = await fetch_json(api_url)

        count = 0
        for f in files:
            if not f["name"].endswith(".md"):
                continue
            try:
                content = await fetch_text(f["download_url"])
                bug_type = f["name"].replace("TOP", "").replace(".md", "").strip()
                bug_type_readable = bug_type.replace("_", " ").title()

                # Parse individual report entries from the markdown
                reports_found = []
                for line in content.split("\n"):
                    match = re.search(r'\[([^\]]+)\]\(https://hackerone\.com/reports/(\d+)\)[^-]*-\s*(\d+)\s*upvotes?,\s*\$?([\d,]+)', line)
                    if match:
                        reports_found.append({
                            "title": match.group(1),
                            "report_id": match.group(2),
                            "upvotes": int(match.group(3)),
                            "bounty": match.group(4)
                        })

                # Store the full category file
                item_id = f"h1-top-{content_hash(bug_type)}"
                tags = ["hackerone", "bug-bounty", "top-reports", bug_type.lower().replace(" ", "-")]

                store_knowledge(
                    item_id=item_id,
                    title=f"Top HackerOne Reports: {bug_type_readable}",
                    content=content,
                    source="hackerone-tops",
                    category="bug-bounty",
                    subcategory=bug_type.lower(),
                    tags=tags,
                    url=f["html_url"]
                )
                count += 1

                # Also store top 10 individual reports for granular search
                for report in reports_found[:10]:
                    r_id = f"h1-top-{report['report_id']}"
                    r_content = f"# {report['title']}\n\n"
                    r_content += f"**Bug Type:** {bug_type_readable}\n"
                    r_content += f"**Upvotes:** {report['upvotes']}\n"
                    r_content += f"**Bounty:** ${report['bounty']}\n"
                    r_content += f"**Report:** https://hackerone.com/reports/{report['report_id']}\n"

                    store_knowledge(
                        item_id=r_id,
                        title=report["title"],
                        content=r_content,
                        source="hackerone-tops",
                        category=bug_type.lower(),
                        subcategory="top-report",
                        tags=tags + ["top-rated"],
                        url=f"https://hackerone.com/reports/{report['report_id']}"
                    )
                    count += 1

            except Exception as e:
                logger.warning(f"Failed to fetch {f['name']}: {e}")
                continue

        update_source("hackerone-tops", count)
        return f"✅ Ingested {count} items from {len(files)} HackerOne bug type categories."
    except Exception as e:
        logger.error(f"HackerOne tops ingest error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def ingest_hackerone_api(h1_username: str = "", h1_api_token: str = "", max_pages: str = "5") -> str:
    """Ingest disclosed reports directly from HackerOne's official API with structured severity, CWE, and bounty data. Requires HackerOne API credentials (free hacker account)."""
    try:
        if not h1_username or not h1_api_token:
            return ("❌ HackerOne API credentials required.\n\n"
                    "To get them (free):\n"
                    "1. Sign up at https://hackerone.com/users/sign_up\n"
                    "2. Go to Settings → API Token\n"
                    "3. Generate a token\n"
                    "4. Call this tool with your username and token\n\n"
                    "Or use ingest_hackerone_reports for the GitHub archive (no credentials needed).")

        import httpx
        from base64 import b64encode
        pages = int(max_pages)
        auth_header = b64encode(f"{h1_username}:{h1_api_token}".encode()).decode()
        base_url = "https://api.hackerone.com/v1/hackers/hacktivity"
        count = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, pages + 1):
                params = {
                    "queryString": "disclosed:true",
                    "page[number]": page,
                    "page[size]": 25
                }
                headers = {
                    "Authorization": f"Basic {auth_header}",
                    "Accept": "application/json"
                }
                logger.info(f"Fetching HackerOne API page {page}/{pages}...")

                try:
                    resp = await client.get(base_url, params=params, headers=headers)
                    if resp.status_code == 401:
                        return "❌ Invalid HackerOne credentials. Check your username and API token."
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning(f"API page {page} failed: {e}")
                    break

                reports = data.get("data", [])
                if not reports:
                    break

                for report in reports:
                    attrs = report.get("attributes", {})
                    rels = report.get("relationships", {})

                    title = attrs.get("title", "Unknown")
                    report_id = str(report.get("id", ""))
                    severity = attrs.get("severity_rating", "unknown")
                    cwe = attrs.get("cwe", "")
                    cve_ids = attrs.get("cve_ids", [])
                    bounty = attrs.get("total_awarded_amount", 0)
                    votes = attrs.get("votes", 0)
                    url = attrs.get("url", "")
                    disclosed_at = attrs.get("disclosed_at", "")

                    # Get program and reporter info
                    program_data = rels.get("program", {}).get("data", {}).get("attributes", {})
                    program_name = program_data.get("name", "Unknown")
                    reporter_data = rels.get("reporter", {}).get("data", {}).get("attributes", {})
                    reporter = reporter_data.get("username", "anonymous")

                    # Get AI summary if available
                    summary_data = rels.get("report_generated_content", {}).get("data", {}).get("attributes", {})
                    summary = summary_data.get("hacktivity_summary", "")

                    full_content = f"# {title}\n\n"
                    full_content += f"**Program:** {program_name}\n"
                    full_content += f"**Severity:** {severity}\n"
                    full_content += f"**CWE:** {cwe}\n" if cwe else ""
                    full_content += f"**CVEs:** {', '.join(cve_ids)}\n" if cve_ids else ""
                    full_content += f"**Bounty:** ${bounty}\n" if bounty else ""
                    full_content += f"**Upvotes:** {votes}\n"
                    full_content += f"**Reporter:** {reporter}\n"
                    full_content += f"**Disclosed:** {disclosed_at}\n"
                    full_content += f"**URL:** {url}\n"
                    if summary:
                        full_content += f"\n## Summary\n{summary}\n"

                    tags = ["hackerone", "bug-bounty", "api-sourced", severity]
                    if cwe:
                        tags.append(cwe.lower().replace(" ", "-"))

                    item_id = f"h1-api-{report_id}"
                    store_knowledge(
                        item_id=item_id,
                        title=f"H1/{program_name}: {title}",
                        content=full_content,
                        source="hackerone-api",
                        category=cwe.lower() if cwe else severity,
                        subcategory=program_name.lower(),
                        tags=tags,
                        url=url
                    )
                    count += 1

        update_source("hackerone-api", count)
        return f"✅ Ingested {count} disclosed reports from HackerOne API ({pages} pages)."
    except Exception as e:
        logger.error(f"HackerOne API ingest error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def ingest_bugcrowd_taxonomy() -> str:
    """Ingest Bugcrowd's Vulnerability Rating Taxonomy (VRT) - the industry-standard classification mapping vulnerability types to severity ratings (P1-P5), including AI security, cloud, and web categories."""
    try:
        url = "https://raw.githubusercontent.com/bugcrowd/vulnerability-rating-taxonomy/master/vulnerability-rating-taxonomy.json"
        logger.info("Fetching Bugcrowd VRT...")
        data = await fetch_json(url)

        count = 0

        def process_vrt_node(node, parent_path=""):
            nonlocal count
            name = node.get("name", "Unknown")
            node_id = node.get("id", "")
            priority = node.get("priority", None)
            path = f"{parent_path}/{name}" if parent_path else name

            # Build content
            content = f"# Bugcrowd VRT: {path}\n\n"
            content += f"**ID:** {node_id}\n"
            if priority:
                content += f"**Priority:** {priority}\n"
            content += f"**Full Path:** {path}\n\n"

            # Map priority to severity for context
            priority_map = {
                1: "Critical (P1)", 2: "High (P2)", 3: "Medium (P3)",
                4: "Low (P4)", 5: "Informational (P5)"
            }
            if priority and isinstance(priority, int):
                content += f"**Severity:** {priority_map.get(priority, f'P{priority}')}\n"

            tags = ["bugcrowd", "vrt", "taxonomy", "severity-rating"]
            if priority:
                tags.append(f"p{priority}")
            # Add category-level tags
            top_cat = path.split("/")[0].lower().replace(" ", "-") if path else ""
            if top_cat:
                tags.append(top_cat)

            item_id = f"bc-vrt-{content_hash(node_id or path)}"
            store_knowledge(
                item_id=item_id,
                title=f"VRT: {path}",
                content=content,
                source="bugcrowd-vrt",
                category="taxonomy",
                subcategory=top_cat,
                tags=tags,
                url="https://bugcrowd.com/vulnerability-rating-taxonomy"
            )
            count += 1

            # Recurse into children
            for child in node.get("children", []):
                process_vrt_node(child, path)

        # VRT JSON has a "content" array at root
        for category in data.get("content", data if isinstance(data, list) else []):
            process_vrt_node(category)

        # Also fetch the CHANGELOG for context on what's new
        try:
            changelog_url = "https://raw.githubusercontent.com/bugcrowd/vulnerability-rating-taxonomy/master/CHANGELOG.md"
            changelog = await fetch_text(changelog_url)
            store_knowledge(
                item_id="bc-vrt-changelog",
                title="Bugcrowd VRT Changelog",
                content=changelog[:15000],
                source="bugcrowd-vrt",
                category="taxonomy",
                subcategory="changelog",
                tags=["bugcrowd", "vrt", "changelog", "updates"],
                url="https://github.com/bugcrowd/vulnerability-rating-taxonomy/blob/master/CHANGELOG.md"
            )
            count += 1
        except Exception:
            pass

        update_source("bugcrowd-vrt", count)
        return f"✅ Ingested {count} Bugcrowd VRT entries across all vulnerability categories."
    except Exception as e:
        logger.error(f"Bugcrowd VRT ingest error: {e}")
        return f"❌ Error: {str(e)}"


# === SEARCH & BROWSE TOOLS ===

@mcp.tool()
async def search_knowledge(query: str = "", top_k: str = "10") -> str:
    """Semantic search across all ingested cybersecurity knowledge. Returns the most relevant results ranked by similarity."""
    try:
        if not query:
            return "❌ Please provide a search query."
        k = int(top_k)
        collection = get_collection()
        if not collection or collection.count() == 0:
            return "❌ Knowledge base is empty. Run an ingest command first."

        results = collection.query(query_texts=[query], n_results=min(k, collection.count()))

        if not results["documents"] or not results["documents"][0]:
            return f"No results found for: {query}"

        output = f"🔍 Search results for: '{query}'\n{'='*50}\n\n"
        for i, (doc, meta, dist) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        )):
            score = round(1 - dist, 3)
            output += f"**{i+1}. {meta.get('title', 'Unknown')}** (score: {score})\n"
            output += f"   Source: {meta.get('source', '?')} | Category: {meta.get('category', '?')}\n"
            if meta.get("mitre_id"):
                output += f"   MITRE ID: {meta['mitre_id']}\n"
            if meta.get("url"):
                output += f"   URL: {meta['url']}\n"
            preview = doc[:300].replace("\n", " ")
            output += f"   Preview: {preview}...\n\n"

        return output
    except Exception as e:
        logger.error(f"Search error: {e}")
        return f"❌ Search error: {str(e)}"


@mcp.tool()
async def browse_topics(source: str = "", category: str = "") -> str:
    """Browse available topics, categories, and sources in the knowledge base. Filter by source or category."""
    try:
        conn = get_db()
        if source and category:
            rows = conn.execute(
                "SELECT DISTINCT subcategory, COUNT(*) as cnt FROM knowledge WHERE source=? AND category=? GROUP BY subcategory ORDER BY cnt DESC",
                (source, category)).fetchall()
            header = f"📂 Subcategories in {source} / {category}"
        elif source:
            rows = conn.execute(
                "SELECT DISTINCT category, COUNT(*) as cnt FROM knowledge WHERE source=? GROUP BY category ORDER BY cnt DESC",
                (source,)).fetchall()
            header = f"📂 Categories in {source}"
        elif category:
            rows = conn.execute(
                "SELECT DISTINCT source, COUNT(*) as cnt FROM knowledge WHERE category=? GROUP BY source ORDER BY cnt DESC",
                (category,)).fetchall()
            header = f"📂 Sources for category: {category}"
        else:
            rows = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM knowledge GROUP BY source ORDER BY cnt DESC").fetchall()
            header = "📂 All sources in knowledge base"
        conn.close()

        if not rows:
            return "Knowledge base is empty. Run an ingest command first."

        output = f"{header}\n{'='*50}\n\n"
        for row in rows:
            output += f"  • {row[0]} ({row[1]} items)\n"
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def get_technique(identifier: str = "") -> str:
    """Get full details for a specific technique by MITRE ID (e.g., T1059) or keyword search in titles."""
    try:
        if not identifier:
            return "❌ Please provide a MITRE ID or keyword."
        conn = get_db()
        row = conn.execute("SELECT * FROM knowledge WHERE mitre_id=? OR mitre_id LIKE ?",
                          (identifier, f"{identifier}%")).fetchone()
        if not row:
            rows = conn.execute("SELECT * FROM knowledge WHERE title LIKE ? LIMIT 1",
                               (f"%{identifier}%",)).fetchone()
            row = rows
        conn.close()

        if not row:
            return f"No technique found for: {identifier}. Try search_knowledge for fuzzy matching."

        output = f"📋 {row['title']}\n{'='*50}\n\n"
        if row['mitre_id']:
            output += f"**MITRE ID:** {row['mitre_id']}\n"
        output += f"**Source:** {row['source']}\n"
        output += f"**Category:** {row['category']}\n"
        if row['subcategory']:
            output += f"**Subcategory:** {row['subcategory']}\n"
        if row['url']:
            output += f"**URL:** {row['url']}\n"
        tags = json.loads(row['tags']) if row['tags'] else []
        if tags:
            output += f"**Tags:** {', '.join(tags)}\n"
        output += f"\n---\n\n{row['content']}"
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def get_attack_chain(tactic: str = "") -> str:
    """Map tactic-to-technique relationships. Provide a tactic name like initial-access, execution, persistence, privilege-escalation, etc."""
    try:
        if not tactic:
            conn = get_db()
            rows = conn.execute(
                "SELECT DISTINCT subcategory, COUNT(*) as cnt FROM knowledge WHERE source='mitre-attack' AND subcategory != '' GROUP BY subcategory ORDER BY cnt DESC"
            ).fetchall()
            conn.close()
            if not rows:
                return "❌ No MITRE ATT&CK data. Run ingest_mitre_attack first."
            output = "🔗 Available tactics:\n\n"
            for row in rows:
                output += f"  • {row[0]} ({row[1]} techniques)\n"
            output += "\nUse get_attack_chain with a tactic name to see its techniques."
            return output

        conn = get_db()
        rows = conn.execute(
            "SELECT mitre_id, title, tags FROM knowledge WHERE source='mitre-attack' AND (subcategory=? OR tags LIKE ?) ORDER BY mitre_id",
            (tactic, f'%"{tactic}"%')).fetchall()
        conn.close()

        if not rows:
            return f"No techniques found for tactic: {tactic}"

        output = f"🔗 Attack chain for: {tactic}\n{'='*50}\n\n"
        for row in rows:
            output += f"  • [{row['mitre_id']}] {row['title']}\n"
        output += f"\nTotal: {len(rows)} techniques"
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


# === EXPORT & MANAGEMENT TOOLS ===

@mcp.tool()
async def export_obsidian(source: str = "", category: str = "", max_items: str = "100") -> str:
    """Export knowledge base entries as Obsidian-compatible markdown files with YAML frontmatter and wiki-links."""
    try:
        max_n = int(max_items)
        conn = get_db()
        if source:
            rows = conn.execute("SELECT * FROM knowledge WHERE source=? LIMIT ?", (source, max_n)).fetchall()
        elif category:
            rows = conn.execute("SELECT * FROM knowledge WHERE category=? LIMIT ?", (category, max_n)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM knowledge LIMIT ?", (max_n,)).fetchall()
        conn.close()

        if not rows:
            return "❌ No items to export."

        count = 0
        for row in rows:
            tags = json.loads(row["tags"]) if row["tags"] else []
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', row["title"])[:100]

            frontmatter = "---\n"
            frontmatter += f"title: \"{row['title']}\"\n"
            frontmatter += f"source: {row['source']}\n"
            frontmatter += f"category: {row['category']}\n"
            if row['mitre_id']:
                frontmatter += f"mitre_id: {row['mitre_id']}\n"
            if tags:
                frontmatter += f"tags: [{', '.join(tags[:10])}]\n"
            if row['url']:
                frontmatter += f"url: {row['url']}\n"
            frontmatter += f"updated: {row['updated_at']}\n"
            frontmatter += "---\n\n"

            wiki_content = row["content"]
            for tag in tags[:5]:
                wiki_content = wiki_content.replace(tag, f"[[{tag}]]", 1)

            filepath = OBSIDIAN_DIR / f"{safe_title}.md"
            filepath.write_text(frontmatter + wiki_content, encoding="utf-8")
            count += 1

        return f"✅ Exported {count} files to {OBSIDIAN_DIR}\n📁 Copy this folder to your Obsidian vault."
    except Exception as e:
        return f"❌ Export error: {str(e)}"


@mcp.tool()
async def export_rag_dataset(format_type: str = "jsonl", source: str = "") -> str:
    """Export knowledge base as RAG training data. Formats: jsonl (one JSON object per line) or qa (question-answer pairs)."""
    try:
        conn = get_db()
        if source:
            rows = conn.execute("SELECT * FROM knowledge WHERE source=?", (source,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM knowledge").fetchall()
        conn.close()

        if not rows:
            return "❌ No data to export."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        count = 0

        if format_type == "jsonl":
            export_path = EXPORTS_DIR / f"cyberrag_export_{timestamp}.jsonl"
            with open(export_path, "w") as f:
                for row in rows:
                    entry = {
                        "id": row["id"],
                        "title": row["title"],
                        "content": row["content"],
                        "source": row["source"],
                        "category": row["category"],
                        "mitre_id": row["mitre_id"],
                        "tags": json.loads(row["tags"]) if row["tags"] else [],
                        "url": row["url"]
                    }
                    f.write(json.dumps(entry) + "\n")
                    count += 1
        elif format_type == "qa":
            export_path = EXPORTS_DIR / f"cyberrag_qa_{timestamp}.jsonl"
            with open(export_path, "w") as f:
                for row in rows:
                    entry = {
                        "question": f"What is {row['title']}?",
                        "answer": row["content"][:2000],
                        "source": row["source"],
                        "mitre_id": row["mitre_id"]
                    }
                    f.write(json.dumps(entry) + "\n")
                    count += 1
        else:
            return f"❌ Unknown format: {format_type}. Use 'jsonl' or 'qa'."

        return f"✅ Exported {count} items to {export_path}\n📊 Format: {format_type.upper()}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def export_openwebui(source: str = "", category: str = "", max_items: str = "500") -> str:
    """Export knowledge base as RAG-optimized markdown files for Open WebUI Knowledge Base ingestion. Files use structured H1-H6 headers for markdown splitting, YAML frontmatter for metadata, clean formatting for maximum embedding quality, and chunk-friendly section sizing (500-2000 tokens per section). Optimized for Open WebUI's hybrid search with BM25 + vector retrieval."""
    try:
        max_n = int(max_items)
        conn = get_db()
        if source:
            rows = conn.execute("SELECT * FROM knowledge WHERE source=? LIMIT ?", (source, max_n)).fetchall()
        elif category:
            rows = conn.execute("SELECT * FROM knowledge WHERE category=? LIMIT ?", (category, max_n)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM knowledge LIMIT ?", (max_n,)).fetchall()
        conn.close()

        if not rows:
            return "❌ No items to export."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = EXPORTS_DIR / f"openwebui_{timestamp}"
        export_dir.mkdir(exist_ok=True)

        count = 0
        source_groups = {}
        for row in rows:
            src = row["source"]
            source_groups.setdefault(src, []).append(row)

        for src, items in source_groups.items():
            cat_groups = {}
            for item in items:
                cat = item["category"] or "general"
                cat_groups.setdefault(cat, []).append(item)

            for cat, cat_items in cat_groups.items():
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', f"{src}_{cat}")[:80]

                doc = "---\n"
                doc += f"title: \"CyberRAG: {src.replace('-', ' ').title()} - {cat.replace('-', ' ').title()}\"\n"
                doc += f"source: {src}\n"
                doc += f"category: {cat}\n"
                doc += f"item_count: {len(cat_items)}\n"
                doc += f"exported: {datetime.now(timezone.utc).isoformat()}\n"
                doc += f"description: \"Cybersecurity knowledge base - {src} {cat} content for RAG retrieval\"\n"
                doc += "---\n\n"

                doc += f"# {src.replace('-', ' ').title()}: {cat.replace('-', ' ').title()}\n\n"

                for item in cat_items:
                    tags = json.loads(item["tags"]) if item["tags"] else []
                    content = item["content"]

                    content = re.sub(r'<[^>]+>', '', content)
                    content = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', content)
                    content = re.sub(r'\n{3,}', '\n\n', content)
                    content = re.sub(r'(?i)(table of contents|back to top|click here|read more\.\.\.)', '', content)
                    content = content.strip()

                    if not content:
                        continue

                    doc += f"## {item['title']}\n\n"

                    meta_parts = []
                    if item['mitre_id']:
                        meta_parts.append(f"**MITRE ID:** {item['mitre_id']}")
                    if item['url']:
                        meta_parts.append(f"**Source URL:** {item['url']}")
                    if tags:
                        meta_parts.append(f"**Tags:** {', '.join(tags[:10])}")
                    if item['subcategory'] and item['subcategory'] != cat:
                        meta_parts.append(f"**Subcategory:** {item['subcategory']}")

                    if meta_parts:
                        doc += " | ".join(meta_parts) + "\n\n"

                    if len(content) > 4000:
                        sections = re.split(r'\n(?=#{1,6}\s)', content)
                        if len(sections) <= 1:
                            paragraphs = content.split('\n\n')
                            current_section = ""
                            section_num = 1
                            for para in paragraphs:
                                if len(current_section) + len(para) > 1500 and current_section:
                                    doc += f"### Section {section_num}\n\n{current_section.strip()}\n\n"
                                    current_section = para + "\n\n"
                                    section_num += 1
                                else:
                                    current_section += para + "\n\n"
                            if current_section.strip():
                                if section_num > 1:
                                    doc += f"### Section {section_num}\n\n{current_section.strip()}\n\n"
                                else:
                                    doc += current_section.strip() + "\n\n"
                        else:
                            for section in sections:
                                section = section.strip()
                                if section:
                                    section = re.sub(r'^(#{1,2})\s', '### ', section)
                                    doc += section + "\n\n"
                    else:
                        doc += content + "\n\n"

                    doc += "---\n\n"
                    count += 1

                filepath = export_dir / f"{safe_name}.md"
                filepath.write_text(doc, encoding="utf-8")

        index_doc = "---\n"
        index_doc += "title: \"CyberRAG Knowledge Base Index\"\n"
        index_doc += f"exported: {datetime.now(timezone.utc).isoformat()}\n"
        index_doc += f"total_items: {count}\n"
        index_doc += "---\n\n"
        index_doc += "# CyberRAG Knowledge Base Index\n\n"
        index_doc += f"Total items exported: {count}\n\n"
        index_doc += "## Sources\n\n"
        for src, items in source_groups.items():
            index_doc += f"### {src.replace('-', ' ').title()}\n\n"
            cats = set(item["category"] for item in items)
            for cat in sorted(cats):
                cat_count = sum(1 for item in items if item["category"] == cat)
                index_doc += f"- **{cat}**: {cat_count} items\n"
            index_doc += "\n"

        index_path = export_dir / "_index.md"
        index_path.write_text(index_doc, encoding="utf-8")

        return (f"✅ Exported {count} items to {export_dir}\n\n"
                f"📁 **{len(source_groups)} source files** + 1 index file\n"
                f"📋 Optimized for Open WebUI Knowledge Base:\n"
                f"   • Markdown H1-H6 headers for semantic splitting\n"
                f"   • YAML frontmatter for metadata/citations\n"
                f"   • HTML/image noise removed\n"
                f"   • Long content split into ~1500 char sections\n"
                f"   • BM25-friendly keyword metadata blocks\n\n"
                f"🔧 **Recommended Open WebUI settings:**\n"
                f"   • Text Splitter: Token (Tiktoken)\n"
                f"   • Chunk Size: 1500-2000\n"
                f"   • Chunk Overlap: 200\n"
                f"   • Chunk Min Size Target: 1000\n"
                f"   • Markdown Header Splitting: ON\n"
                f"   • Hybrid Search: ON\n"
                f"   • Top K: 10-20\n\n"
                f"📤 Upload the .md files to Open WebUI:\n"
                f"   Workspace → Knowledge → Create Collection → Upload files")
    except Exception as e:
        return f"❌ Export error: {str(e)}"


@mcp.tool()
async def list_sources() -> str:
    """List all ingested sources with their status, item counts, and last update times."""
    try:
        conn = get_db()
        rows = conn.execute("SELECT * FROM sources ORDER BY last_ingested DESC").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        conn.close()

        if not rows:
            return ("📭 No sources ingested yet. Try:\n"
                    "  • ingest_mitre_attack\n  • ingest_gtfobins\n  • ingest_wadcoms\n"
                    "  • ingest_hacktricks\n  • ingest_owasp\n  • ingest_payloads\n"
                    "  • ingest_bugbounty_writeups\n  • ingest_hackerone_reports\n"
                    "  • ingest_hackerone_tops\n  • ingest_bugcrowd_taxonomy")

        output = f"📊 CyberRAG Knowledge Base Status\n{'='*50}\n\n"
        output += f"Total items: {total}\n\n"
        for row in rows:
            output += f"  • **{row['name']}** — {row['item_count']} items (status: {row['status']})\n"
            output += f"    Last ingested: {row['last_ingested']}\n"
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def refresh_source(source_name: str = "") -> str:
    """Clear and re-ingest a specific source. Provide the source name from list_sources."""
    try:
        if not source_name:
            return "❌ Provide a source name. Use list_sources to see available sources."

        conn = get_db()
        deleted = conn.execute("DELETE FROM knowledge WHERE source=?", (source_name,)).rowcount
        conn.commit()
        conn.close()

        collection = get_collection()
        if collection:
            try:
                existing = collection.get(where={"source": source_name})
                if existing and existing["ids"]:
                    collection.delete(ids=existing["ids"])
            except Exception:
                pass

        return f"🔄 Cleared {deleted} items from '{source_name}'. Now run the appropriate ingest command to re-import fresh data."
    except Exception as e:
        return f"❌ Error: {str(e)}"


# === SERVER STARTUP ===
if __name__ == "__main__":
    logger.info("Starting CyberRAG MCP server...")
    logger.info(f"Data directory: {DATA_DIR}")
    logger.info(f"SQLite: {SQLITE_PATH}")
    logger.info(f"ChromaDB: {CHROMADB_DIR}")

    try:
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)