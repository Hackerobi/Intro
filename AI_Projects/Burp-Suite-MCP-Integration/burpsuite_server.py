#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Burp Suite MCP Server - AI-powered web application security testing interface."""
import os
import sys
import json
import logging
import asyncio
import aiofiles
from datetime import datetime, timezone
from pathlib import Path
import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("burpsuite-server")

mcp = FastMCP("burpsuite")

BURP_PROXY_HOST = os.environ.get("BURP_PROXY_HOST", "host.docker.internal")
BURP_PROXY_PORT = os.environ.get("BURP_PROXY_PORT", "8087")
BURP_API_PORT = os.environ.get("BURP_API_PORT", "1337")
REPORTS_DIR = Path("/app/reports")
FINDINGS_DIR = Path("/app/findings")

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
FINDINGS_DIR.mkdir(parents=True, exist_ok=True)

session_data = {
    "target": "",
    "scope": [],
    "findings": [],
    "scan_history": [],
    "current_workflow": None
}

def get_burp_api_url():
    return f"http://{BURP_PROXY_HOST}:{BURP_API_PORT}"

def get_burp_proxy_url():
    return f"http://{BURP_PROXY_HOST}:{BURP_PROXY_PORT}"

async def send_request_through_proxy(method, url, headers=None, body=""):
    proxy_url = get_burp_proxy_url()
    async with httpx.AsyncClient(proxy=proxy_url, timeout=30, verify=False) as client:
        if method.upper() == "GET":
            response = await client.get(url, headers=headers)
        elif method.upper() == "POST":
            response = await client.post(url, headers=headers, content=body)
        elif method.upper() == "PUT":
            response = await client.put(url, headers=headers, content=body)
        elif method.upper() == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            response = await client.request(method, url, headers=headers, content=body)
        return response

def generate_finding_id():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    count = len(session_data["findings"]) + 1
    return f"FINDING-{timestamp}-{count:04d}"

@mcp.tool()
async def set_target(url: str = "") -> str:
    """Set the target URL for the penetration test."""
    if not url.strip():
        return "[ERROR] Target URL is required. Example: set_target('https://example.com')"
    
    try:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        session_data["target"] = url
        session_data["scope"].append(url)
        
        logger.info(f"Target set to: {url}")
        
        result = "[OK] Target configured successfully!\n\n"
        result += f"[TARGET] Primary Target: {url}\n\n"
        result += "Next Steps:\n"
        result += "1. Use add_to_scope to add additional domains/paths\n"
        result += "2. Use start_reconnaissance to begin automated discovery\n"
        result += "3. Use send_request to manually explore endpoints\n\n"
        result += "[WARNING] Ensure you have authorization to test this target."
        return result
    except Exception as e:
        logger.error(f"Error setting target: {e}")
        return f"[ERROR] Error setting target: {str(e)}"

