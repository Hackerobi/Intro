#!/usr/bin/env python3
"""StudyCompanion MCP Server - Personal Cybersecurity Study Assistant"""
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

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("studycompanion")

# === CONFIGURATION ===
DATA_DIR = Path(os.environ.get("STUDYCOMPANION_DATA_DIR", "/app/data"))
SQLITE_PATH = DATA_DIR / "sqlite" / "studycompanion.db"
CHROMADB_DIR = str(DATA_DIR / "chromadb")
EXPORTS_DIR = DATA_DIR / "exports"

for d in [DATA_DIR / "sqlite", DATA_DIR / "chromadb", EXPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === CYBERSECURITY TAXONOMY ===
TAXONOMY = {
    "reconnaissance": ["nmap", "recon-ng", "shodan", "theHarvester", "amass", "subfinder", "osint", "footprinting", "dns enumeration", "port scanning"],
    "enumeration": ["smb", "snmp", "ldap", "nfs", "ftp", "ssh", "dns", "http", "rpc", "netbios", "service enumeration", "banner grabbing"],
    "web-exploitation": ["sql injection", "sqli", "xss", "cross-site scripting", "csrf", "ssrf", "lfi", "rfi", "file inclusion", "xxe", "idor", "command injection", "deserialization", "upload bypass", "burp suite"],
    "privilege-escalation": ["suid", "sudo", "cron", "capabilities", "kernel exploit", "path hijacking", "dll hijacking", "token impersonation", "uac bypass", "potato", "linpeas", "winpeas", "gtfobins"],
    "active-directory": ["kerberoasting", "asrep roasting", "pass the hash", "pass the ticket", "golden ticket", "silver ticket", "dcsync", "bloodhound", "mimikatz", "rubeus", "certipy", "adcs", "gpo abuse", "delegation", "constrained delegation", "unconstrained delegation"],
    "network-security": ["arp spoofing", "mitm", "man in the middle", "packet capture", "wireshark", "tcpdump", "vlan hopping", "dns poisoning", "firewall", "ids", "ips", "vpn", "proxy"],
    "cryptography": ["encryption", "decryption", "hash", "rsa", "aes", "ssl", "tls", "certificate", "pgp", "gpg", "steganography", "base64", "rot13", "cipher"],
    "malware-analysis": ["reverse engineering", "ghidra", "ida", "radare2", "strings", "strace", "ltrace", "sandbox", "yara", "volatility", "memory forensics", "static analysis", "dynamic analysis"],
    "forensics": ["disk forensics", "memory forensics", "network forensics", "log analysis", "timeline", "autopsy", "sleuthkit", "volatility", "evidence", "chain of custody", "carving"],
    "cloud-security": ["aws", "azure", "gcp", "s3 bucket", "iam", "lambda", "ec2", "kubernetes", "docker", "container escape", "metadata service", "imds"],
    "wireless-security": ["wifi", "wpa", "wep", "aircrack", "deauth", "evil twin", "bluetooth", "zigbee", "rfid", "sdr"],
    "social-engineering": ["phishing", "spear phishing", "vishing", "smishing", "pretexting", "baiting", "tailgating", "watering hole"],
    "post-exploitation": ["persistence", "lateral movement", "pivoting", "data exfiltration", "c2", "command and control", "cobalt strike", "metasploit", "meterpreter", "empire", "covenant"],
    "defense-evasion": ["obfuscation", "encoding", "packing", "amsi bypass", "etw bypass", "av evasion", "edr bypass", "living off the land", "lolbins"],
    "scripting-automation": ["python", "bash", "powershell", "ruby", "go", "rust", "c", "assembly", "regex", "automation", "scripting"]
}

ALL_TAGS = set()
for category, tags in TAXONOMY.items():
    ALL_TAGS.add(category)
    ALL_TAGS.update(tags)

# === MCP SERVER ===
mcp = FastMCP("StudyCompanion")

# === SQLITE SETUP ===
def get_db():
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT DEFAULT '[]',
        category TEXT DEFAULT '',
        source_ref TEXT DEFAULT '',
        created_at TEXT DEFAULT '',
        updated_at TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS qa_pairs (
        id TEXT PRIMARY KEY,
        note_id TEXT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        difficulty TEXT DEFAULT 'medium',
        tags TEXT DEFAULT '[]',
        created_at TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS flashcards (
        id TEXT PRIMARY KEY,
        deck TEXT DEFAULT 'general',
        front TEXT NOT NULL,
        back TEXT NOT NULL,
        tags TEXT DEFAULT '[]',
        created_at TEXT DEFAULT ''
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
                name="studycompanion",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB collection ready: {_collection.count()} notes")
        except Exception as e:
            logger.error(f"ChromaDB init error: {e}")
            return None
    return _collection

# === HELPER FUNCTIONS ===
def content_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]

def auto_tag(content):
    content_lower = content.lower()
    detected_tags = []
    detected_categories = []

    for category, keywords in TAXONOMY.items():
        for keyword in keywords:
            if keyword in content_lower:
                if category not in detected_categories:
                    detected_categories.append(category)
                if keyword not in detected_tags:
                    detected_tags.append(keyword)

    return detected_categories, detected_tags

def store_note(note_id, title, content, tags, category):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute("""INSERT OR REPLACE INTO notes
            (id, title, content, tags, category, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (note_id, title, content, json.dumps(tags), category, now, now))
        conn.commit()
    finally:
        conn.close()

    collection = get_collection()
    if collection:
        try:
            collection.upsert(
                ids=[note_id],
                documents=[content[:8000]],
                metadatas=[{"title": title, "category": category, "tags": json.dumps(tags[:10])}]
            )
        except Exception as e:
            logger.error(f"ChromaDB upsert error: {e}")

# === NOTE MANAGEMENT TOOLS ===

@mcp.tool()
async def add_note(title: str = "", content: str = "") -> str:
    """Add a study note with automatic cybersecurity topic tagging. Paste your notes and they will be auto-categorized."""
    try:
        if not title or not content:
            return "❌ Both title and content are required."

        categories, tags = auto_tag(content)
        primary_category = categories[0] if categories else "general"
        all_tags = list(set(categories + tags))
        note_id = f"note-{content_hash(title + content)}"

        store_note(note_id, title, content, all_tags, primary_category)

        output = f"✅ Note saved: {title}\n"
        output += f"📁 Category: {primary_category}\n"
        output += f"🏷️ Auto-tags: {', '.join(all_tags[:15])}\n"
        output += f"🆔 ID: {note_id}"
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def tag_content(note_id: str = "", additional_tags: str = "") -> str:
    """Re-tag or manually add tags to an existing note. Provide comma-separated tags."""
    try:
        if not note_id:
            return "❌ Provide a note_id."
        conn = get_db()
        row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        if not row:
            conn.close()
            return f"❌ Note not found: {note_id}"

        existing_tags = json.loads(row["tags"]) if row["tags"] else []
        new_tags = [t.strip() for t in additional_tags.split(",") if t.strip()]
        combined = list(set(existing_tags + new_tags))

        conn.execute("UPDATE notes SET tags=?, updated_at=? WHERE id=?",
                     (json.dumps(combined), datetime.now(timezone.utc).isoformat(), note_id))
        conn.commit()
        conn.close()

        return f"✅ Updated tags for {row['title']}\n🏷️ Tags: {', '.join(combined)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def search_notes(query: str = "", top_k: str = "10") -> str:
    """Semantic search across all personal study notes."""
    try:
        if not query:
            return "❌ Please provide a search query."
        k = int(top_k)
        collection = get_collection()
        if not collection or collection.count() == 0:
            return "❌ No notes yet. Use add_note to start building your knowledge base."

        results = collection.query(query_texts=[query], n_results=min(k, collection.count()))

        if not results["documents"] or not results["documents"][0]:
            return f"No notes found for: {query}"

        output = f"🔍 Notes matching: '{query}'\n{'='*50}\n\n"
        for i, (doc, meta, dist) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        )):
            score = round(1 - dist, 3)
            output += f"**{i+1}. {meta.get('title', 'Unknown')}** (relevance: {score})\n"
            output += f"   Category: {meta.get('category', '?')}\n"
            preview = doc[:200].replace("\n", " ")
            output += f"   {preview}...\n\n"
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


# === STUDY MATERIAL GENERATION TOOLS ===

@mcp.tool()
async def generate_qa(note_id: str = "", num_questions: str = "5") -> str:
    """Generate Q&A pairs from a study note for training data and self-testing. Generates definition, how/why, and command-based questions."""
    try:
        if not note_id:
            return "❌ Provide a note_id. Use search_notes to find notes."
        n = int(num_questions)

        conn = get_db()
        row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        if not row:
            conn.close()
            return f"❌ Note not found: {note_id}"

        title = row["title"]
        content = row["content"]
        tags = json.loads(row["tags"]) if row["tags"] else []
        conn.close()

        qa_pairs = []
        sentences = [s.strip() for s in re.split(r'[.!?\n]', content) if len(s.strip()) > 20]

        # Definition questions
        qa_pairs.append({
            "question": f"What is {title}?",
            "answer": sentences[0] if sentences else content[:200],
            "type": "definition"
        })

        # Extract commands (backtick or $ prefix)
        commands = re.findall(r'`([^`]+)`', content) + re.findall(r'\$\s*(.+)', content)
        for cmd in commands[:n//2]:
            qa_pairs.append({
                "question": f"What does the command '{cmd}' do in the context of {title}?",
                "answer": f"In {title}, the command '{cmd}' is used as part of the technique/process described.",
                "type": "command"
            })

        # How/why questions from content
        for i, sent in enumerate(sentences[1:n]):
            if any(kw in sent.lower() for kw in ["because", "allows", "enables", "used to", "can be", "provides"]):
                qa_pairs.append({
                    "question": f"How does {title} relate to: {sent[:60]}...?",
                    "answer": sent,
                    "type": "conceptual"
                })

        # Tag-based questions
        for tag in tags[:2]:
            qa_pairs.append({
                "question": f"How is {tag} related to {title}?",
                "answer": f"{title} involves {tag} as part of its methodology or toolset.",
                "type": "relationship"
            })

        # Store Q&A pairs
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        for qa in qa_pairs[:n]:
            qa_id = f"qa-{content_hash(qa['question'])}"
            conn.execute("""INSERT OR REPLACE INTO qa_pairs (id, note_id, question, answer, difficulty, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (qa_id, note_id, qa["question"], qa["answer"], "medium", json.dumps(tags), now))
        conn.commit()
        conn.close()

        output = f"📝 Generated {len(qa_pairs[:n])} Q&A pairs from: {title}\n{'='*50}\n\n"
        for i, qa in enumerate(qa_pairs[:n]):
            output += f"**Q{i+1} ({qa['type']}):** {qa['question']}\n"
            output += f"**A:** {qa['answer'][:200]}\n\n"
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def create_flashcards(topic: str = "", deck_name: str = "general") -> str:
    """Create flashcard decks from notes matching a topic. Cards are stored for export to Anki or other tools."""
    try:
        if not topic:
            return "❌ Provide a topic to create flashcards from."

        collection = get_collection()
        if not collection or collection.count() == 0:
            return "❌ No notes available."

        results = collection.query(query_texts=[topic], n_results=min(10, collection.count()))

        if not results["documents"] or not results["documents"][0]:
            return f"No notes found for topic: {topic}"

        conn = get_db()
        now = datetime.now(timezone.utc).isoformat()
        cards = []

        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            title = meta.get("title", "Unknown")
            sentences = [s.strip() for s in re.split(r'[.!?\n]', doc) if len(s.strip()) > 20]

            if sentences:
                card_id = f"fc-{content_hash(title + sentences[0])}"
                front = f"What is {title}?"
                back = sentences[0]
                conn.execute("""INSERT OR REPLACE INTO flashcards (id, deck, front, back, tags, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (card_id, deck_name, front, back, meta.get("tags", "[]"), now))
                cards.append({"front": front, "back": back})

            commands = re.findall(r'`([^`]+)`', doc)
            for cmd in commands[:3]:
                card_id = f"fc-{content_hash(cmd)}"
                front = f"What does `{cmd}` do?"
                back = f"Used in {title}: {cmd}"
                conn.execute("""INSERT OR REPLACE INTO flashcards (id, deck, front, back, tags, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (card_id, deck_name, front, back, meta.get("tags", "[]"), now))
                cards.append({"front": front, "back": back})

        conn.commit()
        conn.close()

        output = f"🃏 Created {len(cards)} flashcards in deck: {deck_name}\n{'='*50}\n\n"
        for i, card in enumerate(cards[:10]):
            output += f"**Card {i+1}**\n  Front: {card['front']}\n  Back: {card['back'][:100]}\n\n"
        if len(cards) > 10:
            output += f"... and {len(cards)-10} more cards"
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def summarize_topic(topic: str = "") -> str:
    """Summarize all knowledge on a specific topic by searching across all notes."""
    try:
        if not topic:
            return "❌ Provide a topic to summarize."

        collection = get_collection()
        if not collection or collection.count() == 0:
            return "❌ No notes available."

        results = collection.query(query_texts=[topic], n_results=min(10, collection.count()))

        if not results["documents"] or not results["documents"][0]:
            return f"No notes found for: {topic}"

        output = f"📚 Summary: {topic}\n{'='*50}\n\n"
        output += f"Found {len(results['documents'][0])} relevant notes:\n\n"

        for i, (doc, meta, dist) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        )):
            score = round(1 - dist, 3)
            if score < 0.3:
                continue
            output += f"### {meta.get('title', 'Unknown')} (relevance: {score})\n"
            output += f"{doc[:500]}\n\n"

        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


# === PROGRESS & ANALYSIS TOOLS ===

@mcp.tool()
async def track_progress() -> str:
    """Dashboard showing study coverage across all cybersecurity topics based on notes and taxonomy."""
    try:
        conn = get_db()
        notes = conn.execute("SELECT tags, category FROM notes").fetchall()
        qa_count = conn.execute("SELECT COUNT(*) FROM qa_pairs").fetchone()[0]
        fc_count = conn.execute("SELECT COUNT(*) FROM flashcards").fetchone()[0]
        conn.close()

        covered_categories = set()
        covered_tags = set()
        for note in notes:
            tags = json.loads(note["tags"]) if note["tags"] else []
            covered_tags.update(tags)
            if note["category"]:
                covered_categories.add(note["category"])

        total_categories = len(TAXONOMY)
        covered_cat_count = len(covered_categories.intersection(TAXONOMY.keys()))
        coverage_pct = round((covered_cat_count / total_categories) * 100, 1) if total_categories > 0 else 0

        output = f"📊 Study Progress Dashboard\n{'='*50}\n\n"
        output += f"📝 Total notes: {len(notes)}\n"
        output += f"❓ Q&A pairs: {qa_count}\n"
        output += f"🃏 Flashcards: {fc_count}\n"
        output += f"📈 Topic coverage: {covered_cat_count}/{total_categories} ({coverage_pct}%)\n\n"
        output += f"**Category Breakdown:**\n\n"

        for category in sorted(TAXONOMY.keys()):
            if category in covered_categories:
                count = sum(1 for n in notes if n["category"] == category)
                output += f"  ✅ {category} ({count} notes)\n"
            else:
                output += f"  ⬜ {category}\n"

        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def find_gaps() -> str:
    """Identify weak areas and recommend next study topics based on coverage gaps in the taxonomy."""
    try:
        conn = get_db()
        notes = conn.execute("SELECT tags, category FROM notes").fetchall()
        conn.close()

        covered_categories = set()
        covered_tags = set()
        category_counts = {}

        for note in notes:
            tags = json.loads(note["tags"]) if note["tags"] else []
            covered_tags.update(tags)
            cat = note["category"]
            if cat:
                covered_categories.add(cat)
                category_counts[cat] = category_counts.get(cat, 0) + 1

        output = f"🔍 Knowledge Gap Analysis\n{'='*50}\n\n"

        missing = [c for c in TAXONOMY.keys() if c not in covered_categories]
        weak = [(c, cnt) for c, cnt in category_counts.items() if cnt < 3]

        if missing:
            output += f"**🚫 Missing Categories ({len(missing)}):**\n"
            for cat in missing:
                sample_topics = ", ".join(TAXONOMY[cat][:5])
                output += f"  • {cat} — try: {sample_topics}\n"
            output += "\n"

        if weak:
            output += f"**⚠️ Weak Categories (< 3 notes):**\n"
            for cat, cnt in sorted(weak, key=lambda x: x[1]):
                missing_topics = [t for t in TAXONOMY[cat] if t not in covered_tags]
                output += f"  • {cat} ({cnt} notes) — missing: {', '.join(missing_topics[:5])}\n"
            output += "\n"

        output += "**📋 Recommended Study Order:**\n"
        priority = missing[:3] + [c for c, _ in sorted(weak, key=lambda x: x[1])[:3]]
        for i, cat in enumerate(priority[:5], 1):
            output += f"  {i}. {cat}\n"

        if not missing and not weak:
            output += "\n🎉 Great coverage! Consider deepening knowledge in existing categories."

        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


# === EXPORT TOOLS ===

@mcp.tool()
async def export_study_data(format_type: str = "jsonl") -> str:
    """Export all study data (notes, Q&A pairs, flashcards) as JSONL for RAG training or Obsidian markdown."""
    try:
        conn = get_db()
        notes = conn.execute("SELECT * FROM notes").fetchall()
        qa_pairs = conn.execute("SELECT * FROM qa_pairs").fetchall()
        flashcards = conn.execute("SELECT * FROM flashcards").fetchall()
        conn.close()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        count = 0

        if format_type == "jsonl":
            export_path = EXPORTS_DIR / f"studycompanion_{timestamp}.jsonl"
            with open(export_path, "w") as f:
                for note in notes:
                    entry = {
                        "type": "note",
                        "title": note["title"],
                        "content": note["content"],
                        "tags": json.loads(note["tags"]) if note["tags"] else [],
                        "category": note["category"]
                    }
                    f.write(json.dumps(entry) + "\n")
                    count += 1
                for qa in qa_pairs:
                    entry = {
                        "type": "qa",
                        "question": qa["question"],
                        "answer": qa["answer"],
                        "difficulty": qa["difficulty"]
                    }
                    f.write(json.dumps(entry) + "\n")
                    count += 1

            return f"✅ Exported {count} items to {export_path}\n📊 Format: JSONL (RAG-ready)\n  Notes: {len(notes)} | Q&A: {len(qa_pairs)} | Flashcards: {len(flashcards)}"

        elif format_type == "obsidian":
            export_dir = EXPORTS_DIR / f"obsidian_{timestamp}"
            export_dir.mkdir(exist_ok=True)
            for note in notes:
                tags = json.loads(note["tags"]) if note["tags"] else []
                safe_title = re.sub(r'[<>:"/\\|?*]', '_', note["title"])[:100]

                frontmatter = "---\n"
                frontmatter += f"title: \"{note['title']}\"\n"
                frontmatter += f"category: {note['category']}\n"
                frontmatter += f"tags: [{', '.join(tags[:10])}]\n"
                frontmatter += f"created: {note['created_at']}\n"
                frontmatter += "---\n\n"

                filepath = export_dir / f"{safe_title}.md"
                filepath.write_text(frontmatter + note["content"], encoding="utf-8")
                count += 1

            return f"✅ Exported {count} notes to {export_dir}\n📁 Copy to your Obsidian vault."
        else:
            return f"❌ Unknown format: {format_type}. Use 'jsonl' or 'obsidian'."
    except Exception as e:
        return f"❌ Error: {str(e)}"


# === SERVER STARTUP ===
if __name__ == "__main__":
    logger.info("Starting StudyCompanion MCP server...")
    logger.info(f"Data directory: {DATA_DIR}")

    try:
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)
