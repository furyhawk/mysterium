import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mysterium.history import (
    HistoryStore,
    conversation_to_markdown,
    markdown_to_html,
    report_to_markdown,
)
from mysterium.main import app

SAMPLE_REPORT = {
    "title": "AI in Healthcare",
    "summary": "A short executive summary.",
    "key_findings": ["Finding one", "Finding two"],
    "sections": [
        {"heading": "Overview", "content": "Body text.", "sources": ["doc.pdf"]},
    ],
    "gaps": ["More data needed"],
    "sources": [
        {"title": "doc.pdf", "relevance": "Directly relevant", "excerpt": "An excerpt"},
    ],
    "generated_at": "2026-08-18T12:00:00+00:00",
}


class HistoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = HistoryStore(root=self._tmp.name, enabled=True)

    def test_save_and_load_report(self) -> None:
        record = self.store.save_report(
            SAMPLE_REPORT,
            query="healthcare AI",
            collection_name="documents",
            model="m",
        )
        self.assertIsNotNone(record)
        self.assertIn("report_id", record)

        report_id = record["report_id"]
        path = Path(self._tmp.name) / "reports" / f"{report_id}.json"
        self.assertTrue(path.exists())

        loaded = self.store.load_report(report_id)
        self.assertEqual(loaded["title"], SAMPLE_REPORT["title"])
        self.assertEqual(loaded["query"], "healthcare AI")
        self.assertEqual(loaded["collection_name"], "documents")

    def test_list_reports_newest_first(self) -> None:
        first = self.store.save_report(
            {**SAMPLE_REPORT, "title": "A"},
            query="a", collection_name="documents", model="m",
        )
        time.sleep(0.002)
        second = self.store.save_report(
            {**SAMPLE_REPORT, "title": "B"},
            query="b", collection_name="documents", model="m",
        )
        items = self.store.list_reports()
        self.assertEqual([r["id"] for r in items], [second["report_id"], first["report_id"]])
        self.assertEqual(items[0]["title"], "B")
        self.assertEqual(items[0]["query"], "b")

    def test_delete_report(self) -> None:
        record = self.store.save_report(
            SAMPLE_REPORT, query="q", collection_name="documents", model="m"
        )
        self.assertTrue(self.store.delete_report(record["report_id"]))
        self.assertIsNone(self.store.load_report(record["report_id"]))
        self.assertFalse(self.store.delete_report(record["report_id"]))

    def test_append_and_load_chat(self) -> None:
        self.store.append_chat(
            "abc123",
            user_message="What is X?",
            assistant_message={"content": "X is Y", "sources": [], "images": []},
            collection_name="documents",
        )
        self.store.append_chat(
            "abc123",
            user_message="And Z?",
            assistant_message={"content": "Z is W"},
            collection_name="documents",
        )

        loaded = self.store.load_chat("abc123")
        self.assertEqual(len(loaded["messages"]), 4)
        self.assertEqual(loaded["title"], "What is X?")
        self.assertEqual(loaded["messages"][0]["role"], "user")
        self.assertEqual(loaded["messages"][1]["role"], "assistant")
        self.assertEqual(loaded["messages"][1]["content"], "X is Y")
        self.assertIn("updated_at", loaded)

    def test_list_and_delete_chat(self) -> None:
        self.store.append_chat(
            "c1", user_message="hi", assistant_message={"content": "yo"},
            collection_name="documents",
        )
        self.store.append_chat(
            "c2", user_message="hey", assistant_message={"content": "sup"},
            collection_name="documents",
        )
        items = self.store.list_chats()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["message_count"], 2)

        self.assertTrue(self.store.delete_chat("c1"))
        self.assertIsNone(self.store.load_chat("c1"))
        self.assertFalse(self.store.delete_chat("c1"))

    def test_disabled_store_does_not_write(self) -> None:
        store = HistoryStore(root=self._tmp.name, enabled=False)
        self.assertIsNone(
            store.save_report(SAMPLE_REPORT, query="q", collection_name="d", model="m")
        )
        self.assertEqual(store.list_reports(), [])
        self.assertIsNone(
            store.append_chat(
                "x", user_message="hi", assistant_message={"content": "yo"},
                collection_name="d",
            )
        )
        self.assertEqual(store.list_chats(), [])
        self.assertIsNone(store.load_report("any"))

    def test_path_traversal_rejected(self) -> None:
        for bad in ("..", "../x", "a/b", ""):
            self.assertIsNone(self.store.load_report(bad))
            self.assertFalse(self.store.delete_report(bad))