@mcp.tool()
async def add_to_scope(url_pattern: str = "") -> str:
    """Add a URL pattern to the testing scope."""
    if not url_pattern.strip():
        return "[ERROR] URL pattern is required. Example: add_to_scope('*.example.com')"
    
    try:
        if url_pattern not in session_data["scope"]:
            session_data["scope"].append(url_pattern)
            logger.info(f"Added to scope: {url_pattern}")
        
        scope_list = "\n".join([f"  - {s}" for s in session_data["scope"]])
        return f"[OK] Scope updated!\n\nCurrent Scope:\n{scope_list}"
    except Exception as e:
        logger.error(f"Error adding to scope: {e}")
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def get_scope() -> str:
    """Get the current testing scope configuration."""
    try:
        if not session_data["scope"]:
            return "[LIST] Scope: No targets configured. Use set_target to begin."
        
        scope_list = "\n".join([f"  - {s}" for s in session_data["scope"]])
        result = "[LIST] Current Testing Scope\n\n"
        result += f"[TARGET] Primary Target: {session_data.get('target', 'Not set')}\n\n"
        result += f"In-Scope URLs/Patterns:\n{scope_list}\n\n"
        result += f"Session Stats:\n"
        result += f"  - Findings: {len(session_data['findings'])}\n"
        result += f"  - Scans completed: {len(session_data['scan_history'])}"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def send_request(url: str = "", method: str = "GET", headers: str = "", body: str = "", through_proxy: str = "true") -> str:
    """Send an HTTP request optionally through Burp proxy."""
    if not url.strip():
        return "[ERROR] URL is required"
    
    try:
        header_dict = {}
        if headers.strip():
            try:
                header_dict = json.loads(headers)
            except json.JSONDecodeError:
                return "[ERROR] Headers must be valid JSON. Example: {\"Cookie\": \"session=abc\"}"
        
        use_proxy = through_proxy.lower() == "true"
        
        if use_proxy:
            response = await send_request_through_proxy(method, url, header_dict, body)
        else:
            async with httpx.AsyncClient(timeout=30, verify=False) as client:
                response = await client.request(method, url, headers=header_dict, content=body if body else None)
        
        response_headers = "\n".join([f"  {k}: {v}" for k, v in response.headers.items()])
        body_preview = response.text[:1000] if response.text else "(empty)"
        if len(response.text) > 1000:
            body_preview += f"\n... (truncated, {len(response.text)} total bytes)"
        
        proxy_status = "[OK] Through Burp Proxy" if use_proxy else "Direct Connection"
        
        result = f"[SEND] Request Sent ({proxy_status})\n\n"
        result += f"Request:\n  {method} {url}\n\n"
        result += f"Response:\n  Status: {response.status_code} {response.reason_phrase}\n\n"
        result += f"Headers:\n{response_headers}\n\n"
        result += f"Body Preview:\n{body_preview}"
        return result
    except httpx.ConnectError:
        if through_proxy.lower() == "true":
            return f"[ERROR] Connection Error: Cannot connect to Burp proxy at {get_burp_proxy_url()}. Ensure Burp Suite is running."
        return f"[ERROR] Connection Error: Cannot connect to {url}"
    except Exception as e:
        logger.error(f"Request error: {e}")
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def start_reconnaissance(target: str = "", depth: str = "standard") -> str:
    """Start automated reconnaissance on target."""
    target_url = target.strip() or session_data.get("target", "")
    if not target_url:
        return "[ERROR] No target specified. Use set_target first or provide a target URL."
    
    try:
        valid_depths = ["quick", "standard", "deep"]
        if depth not in valid_depths:
            depth = "standard"
        
        scan_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        
        scan_record = {
            "id": scan_id,
            "target": target_url,
            "type": "reconnaissance",
            "depth": depth,
            "started": datetime.now(timezone.utc).isoformat(),
            "status": "running"
        }
        session_data["scan_history"].append(scan_record)
        
        depth_config = {
            "quick": {"spider": False, "dirs": 100, "timeout": 60},
            "standard": {"spider": True, "dirs": 500, "timeout": 300},
            "deep": {"spider": True, "dirs": 2000, "timeout": 900}
        }
        config = depth_config[depth]
        
        result = "[SEARCH] Reconnaissance Started\n\n"
        result += f"Scan ID: {scan_id}\n"
        result += f"Target: {target_url}\n"
        result += f"Depth: {depth.capitalize()}\n\n"
        result += f"Configuration:\n"
        result += f"  - Spider enabled: {config['spider']}\n"
        result += f"  - Directory entries: {config['dirs']}\n"
        result += f"  - Timeout: {config['timeout']}s\n\n"
        result += "Recommended Workflow:\n"
        result += "1. Monitor progress with get_scan_status\n"
        result += "2. Review findings with get_findings\n"
        result += "3. Perform targeted testing on discovered endpoints"
        return result
    except Exception as e:
        logger.error(f"Reconnaissance error: {e}")
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def discover_directories(target: str = "", wordlist: str = "common", extensions: str = "") -> str:
    """Discover hidden directories and files using wordlist-based enumeration."""
    target_url = target.strip() or session_data.get("target", "")
    if not target_url:
        return "[ERROR] No target specified"
    
    try:
        wordlists = {
            "common": "/app/wordlists/common.txt",
            "medium": "/app/wordlists/directory-medium.txt",
            "large": "/app/wordlists/directory-large.txt",
            "api": "/app/wordlists/api-endpoints.txt",
            "backup": "/app/wordlists/backup-files.txt"
        }
        
        wordlist_path = wordlists.get(wordlist, wordlists["common"])
        ext_list = extensions.split(",") if extensions else ["", ".php", ".asp", ".aspx", ".jsp", ".html", ".js"]
        
        result = "[DIR] Directory Discovery Configuration\n\n"
        result += f"Target: {target_url}\n"
        result += f"Wordlist: {wordlist} ({wordlist_path})\n"
        result += f"Extensions: {', '.join(ext_list) if ext_list else 'None'}\n\n"
        result += "To execute in Burp Suite:\n"
        result += f"1. Open Intruder\n"
        result += f"2. Set target to: {target_url}/[directory]\n"
        result += f"3. Load wordlist: {wordlist_path}\n"
        result += "4. Configure extensions as payload processing\n"
        result += "5. Start attack"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def scan_vulnerabilities(target: str = "", scan_type: str = "passive") -> str:
    """Scan for vulnerabilities - scan_type can be passive, light, or active."""
    target_url = target.strip() or session_data.get("target", "")
    if not target_url:
        return "[ERROR] No target specified"
    
    try:
        scan_types = {
            "passive": {
                "description": "Non-intrusive analysis of responses",
                "checks": ["Information disclosure", "Missing headers", "Cookie flags", "Version exposure", "Comments/debug info"]
            },
            "light": {
                "description": "Safe active checks",
                "checks": ["Reflected XSS", "Open redirects", "Path traversal", "CORS misconfig", "Clickjacking"]
            },
            "active": {
                "description": "Full vulnerability scanning (may modify data)",
                "checks": ["SQL Injection", "Command Injection", "SSRF", "XXE", "Deserialization", "Authentication bypass"]
            }
        }
        
        if scan_type not in scan_types:
            scan_type = "passive"
        
        config = scan_types[scan_type]
        checks_list = "\n".join([f"    - {c}" for c in config["checks"]])
        
        result = "[SCAN] Vulnerability Scan Configuration\n\n"
        result += f"Target: {target_url}\n"
        result += f"Scan Type: {scan_type.capitalize()}\n"
        result += f"Description: {config['description']}\n\n"
        result += f"Checks to perform:\n{checks_list}\n\n"
        if scan_type == "active":
            result += "[WARNING] ACTIVE scanning may modify application data!\n"
        else:
            result += "This scan type is safe and non-destructive.\n"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def test_injection(url: str = "", parameter: str = "", injection_type: str = "sql") -> str:
    """Test a parameter for injection vulnerabilities."""
    if not url.strip() or not parameter.strip():
        return "[ERROR] Both URL and parameter name are required"
    
    try:
        payloads = {
            "sql": [
                "' OR '1'='1",
                "' OR '1'='1'--",
                "1' ORDER BY 1--",
                "1 UNION SELECT NULL--",
                "'; WAITFOR DELAY '0:0:5'--"
            ],
            "command": [
                "; ls -la",
                "| cat /etc/passwd",
                "`id`",
                "$(whoami)",
                "| sleep 5"
            ],
            "ldap": [
                "*",
                "*)(&",
                "*)(uid=*))(|(uid=*"
            ],
            "xpath": [
                "' or '1'='1",
                "' or ''='"
            ],
            "nosql": [
                '{"$gt": ""}',
                '{"$ne": ""}'
            ]
        }
        
        selected_payloads = payloads.get(injection_type, payloads["sql"])
        payloads_list = "\n".join([f"    {i+1}. {p}" for i, p in enumerate(selected_payloads)])
        
        result = "[INJECT] Injection Testing Configuration\n\n"
        result += f"Target URL: {url}\n"
        result += f"Parameter: {parameter}\n"
        result += f"Injection Type: {injection_type.upper()}\n\n"
        result += f"Test Payloads:\n{payloads_list}\n\n"
        result += "Testing Methodology:\n"
        result += "1. Send baseline request to establish normal response\n"
        result += "2. Inject each payload and compare responses\n"
        result += "3. Look for: errors, timing differences, data leakage"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def test_xss(url: str = "", parameter: str = "", context: str = "html") -> str:
    """Test for XSS vulnerabilities."""
    if not url.strip() or not parameter.strip():
        return "[ERROR] Both URL and parameter name are required"
    
    try:
        payloads = {
            "html": [
                "<script>alert('XSS')</script>",
                "<img src=x onerror=alert('XSS')>",
                "<svg onload=alert('XSS')>"
            ],
            "attribute": [
                "\" onmouseover=\"alert(1)",
                "' onfocus='alert(1)' autofocus='"
            ],
            "javascript": [
                "';alert('XSS');//",
                "'-alert('XSS')-'"
            ],
            "url": [
                "javascript:alert(1)",
                "data:text/html,<script>alert(1)</script>"
            ]
        }
        
        selected_payloads = payloads.get(context, payloads["html"])
        payloads_list = "\n".join([f"    {i+1}. {p}" for i, p in enumerate(selected_payloads)])
        
        result = "[XSS] XSS Testing Configuration\n\n"
        result += f"Target URL: {url}\n"
        result += f"Parameter: {parameter}\n"
        result += f"Context: {context}\n\n"
        result += f"Test Payloads (context-specific):\n{payloads_list}\n\n"
        result += "Testing Approach:\n"
        result += "1. Identify where input is reflected\n"
        result += "2. Determine the rendering context\n"
        result += "3. Craft payload to break out of context\n"
        result += "4. Verify JavaScript execution"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def test_authentication(url: str = "", test_type: str = "all") -> str:
    """Test authentication mechanisms."""
    if not url.strip():
        return "[ERROR] URL is required"
    
    try:
        tests = {
            "brute": {
                "name": "Brute Force",
                "checks": ["Default credentials", "Common password lists", "Username enumeration", "Rate limiting bypass"]
            },
            "bypass": {
                "name": "Authentication Bypass",
                "checks": ["SQL injection in login", "Direct page access", "Parameter manipulation", "JWT/token manipulation"]
            },
            "session": {
                "name": "Session Management",
                "checks": ["Session fixation", "Session token predictability", "Concurrent session handling", "Logout functionality"]
            }
        }
        
        result = "[AUTH] Authentication Testing\n\n"
        result += f"Target: {url}\n"
        result += f"Test Scope: {test_type.capitalize()}\n\n"
        
        if test_type == "all":
            selected_tests = tests
        else:
            selected_tests = {test_type: tests.get(test_type, tests["bypass"])}
        
        for key, test in selected_tests.items():
            checks_list = "\n".join([f"      - {c}" for c in test["checks"]])
            result += f"{test['name']}:\n{checks_list}\n\n"
        
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def add_finding(title: str = "", severity: str = "medium", description: str = "", evidence: str = "", recommendation: str = "") -> str:
    """Add a security finding to the report."""
    if not title.strip():
        return "[ERROR] Finding title is required"
    
    try:
        valid_severities = ["critical", "high", "medium", "low", "info"]
        if severity.lower() not in valid_severities:
            severity = "medium"
        
        finding_id = generate_finding_id()
        
        finding = {
            "id": finding_id,
            "title": title,
            "severity": severity.lower(),
            "description": description or "No description provided",
            "evidence": evidence or "No evidence attached",
            "recommendation": recommendation or "Remediation pending",
            "status": "open",
            "created": datetime.now(timezone.utc).isoformat(),
            "target": session_data.get("target", "Unknown")
        }
        
        session_data["findings"].append(finding)
        
        logger.info(f"Finding added: {finding_id} - {title}")
        
        result = "[OK] Finding Recorded\n\n"
        result += f"ID: {finding_id}\n"
        result += f"Severity: {severity.upper()}\n"
        result += f"Title: {title}\n\n"
        result += f"Description:\n{description or 'Not provided'}\n\n"
        result += f"Evidence:\n{evidence or 'Not provided'}\n\n"
        result += f"Recommendation:\n{recommendation or 'Not provided'}\n\n"
        result += f"[STATS] Session Stats: {len(session_data['findings'])} total findings"
        return result
    except Exception as e:
        logger.error(f"Error adding finding: {e}")
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def get_findings(severity_filter: str = "", status_filter: str = "") -> str:
    """Get all recorded findings with optional filters."""
    try:
        findings = session_data["findings"]
        
        if not findings:
            return "[LIST] Findings Report\n\nNo findings recorded yet.\n\nUse add_finding to record discovered vulnerabilities."
        
        if severity_filter:
            findings = [f for f in findings if f["severity"] == severity_filter.lower()]
        if status_filter:
            findings = [f for f in findings if f["status"] == status_filter.lower()]
        
        grouped = {}
        for finding in findings:
            sev = finding["severity"]
            if sev not in grouped:
                grouped[sev] = []
            grouped[sev].append(finding)
        
        result = "[LIST] Security Findings Report\n\n"
        result += f"Target: {session_data.get('target', 'Not set')}\n"
        result += f"Total Findings: {len(findings)}\n\n"
        
        severity_order = ["critical", "high", "medium", "low", "info"]
        for sev in severity_order:
            if sev in grouped:
                result += f"\n{sev.upper()} ({len(grouped[sev])})\n"
                for f in grouped[sev]:
                    result += f"  - [{f['id']}] {f['title']} ({f['status']})\n"
        
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def get_finding_details(finding_id: str = "") -> str:
    """Get detailed information about a specific finding."""
    if not finding_id.strip():
        return "[ERROR] Finding ID is required"
    
    try:
        finding = next((f for f in session_data["findings"] if f["id"] == finding_id), None)
        
        if not finding:
            return f"[ERROR] Finding not found: {finding_id}"
        
        result = "[DOC] Finding Details\n\n"
        result += f"ID: {finding['id']}\n"
        result += f"Title: {finding['title']}\n"
        result += f"Severity: {finding['severity'].upper()}\n"
        result += f"Status: {finding['status'].capitalize()}\n"
        result += f"Target: {finding['target']}\n"
        result += f"Created: {finding['created']}\n\n"
        result += f"Description:\n{finding['description']}\n\n"
        result += f"Evidence:\n{finding['evidence']}\n\n"
        result += f"Recommendation:\n{finding['recommendation']}"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def update_finding(finding_id: str = "", status: str = "", severity: str = "", notes: str = "") -> str:
    """Update a finding status, severity, or add notes."""
    if not finding_id.strip():
        return "[ERROR] Finding ID is required"
    
    try:
        finding = next((f for f in session_data["findings"] if f["id"] == finding_id), None)
        
        if not finding:
            return f"[ERROR] Finding not found: {finding_id}"
        
        updates = []
        
        if status.strip():
            valid_statuses = ["open", "confirmed", "resolved", "false_positive", "accepted"]
            if status.lower() in valid_statuses:
                finding["status"] = status.lower()
                updates.append(f"Status -> {status}")
        
        if severity.strip():
            valid_severities = ["critical", "high", "medium", "low", "info"]
            if severity.lower() in valid_severities:
                finding["severity"] = severity.lower()
                updates.append(f"Severity -> {severity}")
        
        if notes.strip():
            if "notes" not in finding:
                finding["notes"] = []
            finding["notes"].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "content": notes
            })
            updates.append("Added note")
        
        finding["updated"] = datetime.now(timezone.utc).isoformat()
        
        if not updates:
            return "[WARNING] No updates provided. Specify status, severity, or notes."
        
        result = "[OK] Finding Updated\n\n"
        result += f"ID: {finding_id}\n"
        result += f"Updates: {', '.join(updates)}\n"
        result += f"Current status: {finding['status']}\n"
        result += f"Current severity: {finding['severity']}"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def generate_report(format_type: str = "markdown", include_evidence: str = "true") -> str:
    """Generate a penetration test report."""
    try:
        target = session_data.get("target", "Unknown Target")
        findings = session_data["findings"]
        scope = session_data["scope"]
        
        include_ev = include_evidence.lower() == "true"
        
        severity_counts = {}
        for f in findings:
            sev = f["severity"]
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        filename = f"pentest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if format_type == "json":
            report_data = {
                "report": {
                    "title": "Penetration Test Report",
                    "target": target,
                    "generated": timestamp,
                    "scope": scope,
                    "summary": severity_counts,
                    "findings": findings
                }
            }
            report_content = json.dumps(report_data, indent=2)
            filename += ".json"
        else:
            findings_md = ""
            severity_order = ["critical", "high", "medium", "low", "info"]
            
            for sev in severity_order:
                sev_findings = [f for f in findings if f["severity"] == sev]
                if sev_findings:
                    findings_md += f"\n### {sev.upper()} Severity\n\n"
                    for f in sev_findings:
                        evidence_section = f"\n**Evidence:**\n```\n{f['evidence']}\n```\n" if include_ev else ""
                        findings_md += f"#### {f['id']}: {f['title']}\n\n"
                        findings_md += f"**Severity:** {f['severity'].upper()} | **Status:** {f['status']}\n\n"
                        findings_md += f"**Description:**\n{f['description']}\n"
                        findings_md += evidence_section
                        findings_md += f"\n**Recommendation:**\n{f['recommendation']}\n\n---\n\n"
            
            report_content = f"# Penetration Test Report\n\n"
            report_content += f"**Target:** {target}\n"
            report_content += f"**Generated:** {timestamp}\n"
            report_content += f"**Scope:** {', '.join(scope) if scope else 'Not defined'}\n\n"
            report_content += "---\n\n"
            report_content += "## Executive Summary\n\n"
            report_content += f"This penetration test assessment identified **{len(findings)}** security findings:\n\n"
            report_content += f"| Severity | Count |\n|----------|-------|\n"
            report_content += f"| Critical | {severity_counts.get('critical', 0)} |\n"
            report_content += f"| High | {severity_counts.get('high', 0)} |\n"
            report_content += f"| Medium | {severity_counts.get('medium', 0)} |\n"
            report_content += f"| Low | {severity_counts.get('low', 0)} |\n"
            report_content += f"| Info | {severity_counts.get('info', 0)} |\n\n"
            report_content += "---\n\n"
            report_content += "## Findings\n"
            report_content += findings_md
            report_content += "\n---\n\n*Report generated by Burp Suite MCP Server*\n"
            filename += ".md"
        
        report_path = REPORTS_DIR / filename
        async with aiofiles.open(report_path, 'w') as f:
            await f.write(report_content)
        
        logger.info(f"Report generated: {report_path}")
        
        result = "[OK] Report Generated\n\n"
        result += f"Format: {format_type.upper()}\n"
        result += f"Filename: {filename}\n"
        result += f"Path: {report_path}\n\n"
        result += f"Summary:\n"
        result += f"  - Total Findings: {len(findings)}\n"
        result += f"  - Critical: {severity_counts.get('critical', 0)}\n"
        result += f"  - High: {severity_counts.get('high', 0)}\n"
        result += f"  - Medium: {severity_counts.get('medium', 0)}\n"
        result += f"  - Low: {severity_counts.get('low', 0)}\n"
        result += f"  - Info: {severity_counts.get('info', 0)}"
        return result
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return f"[ERROR] Error generating report: {str(e)}"

