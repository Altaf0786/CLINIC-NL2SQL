#!/usr/bin/env python3
"""SQL validation tests for the secure Vanna runner."""

from __future__ import annotations

import pytest

from backend.services.sql_runner import SecureSqliteRunner


def test_runner_rejects_non_select_sql():
    runner = SecureSqliteRunner(database_path="clinic.db")

    with pytest.raises(ValueError, match="Only SELECT queries are allowed"):
        runner.validate_sql("DELETE FROM patients")


def test_runner_rejects_dangerous_keywords():
    runner = SecureSqliteRunner(database_path="clinic.db")

    with pytest.raises(ValueError, match="Forbidden keyword detected"):
        runner.validate_sql("SELECT * FROM patients; GRANT ALL")


def test_runner_rejects_system_tables():
    runner = SecureSqliteRunner(database_path="clinic.db")

    with pytest.raises(ValueError, match="system tables"):
        runner.validate_sql("SELECT name FROM sqlite_master")


def test_runner_allows_safe_select():
    runner = SecureSqliteRunner(database_path="clinic.db")

    validated = runner.validate_sql("SELECT COUNT(*) AS total_patients FROM patients")

    assert validated == "SELECT COUNT(*) AS total_patients FROM patients"