class MarkdownExportTests(unittest.TestCase):
    def test_report_to_markdown(self) -> None:
        md = report_to_markdown(SAMPLE_REPORT)
        self.assertIn("# AI in Healthcare", md)
        self.assertIn("## Summary", md)
        self.assertIn("- Finding one", md)
        self.assertIn("## Overview", md)
        self.assertIn("## Sources", md)
        self.assertIn("### doc.pdf", md)
        self.assertIn("> An excerpt", md)

    def test_conversation_to_markdown(self) -> None:
        chat = {
            "id": "c1",
            "title": "Intro",
            "created_at": "2026-08-18T12:00:00+00:00",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
        }
        md = conversation_to_markdown(chat)
        self.assertIn("# Intro", md)
        self.assertIn("### User 1", md)
        self.assertIn("Hello", md)
        self.assertIn("### Assistant 2", md)
        self.assertIn("Hi there", md)

    def test_markdown_to_html(self) -> None:
        html = markdown_to_html("# Hello\n\nSome **bold** text.\n\n- item", title="Hello")
        self.assertIn("<h1>Hello</h1>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<li>item</li>", html)
        self.assertIn("<title>Hello</title>", html)
        self.assertTrue(html.rstrip().endswith("</html>"))


class HistoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._env = patch.dict(
            os.environ,
            {"DATA_DIR": self._tmp.name, "HISTORY_ENABLED": "true"},
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        self.client = TestClient(app)

    def _save_report(self) -> dict:
        store = HistoryStore(root=self._tmp.name, enabled=True)
        return store.save_report(
            SAMPLE_REPORT, query="q", collection_name="documents", model="m"
        )

    def test_list_get_and_export_report(self) -> None:
        record = self._save_report()
        report_id = record["report_id"]

        res = self.client.get("/api/history/reports")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["items"][0]["id"], report_id)

        res = self.client.get(f"/api/history/reports/{report_id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["title"], SAMPLE_REPORT["title"])

        for fmt, media in (
            ("md", "text/markdown"),
            ("json", "application/json"),
            ("html", "text/html"),
        ):
            res = self.client.get(f"/api/history/reports/{report_id}/export?format={fmt}")
            self.assertEqual(res.status_code, 200)
            self.assertIn("attachment", res.headers["content-disposition"])
            self.assertIn(media, res.headers["content-type"])
            self.assertIn(f"{report_id}.{fmt}", res.headers["content-disposition"])

    def test_report_404_and_bad_format(self) -> None:
        res = self.client.get("/api/history/reports/does-not-exist")
        self.assertEqual(res.status_code, 404)

        record = self._save_report()
        res = self.client.get(
            f"/api/history/reports/{record['report_id']}/export?format=pdf"
        )
        self.assertEqual(res.status_code, 400)

    def test_delete_report_endpoint(self) -> None:
        record = self._save_report()
        res = self.client.delete(f"/api/history/reports/{record['report_id']}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "deleted"})

        res = self.client.get(f"/api/history/reports/{record['report_id']}")
        self.assertEqual(res.status_code, 404)

    def test_chat_endpoints(self) -> None:
        HistoryStore(root=self._tmp.name, enabled=True).append_chat(
            "c1",
            user_message="hi",
            assistant_message={"content": "yo", "sources": []},
            collection_name="documents",
        )

        res = self.client.get("/api/history/chats")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["items"][0]["id"], "c1")

        res = self.client.get("/api/history/chats/c1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["messages"][1]["content"], "yo")

        res = self.client.get("/api/history/chats/c1/export?format=md")
        self.assertEqual(res.status_code, 200)
        self.assertIn("hi", res.text)

        res = self.client.delete("/api/history/chats/c1")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/api/history/chats/c1")
        self.assertEqual(res.status_code, 404)

    def test_disabled_history(self) -> None:
        with patch.dict(
            os.environ,
            {"DATA_DIR": self._tmp.name, "HISTORY_ENABLED": "false"},
        ):
            res = self.client.get("/api/history/reports")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json(), {"items": []})

            res = self.client.get("/api/history/reports/any")
            self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
