#!/usr/bin/env python3
"""Integration tests for the Clinic NL2SQL agent.

Sends natural-language questions to the running Vanna chat_poll endpoint,
executes the same queries directly against SQLite, and compares results.

Prerequisites:
    The server must be running:  uvicorn app:app --host 0.0.0.0 --port 8000

Usage:
    python scripts/test_integration.py              # run all tests
    python scripts/test_integration.py --quick       # run first 5 only
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from datetime import datetime
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8000"
DB_PATH = "clinic.db"
REQUEST_TIMEOUT = 120  # seconds

ADMIN_CONTEXT: dict[str, Any] = {
    "cookies": {"vanna_email": "admin@example.com"},
    "headers": {},
    "url": f"{BASE_URL}/api/vanna/v2/chat_poll",
    "method": "POST",
    "query_params": {},
    "client_host": "127.0.0.1",
}

# ---------------------------------------------------------------------------
# Test definitions — deduplicated from the former two files
# ---------------------------------------------------------------------------

TESTS: list[dict[str, Any]] = [
    {
        "id": 1,
        "category": "Basic Counts",
        "question": "How many patients do we have?",
        "validation_sql": "SELECT COUNT(*) AS total FROM patients",
    },
    {
        "id": 2,
        "category": "Financial Analysis",
        "question": "What is the total revenue from paid invoices?",
        "validation_sql": "SELECT ROUND(SUM(total_amount), 2) AS total FROM invoices WHERE status = 'Paid'",
    },
    {
        "id": 3,
        "category": "Appointment Management",
        "question": "How many completed appointments do we have?",
        "validation_sql": "SELECT COUNT(*) AS total FROM appointments WHERE status = 'Completed'",
    },
    {
        "id": 4,
        "category": "Staff Management",
        "question": "How many doctors work in the Cardiology department?",
        "validation_sql": "SELECT COUNT(*) AS total FROM doctors WHERE specialization = 'Cardiology'",
    },
    {
        "id": 5,
        "category": "Revenue Analysis",
        "question": "What is the average invoice amount?",
        "validation_sql": "SELECT ROUND(AVG(total_amount), 2) AS avg_amount FROM invoices",
    },
    {
        "id": 6,
        "category": "Patient Metrics",
        "question": "How many patients have overdue invoices?",
        "validation_sql": "SELECT COUNT(DISTINCT patient_id) AS total FROM invoices WHERE status = 'Overdue'",
    },
    {
        "id": 7,
        "category": "Appointment Analytics",
        "question": "What is the average number of appointments per patient?",
        "validation_sql": (
            "SELECT ROUND(AVG(cnt), 2) AS avg_appts "
            "FROM (SELECT COUNT(*) AS cnt FROM appointments GROUP BY patient_id)"
        ),
    },
    {
        "id": 8,
        "category": "Data Retrieval",
        "question": "Show me all doctors",
        "validation_sql": "SELECT id, name, specialization FROM doctors ORDER BY id",
    },
    {
        "id": 9,
        "category": "Ranking",
        "question": "Which doctor has the most appointments?",
        "validation_sql": (
            "SELECT d.name, COUNT(a.id) AS total "
            "FROM doctors d JOIN appointments a ON d.id = a.doctor_id "
            "GROUP BY d.id ORDER BY total DESC LIMIT 1"
        ),
    },
    {
        "id": 10,
        "category": "Basic Counts",
        "question": "How many appointments are scheduled?",
        "validation_sql": "SELECT COUNT(*) AS total FROM appointments WHERE status = 'Scheduled'",
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def execute_sql(sql: str) -> dict[str, Any]:
    """Run SQL directly against the clinic database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
        conn.close()
        return {"success": True, "rows": rows, "count": len(rows)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def query_agent(question: str, test_id: int) -> dict[str, Any]:
    """Send a question to the Vanna chat_poll endpoint."""
    try:
        resp = requests.post(
            f"{BASE_URL}/api/vanna/v2/chat_poll",
            json={
                "message": question,
                "conversation_id": f"integration-{test_id}",
                "request_context": ADMIN_CONTEXT,
                "metadata": {},
            },
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return {"success": False, "error": f"HTTP {resp.status_code}"}

        data = resp.json()
        chunks = data.get("chunks", [])
        return {
            "success": True,
            "summary": _extract_text(chunks),
            "rows": _extract_dataframe_rows(chunks),
            "row_count": (_extract_dataframe(chunks) or {}).get("row_count", 0),
            "total_chunks": data.get("total_chunks", len(chunks)),
        }
    except requests.Timeout:
        return {"success": False, "error": f"Timeout ({REQUEST_TIMEOUT}s)"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _extract_text(chunks: list[dict]) -> str:
    """Pull human-readable text from agent response chunks."""
    parts: list[str] = []
    for chunk in chunks:
        simple = chunk.get("simple") or {}
        if simple.get("type") == "text" and simple.get("text"):
            parts.append(simple["text"])
            continue
        rich = chunk.get("rich") or {}
        if rich.get("type") == "text":
            content = (rich.get("data") or {}).get("content")
            if content:
                parts.append(content)
    return "\n".join(p.strip() for p in parts if p.strip())


def _extract_dataframe(chunks: list[dict]) -> dict | None:
    """Return the last dataframe chunk (if any)."""
    frame = None
    for chunk in chunks:
        rich = chunk.get("rich") or {}
        if rich.get("type") == "dataframe":
            frame = rich.get("data") or {}
    return frame


def _extract_dataframe_rows(chunks: list[dict]) -> list[dict]:
    """Return data rows from the last dataframe chunk."""
    frame = _extract_dataframe(chunks)
    return (frame or {}).get("data", [])


def compare_rows(
    agent_rows: list[dict], expected_rows: list[dict]
) -> bool:
    """Compare agent output rows against direct-SQL rows."""
    if len(agent_rows) != len(expected_rows):
        return False
    if not expected_rows:
        return True

    keys = list(expected_rows[0].keys())

    # Single-scalar comparison with tolerance
    if len(expected_rows) == 1 and len(keys) == 1 and len(agent_rows[0]) == 1:
        exp = next(iter(expected_rows[0].values()))
        got = next(iter(agent_rows[0].values()))
        if isinstance(exp, (int, float)) and isinstance(got, (int, float)):
            return math.isclose(float(got), float(exp), rel_tol=1e-9, abs_tol=1e-9)
        return got == exp

    for a_row, e_row in zip(agent_rows, expected_rows):
        if not all(k in a_row for k in keys):
            return False
        if {k: a_row[k] for k in keys} != e_row:
            return False
    return True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_tests(tests: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute all integration tests and print a verification report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_count": len(tests),
        "results": [],
    }

    print(f"\n{'=' * 80}")
    print("CLINIC NL2SQL — INTEGRATION TEST REPORT")
    print(f"{'=' * 80}")
    print(f"Timestamp : {report['timestamp']}")
    print(f"Database  : {DB_PATH}")
    print(f"API       : {BASE_URL}")
    print(f"Tests     : {len(tests)}")
    print(f"{'=' * 80}\n")

    passed = failed = 0

    for test in tests:
        tid = test["id"]
        print(f"{'─' * 80}")
        print(f"TEST #{tid}: [{test['category']}] {test['question']}")
        print(f"{'─' * 80}")

        # 1. Query agent
        start = time.time()
        agent = query_agent(test["question"], tid)
        elapsed = round(time.time() - start, 2)

        if not agent["success"]:
            print(f"  ❌ Agent error: {agent['error']}")
            failed += 1
            report["results"].append({
                "test_id": tid, "status": "FAILED", "error": agent["error"]
            })
            continue

        summary = (agent.get("summary") or "")[:200]
        print(f"  Agent response ({elapsed}s): {summary}")

        # 2. Direct SQL
        sql_result = execute_sql(test["validation_sql"])
        if not sql_result["success"]:
            print(f"  ❌ SQL error: {sql_result['error']}")
            failed += 1
            report["results"].append({
                "test_id": tid, "status": "FAILED", "error": sql_result["error"]
            })
            continue

        expected_rows = sql_result["rows"]
        expected_count = sql_result["count"]

        # 3. Compare
        rows_ok = compare_rows(agent.get("rows", []), expected_rows)
        count_ok = agent.get("row_count", 0) == expected_count

        if expected_count == 1 and len(expected_rows[0]) == 1:
            val = next(iter(expected_rows[0].values()))
            print(f"  Expected: {val}")
        else:
            print(f"  Expected: {expected_count} rows")

        if rows_ok and count_ok:
            print(f"  ✅ PASSED ({elapsed}s)")
            passed += 1
            report["results"].append({
                "test_id": tid, "status": "PASSED", "time": elapsed,
                "rows": expected_count,
            })
        else:
            print(f"  ❌ FAILED — rows_match={rows_ok}, count_match={count_ok}")
            failed += 1
            report["results"].append({
                "test_id": tid, "status": "FAILED",
                "rows_match": rows_ok, "count_match": count_ok,
            })

    # Summary
    total = len(tests)
    rate = (passed / total * 100) if total else 0
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"  ✅ Passed : {passed}/{total}")
    print(f"  ❌ Failed : {failed}/{total}")
    print(f"  Rate     : {rate:.0f}%")

    # Category breakdown
    cats: dict[str, dict[str, int]] = {}
    for r in report["results"]:
        tid = r["test_id"]
        cat = next(t["category"] for t in tests if t["id"] == tid)
        cats.setdefault(cat, {"passed": 0, "failed": 0})
        cats[cat]["passed" if r["status"] == "PASSED" else "failed"] += 1

    print("\n  By category:")
    for cat, s in cats.items():
        t = s["passed"] + s["failed"]
        icon = "✅" if s["failed"] == 0 else "⚠️"
        print(f"    {icon} {cat}: {s['passed']}/{t}")

    print(f"{'=' * 80}\n")
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and run the integration test suite."""
    parser = argparse.ArgumentParser(description="Clinic NL2SQL integration tests")
    parser.add_argument(
        "--quick", action="store_true", help="Run only the first 5 tests"
    )
    args = parser.parse_args()

    subset = TESTS[:5] if args.quick else TESTS
    report = run_tests(subset)

    passed = sum(1 for r in report["results"] if r["status"] == "PASSED")
    sys.exit(0 if passed == len(subset) else 1)


if __name__ == "__main__":
    main()
