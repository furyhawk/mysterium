"""Filesystem persistence for research reports and chat transcripts.

Mysterium is otherwise stateless: reports and chat turns are generated on
demand and returned over HTTP/SSE. This module adds an optional, non-fatal
history layer that writes each successful artifact to disk as JSON:

- ``<data_dir>/reports/<report_id>.json``      — a full research report plus
  metadata (``report_id``, ``query``, ``collection_name``, ``model``,
  ``saved_at``).
- ``<data_dir>/chats/<conversation_id>.json``  — a multi-turn chat transcript
  (``id``, ``title``, ``created_at``, ``updated_at``, ``messages``).

Markdown (and a standalone HTML page) are rendered on demand from the JSON so
export works without storing redundant files. Persistence is best-effort:
every method catches its own I/O errors and logs a warning, so a failed save
never breaks the request that generated the artifact.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Constants & small helpers ──────────────────────────────────────

# Safe filename charset: ids are UUIDs (hex + dashes) but we keep a small
# whitelist so URL paths can never escape the reports/chats directories.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _is_safe_name(name: str) -> bool:
    """Return True when ``name`` is safe to use as a filename."""
    return bool(name) and name not in (".", "..") and _SAFE_NAME_RE.match(name) is not None


def _now_iso() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.datetime.now(datetime.UTC).isoformat()


def _format_ts(value: str) -> str:
    """Best-effort ISO timestamp → ``YYYY-MM-DD HH:MM`` local time."""
    try:
        return datetime.datetime.fromisoformat(value).astimezone().strftime(
            "%Y-%m-%d %H:%M"
        )
    except (TypeError, ValueError):
        return value or ""


def _make_title(text: str, limit: int = 60) -> str:
    """Derive a short conversation title from the first user message."""
    line = next(
        (ln.strip() for ln in (text or "").splitlines() if ln.strip()),
        (text or "").strip(),
    )
    line = re.sub(r"[#*`>_\-]+", " ", line).strip()
    if not line:
        line = "Conversation"
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def _escape_html(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── HistoryStore ────────────────────────────────────────────────────


class HistoryStore:
    """Filesystem-backed store for reports and chat transcripts."""

    def __init__(self, root: str | Path = "./data", enabled: bool = True) -> None:
        self.root = Path(root)
        self.enabled = enabled
        self.reports_dir = self.root / "reports"
        self.chats_dir = self.root / "chats"

    # ── low-level file helpers ─────────────────────────────────────

    @staticmethod
    def _write_json(directory: Path, name: str, data: dict) -> None:
        """Atomically write ``data`` to ``directory/name`` (tmp + rename)."""
        directory.mkdir(parents=True, exist_ok=True)
        tmp = directory / f".{name}.{uuid.uuid4().hex}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, directory / name)

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _scan(self, directory: Path) -> list[tuple[str, dict]]:
        """Return ``(stem, data)`` pairs for every ``*.json`` file in dir."""
        if not self.enabled or not directory.is_dir():
            return []
        pairs: list[tuple[str, dict]] = []
        for path in directory.glob("*.json"):
            data = self._read_json(path)
            if data is not None:
                pairs.append((path.stem, data))
        return pairs

    # ── reports ────────────────────────────────────────────────────

    def save_report(
        self,
        report: dict,
        *,
        query: str,
        collection_name: str,
        model: str,
    ) -> dict | None:
        """Persist a research report, returning the stored record (or None).

        The returned record is the report dict extended with ``report_id``,
        ``query``, ``collection_name``, ``model`` and ``saved_at``. Callers
        typically surface ``report_id`` back to the client so the UI can link
        to the history entry.
        """
        if not self.enabled or not report:
            return None
        try:
            record = dict(report)
            record["report_id"] = record.get("report_id") or uuid.uuid4().hex
            record["query"] = query
            record["collection_name"] = collection_name
            record["model"] = model
            record["saved_at"] = _now_iso()
            self._write_json(
                self.reports_dir, f"{record['report_id']}.json", record
            )
            return record
        except OSError as e:
            logger.warning("Failed to save report: %s", e)
            return None

    def list_reports(self) -> list[dict]:
        """Summaries of all saved reports, newest first."""
        items = []
        for stem, data in self._scan(self.reports_dir):
            items.append(
                {
                    "id": data.get("report_id") or stem,
                    "title": data.get("title") or "Untitled report",
                    "query": data.get("query", ""),
                    "model": data.get("model", ""),
                    "collection_name": data.get("collection_name", ""),
                    "saved_at": data.get("saved_at", ""),
                }
            )
        items.sort(key=lambda r: r["saved_at"], reverse=True)
        return items

    def load_report(self, report_id: str) -> dict | None:
        if not self.enabled or not _is_safe_name(report_id):
            return None
        return self._read_json(self.reports_dir / f"{report_id}.json")

    def delete_report(self, report_id: str) -> bool:
        if not self.enabled or not _is_safe_name(report_id):
            return False
        return self._delete(self.reports_dir / f"{report_id}.json")

    # ── chats ──────────────────────────────────────────────────────

    def append_chat(
        self,
        conversation_id: str,
        *,
        user_message: str,
        assistant_message: dict,
        collection_name: str,
    ) -> dict | None:
        """Append one turn (user + assistant) to a conversation transcript.

        Creates the transcript on first use, deriving the title from the first
        user message. Returns the updated transcript dict (or None on failure
        / when disabled).
        """
        if not self.enabled or not conversation_id:
            return None
        try:
            path = self.chats_dir / f"{conversation_id}.json"
            chat = self._read_json(path) or {}
            chat.setdefault("id", conversation_id)
            chat.setdefault("title", _make_title(user_message))
            chat.setdefault("collection_name", collection_name)
            chat.setdefault("created_at", _now_iso())

            messages = chat.setdefault("messages", [])
            messages.append({"role": "user", "content": user_message})
            assistant = dict(assistant_message)
            assistant["role"] = "assistant"
            messages.append(assistant)

            chat["updated_at"] = _now_iso()
            self._write_json(self.chats_dir, f"{conversation_id}.json", chat)
            return chat
        except OSError as e:
            logger.warning("Failed to append chat %r: %s", conversation_id, e)
            return None

    def list_chats(self) -> list[dict]:
        """Summaries of all saved conversations, most recent first."""
        items = []
        for stem, data in self._scan(self.chats_dir):
            messages = data.get("messages") or []
            items.append(
                {
                    "id": data.get("id") or stem,
                    "title": data.get("title") or "Untitled conversation",
                    "collection_name": data.get("collection_name", ""),
                    "message_count": len(messages),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                }
            )
        items.sort(key=lambda c: c["updated_at"], reverse=True)
        return items

    def load_chat(self, conversation_id: str) -> dict | None:
        if not self.enabled or not _is_safe_name(conversation_id):
            return None
        return self._read_json(self.chats_dir / f"{conversation_id}.json")

    def delete_chat(self, conversation_id: str) -> bool:
        if not self.enabled or not _is_safe_name(conversation_id):
            return False
        return self._delete(self.chats_dir / f"{conversation_id}.json")

    # ── shared ─────────────────────────────────────────────────────

    @staticmethod
    def _delete(path: Path) -> bool:
        """Remove a file; return False when it did not exist."""
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError as e:
            logger.warning("Failed to delete %s: %s", path, e)
            return False


# ── Markdown / HTML export rendering ────────────────────────────────


def report_to_markdown(report: dict) -> str:
    """Render a research report as Markdown (mirrors the frontend exporter)."""
    lines: list[str] = []

    if report.get("title"):
        lines.append(f"# {report['title']}\n")

    if report.get("summary"):
        lines.append("## Summary\n")
        lines.append(report["summary"] + "\n")

    images = report.get("images") or []
    if images:
        lines.append("## Images\n")
        for im in images:
            src = im.get("url") or f"/api/images/{im.get('image_id', '')}"
            lines.append(f"![{im.get('description') or 'Image'}]({src})")
            if im.get("page_num") is not None:
                lines.append(f"*Page {im['page_num']}*")
            lines.append("")

    findings = report.get("key_findings") or []
    if findings:
        lines.append("## Key Findings\n")
        lines.extend(f"- {f}" for f in findings)
        lines.append("")

    for sec in report.get("sections") or []:
        lines.append(f"## {sec.get('heading', '')}\n")
        lines.append((sec.get("content") or "") + "\n")
        if sec.get("sources"):
            lines.append(f"*Sources: {', '.join(sec['sources'])}*\n")

    gaps = report.get("gaps") or []
    if gaps:
        lines.append("## Knowledge Gaps\n")
        lines.extend(f"- {g}" for g in gaps)
        lines.append("")

    sources = report.get("sources") or []
    if sources:
        lines.append("## Sources\n")
        for s in sources:
            lines.append(f"### {s.get('title', '')}")
            lines.append(f"*{s.get('relevance', '')}*")
            lines.append(f"> {s.get('excerpt', '')}")
            lines.append("")

    if report.get("generated_at"):
        lines.append(f"---\n*Generated: {_format_ts(report['generated_at'])}*")

    return "\n".join(lines)


def conversation_to_markdown(chat: dict) -> str:
    """Render a chat transcript as Markdown."""
    title = chat.get("title") or "Conversation"
    messages = chat.get("messages") or []
    lines: list[str] = [f"# {title}\n"]

    updated = chat.get("updated_at") or chat.get("created_at") or ""
    if updated:
        lines.append(f"*Saved {_format_ts(updated)} · {len(messages)} message(s)*\n")

    for i, m in enumerate(messages, 1):
        role = "User" if m.get("role") == "user" else "Assistant"
        lines.append(f"### {role} {i}\n")
        lines.append((m.get("content") or "").strip() + "\n")

        sources = m.get("sources") or []
        if sources:
            lines.append("*Sources:*")
            for s in sources:
                name = s.get("filename") or "Unknown source"
                score = s.get("score")
                score_s = f" — {(float(score) * 100):.1f}%" if score is not None else ""
                lines.append(f"- {name}{score_s}")
            lines.append("")

        for im in m.get("images") or []:
            lines.append(f"![{im.get('description') or 'Image'}](/api/images/{im.get('image_id', '')})")

        lines.append("---")

    return "\n".join(lines).strip() + "\n"


def markdown_to_html(markdown_text: str, *, title: str = "Mysterium export") -> str:
    """Render the Markdown subset our exporters produce into a standalone page."""
    body = _render_markdown(markdown_text)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>{_escape_html(title)}</title>\n"
        "<style>"
        "body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;"
        "max-width:840px;margin:2.5rem auto;padding:0 1.25rem;line-height:1.65;color:#1f2328}"
        "h1,h2,h3,h4{line-height:1.25}h1{border-bottom:1px solid #d8dee4;padding-bottom:.3em}"
        "blockquote{border-left:3px solid #d0d7de;margin:1em 0;padding-left:1rem;color:#57606a}"
        "code{background:#f6f8fa;padding:.15em .35em;border-radius:4px;font-size:.9em}"
        "pre{background:#f6f8fa;padding:.9rem;border-radius:6px;overflow:auto}"
        "pre code{background:none;padding:0}"
        "hr{border:none;border-top:1px solid #d0d7de;margin:2rem 0}"
        "table{border-collapse:collapse;width:100%;margin:1em 0}"
        "td,th{border:1px solid #d0d7de;padding:.4rem .6rem}"
        "img{max-width:100%}"
        "</style>\n</head>\n<body>\n"
        f"{body}\n</body>\n</html>\n"
    )


def _render_markdown(md: str) -> str:
    """Render the CommonMark subset produced by our exporters into HTML.

    Handles fenced code blocks, ATX headings, blockquotes, tables (pipe rows),
    unordered/ordered lists, horizontal rules and paragraphs, plus inline
    code, bold, italic and links/images. Input is escaped first so model
    content can never inject raw markup.
    """
    escaped = _escape_html(md)

    # Protect fenced code blocks so block/inline rules never touch them.
    code_blocks: list[str] = []
    text = re.sub(
        r"```[^\n]*\n([\s\S]*?)```",
        lambda m: _save_code_block(m.group(1), code_blocks),
        escaped,
    )

    return _render_markdown_lines(text, code_blocks)


def _save_code_block(code: str, blocks: list[str]) -> str:
    blocks.append(code)
    return _code_placeholder(len(blocks) - 1)


def _code_placeholder(idx: int) -> str:
    return f"\u0000CODE\u0000{idx}\u0000"


def _render_markdown_lines(text: str, code_blocks: list[str]) -> str:
    lines = text.split("\n")
    html: list[str] = []
    i = 0

    is_blank = lambda l: l.strip() == ""
    quote_re = re.compile(r"^\s*&gt;\s?")
    h_re = re.compile(r"^(#{1,6})\s+(.*)$")
    ul_re = re.compile(r"^\s*[-*+]\s+")
    ol_re = re.compile(r"^\s*\d+\.\s+")
    hr_re = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}\s*$")
    code_re = re.compile(r"^\u0000CODE\u0000(\d+)\u0000$")
    table_delim_re = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")

    def is_table_start(line: str, n: int) -> bool:
        return is_table_row(line) and n + 1 < len(lines) and table_delim_re.match(lines[n + 1]) is not None

    while i < len(lines):
        line = lines[i]

        m_code = code_re.match(line)
        if m_code:
            html.append("<pre><code>" + code_blocks[int(m_code.group(1))] + "</code></pre>")
            i += 1
            continue

        m_h = h_re.match(line)
        if m_h:
            level = len(m_h.group(1))
            html.append(f"<h{level}>" + _md_inline(m_h.group(2)) + f"</h{level}>")
            i += 1
            continue

        if hr_re.match(line):
            html.append("<hr/>")
            i += 1
            continue

        if quote_re.match(line):
            quote = []
            while i < len(lines) and quote_re.match(lines[i]):
                quote.append(quote_re.sub("", lines[i]))
                i += 1
            html.append("<blockquote>" + _md_inline("\n".join(quote)) + "</blockquote>")
            continue

        if is_table_start(line, i):
            header = _table_row_cells(line)
            i += 2
            rows = []
            while i < len(lines) and is_table_row(lines[i]) and lines[i].strip() != "":
                rows.append(
                    "<tr>"
                    + "".join("<td>" + _md_inline(c) + "</td>" for c in _table_row_cells(lines[i]))
                    + "</tr>"
                )
                i += 1
            html.append(
                "<table><thead><tr>"
                + "".join("<th>" + _md_inline(c) + "</th>" for c in header)
                + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
            )
            continue

        if ul_re.match(line):
            items = []
            while i < len(lines) and ul_re.match(lines[i]):
                items.append("<li>" + _md_inline(ul_re.sub("", lines[i])) + "</li>")
                i += 1
            html.append("<ul>" + "".join(items) + "</ul>")
            continue

        if ol_re.match(line):
            items = []
            while i < len(lines) and ol_re.match(lines[i]):
                items.append("<li>" + _md_inline(ol_re.sub("", lines[i])) + "</li>")
                i += 1
            html.append("<ol>" + "".join(items) + "</ol>")
            continue

        if not is_blank(line):
            para = []
            while (
                i < len(lines)
                and not is_blank(lines[i])
                and not h_re.match(lines[i])
                and not ul_re.match(lines[i])
                and not ol_re.match(lines[i])
                and not quote_re.match(lines[i])
                and not hr_re.match(lines[i])
                and not code_re.match(lines[i])
                and not is_table_start(lines[i], i)
            ):
                para.append(lines[i])
                i += 1
            html.append("<p>" + _md_inline("<br/>".join(para)) + "</p>")
            continue

        i += 1

    return "\n".join(html)


def is_table_row(line: str) -> bool:
    return "|" in line and line.strip().startswith("|")


def _table_row_cells(line: str) -> list[str]:
    return line.strip().strip("|").split("|")


def _md_inline(text: str) -> str:
    # Inline code (protect first so other rules don't touch it).
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    # Images ![alt](url)
    t = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)\)",
        lambda m: f"<img src=\"{m.group(2)}\" alt=\"{m.group(1)}\" loading=\"lazy\" />",
        t,
    )
    # Links [text](url)
    t = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f"<a href=\"{m.group(2)}\">{m.group(1)}</a>",
        t,
    )
    # Bold
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    # Italic
    t = re.sub(r"(^|[\s(])\*([^*\s][^*]*?)\*([\s).,!?;:]|$)", r"\1<em>\2</em>\3", t)
    return t