@mcp.tool()
async def run_workflow(workflow_name: str = "", target: str = "") -> str:
    """Run a predefined testing workflow."""
    target_url = target.strip() or session_data.get("target", "")
    if not target_url:
        return "[ERROR] No target specified. Use set_target first."
    
    try:
        workflows = {
            "quick_scan": {
                "name": "Quick Security Scan",
                "steps": [
                    "1. Technology fingerprinting",
                    "2. Port and service detection",
                    "3. Common vulnerability checks",
                    "4. Security header analysis",
                    "5. SSL/TLS configuration review"
                ],
                "duration": "15-30 minutes"
            },
            "owasp_top10": {
                "name": "OWASP Top 10 Assessment",
                "steps": [
                    "1. A01 - Broken Access Control testing",
                    "2. A02 - Cryptographic failures check",
                    "3. A03 - Injection testing (SQL, Command, etc.)",
                    "4. A04 - Insecure design review",
                    "5. A05 - Security misconfiguration",
                    "6. A06 - Vulnerable components scan",
                    "7. A07 - Authentication testing",
                    "8. A08 - Software integrity verification",
                    "9. A09 - Logging and monitoring check",
                    "10. A10 - SSRF testing"
                ],
                "duration": "2-4 hours"
            },
            "api_security": {
                "name": "API Security Assessment",
                "steps": [
                    "1. API endpoint discovery",
                    "2. Authentication mechanism analysis",
                    "3. Authorization testing (BOLA/IDOR)",
                    "4. Rate limiting verification",
                    "5. Input validation testing",
                    "6. Data exposure analysis",
                    "7. Error handling review"
                ],
                "duration": "1-2 hours"
            },
            "authentication": {
                "name": "Authentication Security Review",
                "steps": [
                    "1. Login mechanism analysis",
                    "2. Password policy verification",
                    "3. Session management testing",
                    "4. Multi-factor authentication review",
                    "5. Account lockout testing",
                    "6. Password reset flow analysis",
                    "7. Remember me functionality"
                ],
                "duration": "1-2 hours"
            }
        }
        
        if workflow_name not in workflows:
            available = "\n".join([f"  - {k}: {v['name']}" for k, v in workflows.items()])
            return f"[LIST] Available Workflows\n\n{available}\n\nUsage: run_workflow('workflow_name', 'target_url')"
        
        workflow = workflows[workflow_name]
        steps_list = "\n".join([f"  {s}" for s in workflow["steps"]])
        
        session_data["current_workflow"] = {
            "name": workflow_name,
            "target": target_url,
            "started": datetime.now(timezone.utc).isoformat(),
            "current_step": 0
        }
        
        result = f"[START] Workflow Started: {workflow['name']}\n\n"
        result += f"Target: {target_url}\n"
        result += f"Estimated Duration: {workflow['duration']}\n\n"
        result += f"Steps:\n{steps_list}\n\n"
        result += "Instructions:\n"
        result += "I will guide you through each step. For each step:\n"
        result += "1. I will explain what to test\n"
        result += "2. Provide specific payloads/techniques\n"
        result += "3. Help you record findings\n\n"
        result += "Ready to begin? Say 'next' to start Step 1.\n\n"
        result += "[WARNING] Ensure you have written authorization before testing."
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def encode_payload(payload: str = "", encoding: str = "url") -> str:
    """Encode a payload for testing."""
    if not payload.strip():
        return "[ERROR] Payload is required"
    
    try:
        import base64
        import urllib.parse
        import html
        
        results = {}
        
        if encoding == "all" or encoding == "url":
            results["URL Encoded"] = urllib.parse.quote(payload)
            results["Double URL"] = urllib.parse.quote(urllib.parse.quote(payload))
        
        if encoding == "all" or encoding == "base64":
            results["Base64"] = base64.b64encode(payload.encode()).decode()
        
        if encoding == "all" or encoding == "html":
            results["HTML Entities"] = html.escape(payload)
            results["HTML Numeric"] = "".join([f"&#{ord(c)};" for c in payload])
        
        if encoding == "all" or encoding == "hex":
            results["Hex"] = payload.encode().hex()
        
        result = f"[ENCODE] Payload Encoding\n\nOriginal: {payload}\n\nEncoded Versions:\n"
        for name, encoded in results.items():
            result += f"\n{name}:\n{encoded}\n"
        
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def decode_payload(payload: str = "", encoding: str = "url") -> str:
    """Decode an encoded payload."""
    if not payload.strip():
        return "[ERROR] Payload is required"
    
    try:
        import base64
        import urllib.parse
        
        decoded = ""
        
        if encoding == "url":
            decoded = urllib.parse.unquote(payload)
        elif encoding == "base64":
            decoded = base64.b64decode(payload).decode()
        elif encoding == "hex":
            decoded = bytes.fromhex(payload.replace("\\x", "").replace("0x", "")).decode()
        else:
            return f"[ERROR] Unknown encoding: {encoding}. Use: url, base64, hex"
        
        result = f"[DECODE] Payload Decoded\n\n"
        result += f"Encoded ({encoding}):\n{payload}\n\n"
        result += f"Decoded:\n{decoded}"
        return result
    except Exception as e:
        return f"[ERROR] Decoding error: {str(e)}"

