"""
Seed Vanna agent memory with curated NL→SQL examples.
Run: python scripts/seed_memory.py
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# Ensure the project root is on sys.path so backend.* imports resolve.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.agent_factory import agent  # noqa: E402

MEMORY_DIR = Path("vanna_memory")


@dataclass(frozen=True, slots=True)
class SeedExample:
    question: str
    sql: str


SEED_EXAMPLES: tuple[SeedExample, ...] = (
    SeedExample("How many patients do we have?", "SELECT COUNT(*) FROM patients;"),
    SeedExample("List all doctors and their specializations", "SELECT name, specialization FROM doctors;"),
    SeedExample("Show me appointments for last month", "SELECT * FROM appointments WHERE appointment_date >= DATE('now','-1 month');"),
    SeedExample("Which doctor has the most appointments?", "SELECT d.name, COUNT(a.id) AS total FROM doctors d LEFT JOIN appointments a ON d.id = a.doctor_id GROUP BY d.id, d.name ORDER BY total DESC LIMIT 1;"),
    SeedExample("What is the total revenue?", "SELECT SUM(total_amount) FROM invoices;"),
    SeedExample("Show revenue by doctor", "SELECT d.name, SUM(i.total_amount) AS revenue FROM doctors d JOIN appointments a ON d.id = a.doctor_id JOIN invoices i ON a.id = i.appointment_id GROUP BY d.id, d.name;"),
    SeedExample("How many cancelled appointments last quarter?", "SELECT COUNT(*) FROM appointments WHERE status='Cancelled' AND appointment_date >= DATE('now','-3 months');"),
    SeedExample("Top 5 patients by spending", "SELECT p.first_name || ' ' || p.last_name AS patient_name, SUM(i.total_amount) AS total FROM patients p JOIN invoices i ON p.id = i.patient_id GROUP BY p.id, patient_name ORDER BY total DESC LIMIT 5;"),
    SeedExample("Average treatment cost by specialization", "SELECT d.specialization, AVG(t.cost) FROM treatments t JOIN appointments a ON t.appointment_id = a.id JOIN doctors d ON a.doctor_id = d.id GROUP BY d.specialization;"),
    SeedExample("Show monthly appointment count for the past 6 months", "SELECT strftime('%Y-%m', appointment_date) AS month, COUNT(*) AS total FROM appointments WHERE appointment_date >= DATE('now','-6 months') GROUP BY month;"),
    SeedExample("Which city has the most patients?", "SELECT city, COUNT(*) AS total FROM patients GROUP BY city ORDER BY total DESC LIMIT 1;"),
    SeedExample("List patients who visited more than 3 times", "SELECT p.first_name, p.last_name, COUNT(a.id) AS visits FROM patients p JOIN appointments a ON p.id = a.patient_id GROUP BY p.id, p.first_name, p.last_name HAVING COUNT(a.id) > 3;"),
    SeedExample("Show unpaid invoices", "SELECT * FROM invoices WHERE status != 'Paid';"),
    SeedExample("What percentage of appointments are no-shows?", "SELECT (SUM(CASE WHEN status='No-Show' THEN 1 ELSE 0 END)*100.0)/COUNT(*) FROM appointments;"),
    SeedExample("Show the busiest day of the week for appointments", "SELECT strftime('%w', appointment_date) AS day, COUNT(*) AS total FROM appointments GROUP BY day ORDER BY total DESC LIMIT 1;"),
    SeedExample("Revenue trend by month", "SELECT strftime('%Y-%m', invoice_date) AS month, SUM(total_amount) FROM invoices GROUP BY month;"),
    SeedExample("Average appointment duration by doctor", "SELECT d.name, AVG(t.duration_minutes) FROM doctors d JOIN appointments a ON d.id = a.doctor_id JOIN treatments t ON a.id = t.appointment_id GROUP BY d.id, d.name;"),
    SeedExample("List patients with overdue invoices", "SELECT DISTINCT p.* FROM patients p JOIN invoices i ON p.id = i.patient_id WHERE i.status='Overdue';"),
    SeedExample("Compare revenue between departments", "SELECT d.department, SUM(i.total_amount) FROM doctors d JOIN appointments a ON d.id = a.doctor_id JOIN invoices i ON a.id = i.appointment_id GROUP BY d.department;"),
    SeedExample("Show patient registration trend by month", "SELECT strftime('%Y-%m', registered_date) AS month, COUNT(*) FROM patients GROUP BY month;"),
    SeedExample("Doctors with no appointments", "SELECT d.name FROM doctors d LEFT JOIN appointments a ON d.id = a.doctor_id WHERE a.id IS NULL;"),
    SeedExample("Patients without any appointment", "SELECT * FROM patients p WHERE NOT EXISTS (SELECT 1 FROM appointments a WHERE a.patient_id = p.id);"),
    SeedExample("Appointments even if doctor missing (left join)", "SELECT a.*, d.name FROM appointments a LEFT JOIN doctors d ON a.doctor_id = d.id;"),
    SeedExample("Patients without email", "SELECT * FROM patients WHERE email IS NULL;"),
    SeedExample("Unique cities", "SELECT DISTINCT city FROM patients;"),
    SeedExample("Patients who had treatments", "SELECT DISTINCT p.* FROM patients p JOIN appointments a ON p.id = a.patient_id JOIN treatments t ON a.id = t.appointment_id;"),
    SeedExample("Top patient per city by spending", "SELECT * FROM (SELECT p.city, p.first_name, p.last_name, SUM(i.total_amount) AS total, RANK() OVER (PARTITION BY p.city ORDER BY SUM(i.total_amount) DESC) rnk FROM invoices i JOIN patients p ON p.id = i.patient_id GROUP BY p.city, p.id) WHERE rnk = 1;"),
    SeedExample("Revenue change month over month", "SELECT month, total, total - LAG(total) OVER (ORDER BY month) AS change FROM (SELECT strftime('%Y-%m', invoice_date) AS month, SUM(total_amount) AS total FROM invoices GROUP BY month);"),
    SeedExample("Classify invoices by payment status", "SELECT CASE WHEN paid_amount >= total_amount THEN 'Fully Paid' WHEN paid_amount = 0 THEN 'Unpaid' ELSE 'Partial' END AS payment_status, COUNT(*) FROM invoices GROUP BY payment_status;"),
    SeedExample("Show the cumulative running total of revenue by month", "WITH MonthlyRev AS (SELECT strftime('%Y-%m', invoice_date) AS month, SUM(total_amount) AS revenue FROM invoices GROUP BY month) SELECT month, revenue, SUM(revenue) OVER (ORDER BY month) AS running_total FROM MonthlyRev;"),
    SeedExample("Show a 7-day moving average of daily revenue", "WITH DailyRev AS (SELECT invoice_date AS day, SUM(total_amount) AS daily_revenue FROM invoices GROUP BY invoice_date) SELECT day, daily_revenue, AVG(daily_revenue) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS moving_avg FROM DailyRev;"),
    SeedExample("Group our patients into 4 quartiles based on their total spending", "WITH PatientSpending AS (SELECT patient_id, SUM(total_amount) AS total_spent FROM invoices GROUP BY patient_id) SELECT patient_id, total_spent, NTILE(4) OVER (ORDER BY total_spent DESC) AS spending_quartile FROM PatientSpending;"),
    SeedExample("What is the average number of days between a patient's first and last appointment?", "WITH PatientLifespan AS (SELECT patient_id, MIN(appointment_date) AS first_visit, MAX(appointment_date) AS latest_visit, CAST(julianday(MAX(appointment_date)) - julianday(MIN(appointment_date)) AS INTEGER) AS days_between FROM appointments GROUP BY patient_id HAVING COUNT(*) > 1) SELECT AVG(days_between) AS avg_days_retained FROM PatientLifespan;"),
    SeedExample("List each department and its unique doctor specializations", "SELECT department, GROUP_CONCAT(DISTINCT specialization) AS specializations FROM doctors GROUP BY department;"),
    SeedExample("How many patients who visited one month also returned the very next month?", "WITH MonthlyVisits AS (SELECT DISTINCT patient_id, strftime('%Y-%m', appointment_date) AS visit_month FROM appointments) SELECT m1.visit_month, COUNT(DISTINCT m1.patient_id) AS retained_patients FROM MonthlyVisits m1 JOIN MonthlyVisits m2 ON m1.patient_id = m2.patient_id AND date(m1.visit_month || '-01', '+1 month') = date(m2.visit_month || '-01') GROUP BY m1.visit_month;"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Vanna agent memory with curated NL2SQL examples.")
    parser.add_argument("--no-reset", action="store_true", help="Keep existing vanna_memory instead of recreating it.")
    return parser.parse_args()


def maybe_reset_memory(reset_memory: bool) -> None:
    if reset_memory and MEMORY_DIR.exists():
        print("Wiping existing Vanna memory...")
        shutil.rmtree(MEMORY_DIR)


def unique_examples(examples: tuple[SeedExample, ...]) -> tuple[SeedExample, ...]:
    seen: set[tuple[str, str]] = set()
    deduped: list[SeedExample] = []
    for example in examples:
        identity = (example.question, example.sql)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(example)
    return tuple(deduped)


async def save_example(save_tool_usage, example: SeedExample) -> None:
    result = save_tool_usage(
        question=example.question,
        tool_name="run_sql",
        args={"sql": example.sql},
        context=None,
    )
    if inspect.isawaitable(result):
        await result


async def run_seeding(reset_memory: bool = True) -> int:
    if not hasattr(agent, "agent_memory"):
        raise RuntimeError("Configured Vanna agent does not expose agent_memory; cannot seed examples.")

    maybe_reset_memory(reset_memory)
    print("Seeding Persistent ChromaDB Memory with curated NL2SQL examples...")

    examples = unique_examples(SEED_EXAMPLES)
    save_tool_usage = agent.agent_memory.save_tool_usage
    total_examples = len(examples)

    for index, example in enumerate(examples, start=1):
        try:
            await save_example(save_tool_usage, example)
            print(f"[{index}/{total_examples}] Saved: {example.question}")
        except Exception as exc:
            raise RuntimeError(f"Failed to save seed example '{example.question}': {exc}") from exc

    print(f"\nSuccessfully seeded {total_examples} Q&A pairs into ChromaDB.")
    return total_examples


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(run_seeding(reset_memory=not arguments.no_reset))
