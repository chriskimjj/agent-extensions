#!/usr/bin/env python3
"""discord-related-threads plugin.

Registers a tool for managing explicit thread relations and a transform_llm_output
hook that appends a related-thread footer to final answers when the current
session is a Discord thread with registered relations.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .thread_attention import ThreadAttentionRuntime, load_thread_attention_config
except ImportError:  # Direct-file test loading outside Hermes' package loader.
    from thread_attention import ThreadAttentionRuntime, load_thread_attention_config

# --- SQLite graph ---------------------------------------------------------

_DB_PATH = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser() / "discord-related-threads" / "relations.sqlite3"
_DB_LOCK = threading.RLock()
_THREAD_ATTENTION_RUNTIME: Optional[ThreadAttentionRuntime] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS relations (
    guild_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    related_thread_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'related',
    label TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, thread_id, related_thread_id)
);
CREATE INDEX IF NOT EXISTS idx_relations_lookup
    ON relations (guild_id, thread_id);
CREATE INDEX IF NOT EXISTS idx_relations_reverse
    ON relations (guild_id, related_thread_id);
"""


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _DB_LOCK, closing(_get_conn()) as conn, conn:
        conn.executescript(_SCHEMA)


def _utc_now() -> str:
    return datetime.now().isoformat()


# --- Public API -----------------------------------------------------------