@mcp.tool()
async def analyze_response(response_body: str = "", check_type: str = "all") -> str:
    """Analyze an HTTP response for security issues."""
    if not response_body.strip():
        return "[ERROR] Response body is required"
    
    try:
        issues = []
        info = []
        
        security_patterns = {
            "SQL Error": ["mysql", "sqlite", "postgresql", "ora-", "sql syntax", "sqlstate"],
            "Path Disclosure": ["/var/www", "/home/", "c:\\", "\\users\\", "/usr/"],
            "Stack Trace": ["traceback", "exception", "error at line", "stack trace"],
            "Debug Info": ["debug", "phpinfo", "server_software", "x-powered-by"],
            "Sensitive Data": ["password", "secret", "api_key", "token", "bearer"],
            "Version Disclosure": ["version", "powered by", "server:", "x-aspnet-version"]
        }
        
        response_lower = response_body.lower()
        
        for issue_type, patterns in security_patterns.items():
            for pattern in patterns:
                if pattern in response_lower:
                    issues.append(f"[WARNING] {issue_type}: Found '{pattern}'")
                    break
        
        info.append(f"[SIZE] Response Length: {len(response_body)} bytes")
        
        if "<form" in response_lower:
            form_count = response_lower.count("<form")
            info.append(f"[NOTE] Forms Found: {form_count}")
        
        if "<script" in response_lower:
            script_count = response_lower.count("<script")
            info.append(f"[SCRIPT] Scripts Found: {script_count}")
        
        issues_text = "\n".join(issues) if issues else "No obvious security issues detected."
        info_text = "\n".join(info)
        
        result = "[SEARCH] Response Analysis\n\n"
        result += f"Security Issues:\n{issues_text}\n\n"
        result += f"Information:\n{info_text}"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def get_session_status() -> str:
    """Get the current testing session status and statistics."""
    try:
        target = session_data.get("target", "Not set")
        scope_count = len(session_data.get("scope", []))
        findings_count = len(session_data.get("findings", []))
        scan_count = len(session_data.get("scan_history", []))
        current_workflow = session_data.get("current_workflow")
        
        findings = session_data.get("findings", [])
        severity_counts = {}
        for f in findings:
            sev = f["severity"]
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        workflow_status = "None active"
        if current_workflow:
            workflow_status = f"{current_workflow['name']} (Step {current_workflow['current_step']})"
        
        result = "[STATS] Session Status\n\n"
        result += f"Target: {target}\n"
        result += f"Scope Items: {scope_count}\n"
        result += f"Current Workflow: {workflow_status}\n\n"
        result += f"Findings Summary:\n"
        result += f"  - Total: {findings_count}\n"
        result += f"  - Critical: {severity_counts.get('critical', 0)}\n"
        result += f"  - High: {severity_counts.get('high', 0)}\n"
        result += f"  - Medium: {severity_counts.get('medium', 0)}\n"
        result += f"  - Low: {severity_counts.get('low', 0)}\n"
        result += f"  - Info: {severity_counts.get('info', 0)}\n\n"
        result += f"Scan History: {scan_count} scans completed\n\n"
        result += f"Burp Connection:\n"
        result += f"  - Proxy: {get_burp_proxy_url()}\n"
        result += f"  - API: {get_burp_api_url()}"
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

@mcp.tool()
async def clear_session() -> str:
    """Clear all session data including findings and scan history."""
    try:
        findings_count = len(session_data["findings"])
        
        session_data["target"] = ""
        session_data["scope"] = []
        session_data["findings"] = []
        session_data["scan_history"] = []
        session_data["current_workflow"] = None
        
        logger.info("Session cleared")
        
        result = "[CLEAR] Session Cleared\n\n"
        result += f"Removed:\n"
        result += f"  - Target configuration\n"
        result += f"  - {findings_count} findings\n"
        result += f"  - Scan history\n"
        result += f"  - Active workflow\n\n"
        result += "The session is now reset. Use set_target to begin a new assessment."
        return result
    except Exception as e:
        return f"[ERROR] {str(e)}"

if __name__ == "__main__":
    logger.info("Starting Burp Suite MCP Server...")
    logger.info(f"Burp Proxy: {get_burp_proxy_url()}")
    logger.info(f"Burp API: {get_burp_api_url()}")
    
    try:
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)
