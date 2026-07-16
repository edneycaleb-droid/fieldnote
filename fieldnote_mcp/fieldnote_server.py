#!/usr/bin/env python3
"""
Fieldnote MCP Server (stdio transport)
Exposes the Fieldnote skill library to Claude Desktop as a local MCP server.

─── Claude Desktop setup ─────────────────────────────────────────────────────
Add to ~/.config/claude/claude_desktop_config.json  (Mac/Linux)
     %APPDATA%\Claude\claude_desktop_config.json    (Windows)

{
  "mcpServers": {
    "fieldnote": {
      "command": "python",
      "args": ["/ABSOLUTE/PATH/TO/fieldnote_mcp/fieldnote_server.py"]
    }
  }
}
──────────────────────────────────────────────────────────────────────────────

For Claude.ai / remote connection, use the /mcp/sse endpoint instead.
"""

import sys, json, os
from pathlib import Path

# ── Path resolution ─────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
SKILLS_DIR = ROOT / "fieldnote_skills"
INDEX_FILE = SKILLS_DIR / "_index.json"


# ── Tool definitions ─────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "list_skills",
        "description": (
            "List all skills in the Fieldnote library. Returns title, description, "
            "tags, tools, concepts, and how many video sources fed into each skill."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag":   {"type": "string",  "description": "Filter by tag (optional)"},
                "limit": {"type": "integer", "description": "Max results, default 25"},
            },
        },
    },
    {
        "name": "get_skill",
        "description": (
            "Get the FULL markdown content of a skill plus all its metadata. "
            "Use this to read the complete steps, tools, concepts, and sources."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name (no .md extension)"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "search_skills",
        "description": (
            "Full-text search across all skill titles, descriptions, tags, "
            "tools, concepts, and steps. Returns ranked results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_all_tools",
        "description": "List every tool, library, and API discovered across all skills.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_all_concepts",
        "description": "List every concept and technique accumulated across all skills.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_library_stats",
        "description": "Return high-level stats: skill count, total tools, concepts, packages.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ── Index helpers ─────────────────────────────────────────────────────────────
def load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception:
            pass
    return {}


# ── Tool execution ────────────────────────────────────────────────────────────
def call_tool(name: str, args: dict) -> dict:
    index = load_index()

    if name == "list_skills":
        tag   = (args.get("tag") or "").lower()
        limit = min(int(args.get("limit") or 25), 100)
        skills = []
        for skill_name, meta in index.items():
            if tag and tag not in [t.lower() for t in meta.get("tags", [])]:
                continue
            skills.append({
                "name":        skill_name,
                "title":       meta.get("title", skill_name),
                "description": meta.get("description", ""),
                "tags":        meta.get("tags", []),
                "tools":       meta.get("tools", [])[:10],
                "concepts":    meta.get("concepts", [])[:6],
                "updated_at":  meta.get("updated_at", ""),
                "source_count": len(meta.get("history", [])) + 1,
            })
        skills.sort(key=lambda x: x["updated_at"], reverse=True)
        return {"skills": skills[:limit], "total": len(index)}

    elif name == "get_skill":
        skill_name = (args.get("name") or "").strip()
        md_path    = SKILLS_DIR / f"{skill_name}.md"
        if not md_path.exists():
            # Case-insensitive fallback
            for f in SKILLS_DIR.glob("*.md"):
                if f.stem.lower() == skill_name.lower():
                    md_path    = f
                    skill_name = f.stem
                    break
            else:
                available = [p.stem for p in SKILLS_DIR.glob("*.md")][:10]
                return {
                    "error": f"Skill '{skill_name}' not found.",
                    "available_examples": available,
                }
        meta = index.get(skill_name, {})
        return {
            "name":         skill_name,
            "title":        meta.get("title", skill_name),
            "description":  meta.get("description", ""),
            "tags":         meta.get("tags", []),
            "tools":        meta.get("tools", []),
            "concepts":     meta.get("concepts", []),
            "steps":        meta.get("steps", []),
            "packages":     meta.get("python_packages", []),
            "source_count": len(meta.get("history", [])) + 1,
            "updated_at":   meta.get("updated_at", ""),
            "content":      md_path.read_text(),
        }

    elif name == "search_skills":
        query   = (args.get("query") or "").lower()
        results = []
        for skill_name, meta in index.items():
            haystack = " ".join([
                meta.get("title", ""),
                meta.get("description", ""),
                " ".join(meta.get("tags", [])),
                " ".join(meta.get("tools", [])),
                " ".join(meta.get("concepts", [])),
                " ".join(meta.get("steps", [])),
            ]).lower()
            score = sum(haystack.count(w) for w in query.split() if w)
            if score > 0:
                results.append({
                    "name":        skill_name,
                    "title":       meta.get("title", skill_name),
                    "description": meta.get("description", ""),
                    "tags":        meta.get("tags", []),
                    "tools":       meta.get("tools", [])[:6],
                    "score":       score,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"results": results[:12], "query": query, "total_matches": len(results)}

    elif name == "get_all_tools":
        all_tools: set = set()
        for meta in index.values():
            all_tools.update(meta.get("tools", []))
        return {"tools": sorted(all_tools), "count": len(all_tools)}

    elif name == "get_all_concepts":
        all_concepts: set = set()
        for meta in index.values():
            all_concepts.update(meta.get("concepts", []))
        return {"concepts": sorted(all_concepts), "count": len(all_concepts)}

    elif name == "get_library_stats":
        all_tools: set    = set()
        all_concepts: set = set()
        all_pkgs: set     = set()
        for meta in index.values():
            all_tools.update(meta.get("tools", []))
            all_concepts.update(meta.get("concepts", []))
            all_pkgs.update(meta.get("python_packages", []))
        return {
            "skills":   len(index),
            "tools":    len(all_tools),
            "concepts": len(all_concepts),
            "packages": len(all_pkgs),
        }

    else:
        return {"error": f"Unknown tool: {name}"}


# ── JSON-RPC helpers ──────────────────────────────────────────────────────────
def send(obj: dict):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def respond(req_id, result: dict):
    send({"jsonrpc": "2.0", "id": req_id, "result": result})


def error_resp(req_id, code: int, message: str):
    send({"jsonrpc": "2.0", "id": req_id,
          "error": {"code": code, "message": message}})


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            respond(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities":    {"tools": {}},
                "serverInfo":      {"name": "fieldnote", "version": "2.0.0"},
            })

        elif method == "initialized":
            pass  # notification — no response needed

        elif method == "tools/list":
            respond(req_id, {"tools": TOOLS})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            try:
                result = call_tool(tool_name, tool_args)
            except Exception as exc:
                result = {"error": str(exc)}
            respond(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
            })

        elif method == "ping":
            respond(req_id, {})

        else:
            if req_id is not None:
                error_resp(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