def link_threads(
    guild_id: str,
    thread_id: str,
    related_thread_id: str,
    relation: str = "related",
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a bidirectional relation between two threads."""
    if thread_id == related_thread_id:
        return {"success": False, "error": "thread_id and related_thread_id must differ"}

    relation = (relation or "related").strip() or "related"
    now = _utc_now()

    with _DB_LOCK, closing(_get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for a, b in ((thread_id, related_thread_id), (related_thread_id, thread_id)):
                conn.execute(
                    """INSERT OR REPLACE INTO relations
                       (guild_id, thread_id, related_thread_id, relation, label, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (guild_id, a, b, relation, label, now),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            return {"success": False, "error": str(e)}

    return {"success": True, "guild_id": guild_id, "thread_id": thread_id, "related_thread_id": related_thread_id}


def unlink_threads(
    guild_id: str,
    thread_id: str,
    related_thread_id: str,
) -> Dict[str, Any]:
    """Remove a bidirectional relation."""
    if thread_id == related_thread_id:
        return {"success": False, "error": "thread_id and related_thread_id must differ"}

    with _DB_LOCK, closing(_get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for a, b in ((thread_id, related_thread_id), (related_thread_id, thread_id)):
                conn.execute(
                    "DELETE FROM relations WHERE guild_id=? AND thread_id=? AND related_thread_id=?",
                    (guild_id, a, b),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            return {"success": False, "error": str(e)}

    return {"success": True, "guild_id": guild_id, "thread_id": thread_id, "related_thread_id": related_thread_id}


def list_relations(guild_id: str, thread_id: str) -> Dict[str, Any]:
    """List all relations for a thread."""
    with _DB_LOCK, closing(_get_conn()) as conn, conn:
        rows = conn.execute(
            "SELECT related_thread_id, relation, label, created_at FROM relations WHERE guild_id=? AND thread_id=? ORDER BY created_at",
            (guild_id, thread_id),
        ).fetchall()

    return {
        "success": True,
        "guild_id": guild_id,
        "thread_id": thread_id,
        "relations": [dict(r) for r in rows],
    }


def _build_footer(relations: List[Dict[str, Any]], guild_id: str) -> str:
    if not relations:
        return ""

    # Deduplicate by related_thread_id keeping the first entry
    seen = set()
    uniq = []
    for r in relations:
        rid = r["related_thread_id"]
        if rid in seen:
            continue
        seen.add(rid)
        uniq.append(r)

    # Take at most 4
    uniq = uniq[:4]

    lines = ["\n---\n관련 스레드:"]
    for r in uniq:
        relation = r.get("relation") or "related"
        label = r.get("label")
        rid = r["related_thread_id"]
        link = f"https://discord.com/channels/{guild_id}/{rid}"
        if label:
            lines.append(f"- [{label}] ({relation}) — {link}")
        else:
            lines.append(f"- {relation}: {link}")

    return "\n".join(lines)


# --- transform_llm_output hook -------------------------------------------

_DISCORD_THREAD_SESSION_KEY_RE = re.compile(r"agent:main:discord:thread:(\d+):\1$")


def _resolve_current_discord_thread() -> Optional[Dict[str, str]]:
    """Try to recover guild_id and thread_id from the active session row in state.db.

    The active session id is not directly exposed to the hook, but the gateway
    runner stores the session row with the session_key containing guild+thread.
    We search for the most recent session matching the current process.
    """
    try:
        hermes_home = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
        state_db = hermes_home / "state.db"
        if not state_db.exists():
            return None

        with closing(
            sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
        ) as conn, conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT session_key, origin_json FROM sessions
                   WHERE source='discord' AND session_key LIKE 'agent:main:discord:thread:%:%'
                   ORDER BY started_at DESC LIMIT 1"""
            ).fetchone()

        if not row:
            return None

        session_key = row["session_key"]
        m = _DISCORD_THREAD_SESSION_KEY_RE.search(session_key)
        if not m:
            return None

        thread_id = m.group(1)
        origin = json.loads(row["origin_json"] or "{}")
        guild_id = origin.get("guild_id") or origin.get("scope_id")
        if not guild_id:
            return None

        return {"guild_id": str(guild_id), "thread_id": thread_id}
    except Exception:
        return None


def _on_transform_llm_output(**kwargs) -> Optional[str]:
    """Hook callback: if current session is a Discord thread with relations, append footer."""
    response_text = kwargs.get("response_text", "")
    if not response_text or not isinstance(response_text, str):
        return None

    # Avoid double-appending
    if "관련 스레드:" in response_text:
        return None

    current = _resolve_current_discord_thread()
    if not current:
        return None

    guild_id = current["guild_id"]
    thread_id = current["thread_id"]

    relations_data = list_relations(guild_id, thread_id)
    if not relations_data.get("success") or not relations_data.get("relations"):
        return None

    footer = _build_footer(relations_data["relations"], guild_id)
    if not footer:
        return None

    return response_text.rstrip() + footer


# --- Plugin registration --------------------------------------------------

def register(ctx) -> None:
    global _THREAD_ATTENTION_RUNTIME
    _init_db()

    # Tool: discord_thread_links (link / list / unlink)
    LINK_SCHEMA = {
        "name": "discord_thread_links",
        "description": "Manage and view explicit related-thread relations for Discord work threads. Use subcommands: link, list, unlink.",
        "parameters": {
            "type": "object",
            "properties": {
                "subcommand": {"type": "string", "enum": ["link", "list", "unlink"], "description": "Action to perform"},
                "guild_id": {"type": "string", "description": "Discord guild (server) ID"},
                "thread_id": {"type": "string", "description": "Source thread ID"},
                "related_thread_id": {"type": "string", "description": "Target thread ID for link/unlink"},
                "relation": {"type": "string", "description": "Relation type (default: related)"},
                "label": {"type": "string", "description": "Optional display label"},
            },
            "required": ["subcommand", "guild_id", "thread_id"],
        },
    }

    def handle_links(params: Dict[str, Any], **kwargs) -> str:
        sub = params.get("subcommand")
        guild_id = params.get("guild_id")
        thread_id = params.get("thread_id")

        if sub == "link":
            related = params.get("related_thread_id")
            if not related:
                return json.dumps({"success": False, "error": "related_thread_id required for link"})
            res = link_threads(
                guild_id,
                thread_id,
                related,
                params.get("relation"),
                params.get("label"),
            )
            return json.dumps(res, ensure_ascii=False)

        if sub == "unlink":
            related = params.get("related_thread_id")
            if not related:
                return json.dumps({"success": False, "error": "related_thread_id required for unlink"})
            res = unlink_threads(guild_id, thread_id, related)
            return json.dumps(res, ensure_ascii=False)

        if sub == "list":
            res = list_relations(guild_id, thread_id)
            return json.dumps(res, ensure_ascii=False)

        return json.dumps({"success": False, "error": f"unknown subcommand: {sub}"})

    ctx.register_tool(
        name="discord_thread_links",
        toolset="discord_related_threads",
        schema=LINK_SCHEMA,
        handler=handle_links,
        description="Manage and view explicit related-thread relations for Discord work threads.",
    )

    # Hook: transform_llm_output
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)

    # Thread attention remains independently disabled unless the profile's
    # plugins.entries.discord-related-threads.thread_attention.enabled is true.
    # The hooks are still registered so existing exclusion-ledger IDs remain
    # filterable if the feature is later disabled.
    required_host_hooks = (
        "pre_gateway_dispatch",
        "gateway_control_message",
        "gateway_history_message",
    )
    required_context_methods = (
        "register_platform_handler",
        "spawn_task",
        "on_unload",
    )
    host_contract_issues = []
    supports_hook = getattr(ctx, "supports_hook", None)
    if not callable(supports_hook):
        host_contract_issues.append("hook compatibility probe is missing")
    else:
        missing_hooks = [name for name in required_host_hooks if not supports_hook(name)]
        if missing_hooks:
            host_contract_issues.append("missing hooks: " + ", ".join(missing_hooks))
    missing_context_methods = [
        name for name in required_context_methods if not callable(getattr(ctx, name, None))
    ]
    if missing_context_methods:
        host_contract_issues.append(
            "missing context methods: " + ", ".join(missing_context_methods)
        )
    host_contract_error = (
        "unsupported Hermes plugin host; " + "; ".join(host_contract_issues)
        if host_contract_issues
        else None
    )
    _THREAD_ATTENTION_RUNTIME = ThreadAttentionRuntime(
        load_thread_attention_config(),
        host_contract_error=host_contract_error,
    )
    ctx.register_hook(
        "pre_gateway_dispatch",
        _THREAD_ATTENTION_RUNTIME.on_pre_gateway_dispatch,
    )
    ctx.register_hook(
        "gateway_history_message",
        _THREAD_ATTENTION_RUNTIME.on_history_message,
    )
    ctx.register_hook(
        "gateway_control_message",
        _THREAD_ATTENTION_RUNTIME.on_control_message,
    )

    # Stock-Hermes lifecycle and live Discord observation.  The native handler
    # factory runs only when Discord connects, so plugin registration remains
    # safe in CLI processes where discord.py is not loaded.
    register_platform_handler = getattr(ctx, "register_platform_handler", None)
    spawn_task = getattr(ctx, "spawn_task", None)
    if callable(register_platform_handler):
        def wire_discord(native, adapter) -> None:
            _THREAD_ATTENTION_RUNTIME.on_discord_connected(
                native=native,
                adapter=adapter,
                spawn_task=spawn_task if callable(spawn_task) else None,
            )

        register_platform_handler("discord", wire_discord)

    on_unload = getattr(ctx, "on_unload", None)
    if callable(on_unload):
        on_unload(_THREAD_ATTENTION_RUNTIME.on_unload)
