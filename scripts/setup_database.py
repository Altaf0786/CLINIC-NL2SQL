"""
Database schema creation and Faker test data generation.
Run: python scripts/setup_database.py
"""

import random
import sqlite3

from faker import Faker


class DatabaseManager:
    def __init__(self, db_path: str = "clinic.db", seed: int = 42):
        self.db_path = db_path
        self.fake = Faker()
        random.seed(seed)
        Faker.seed(seed)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def reset_database(self, cursor):
        cursor.execute("PRAGMA foreign_keys = OFF;")
        for table in ["treatments", "appointments", "invoices", "patients", "doctors"]:
            cursor.execute(f"DROP TABLE IF EXISTS {table};")
        cursor.execute("PRAGMA foreign_keys = ON;")

    def create_schema(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            self.reset_database(cursor)

            cursor.execute("""
                CREATE TABLE patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    date_of_birth DATE,
                    gender TEXT CHECK(gender IN ('M','F')),
                    city TEXT,
                    registered_date DATE
                );
            """)
            cursor.execute("""
                CREATE TABLE doctors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    specialization TEXT,
                    department TEXT,
                    phone TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    doctor_id INTEGER NOT NULL,
                    appointment_date DATETIME,
                    status TEXT CHECK(status IN ('Scheduled','Completed','Cancelled','No-Show')),
                    notes TEXT,
                    FOREIGN KEY(patient_id) REFERENCES patients(id),
                    FOREIGN KEY(doctor_id) REFERENCES doctors(id)
                );
            """)
            cursor.execute("""
                CREATE TABLE treatments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_id INTEGER NOT NULL,
                    treatment_name TEXT,
                    cost REAL CHECK(cost >= 0),
                    duration_minutes INTEGER,
                    FOREIGN KEY(appointment_id) REFERENCES appointments(id)
                );
            """)
            cursor.execute("""
                CREATE TABLE invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    appointment_id INTEGER,
                    invoice_date DATE,
                    total_amount REAL,
                    paid_amount REAL,
                    status TEXT CHECK(status IN ('Paid','Pending','Overdue')),
                    FOREIGN KEY(patient_id) REFERENCES patients(id),
                    FOREIGN KEY(appointment_id) REFERENCES appointments(id)
                );
            """)

            cursor.execute("CREATE INDEX idx_appt_patient ON appointments(patient_id);")
            cursor.execute("CREATE INDEX idx_appt_doctor ON appointments(doctor_id);")
            cursor.execute("CREATE INDEX idx_appt_date ON appointments(appointment_date);")
            cursor.execute("CREATE INDEX idx_invoice_patient ON invoices(patient_id);")
            cursor.execute("CREATE INDEX idx_invoice_date ON invoices(invoice_date);")
            conn.commit()

    def generate_dummy_data(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            try:
                conn.execute("BEGIN")

                specs = ["Dermatology", "Cardiology", "Orthopedics", "General", "Pediatrics"]
                for _ in range(15):
                    spec = random.choice(specs)
                    cursor.execute(
                        "INSERT INTO doctors (name, specialization, department, phone) VALUES (?, ?, ?, ?)",
                        (f"Dr. {self.fake.name()}", spec, f"{spec} Dept", self.fake.phone_number()),
                    )
                cursor.execute("SELECT id FROM doctors")
                doctor_ids = [r[0] for r in cursor.fetchall()]

                cities = list(set(self.fake.city() for _ in range(10)))
                for _ in range(200):
                    cursor.execute(
                        "INSERT INTO patients (first_name, last_name, email, phone, date_of_birth, gender, city, registered_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            self.fake.first_name(),
                            self.fake.last_name(),
                            self.fake.email() if random.random() > 0.15 else None,
                            self.fake.phone_number() if random.random() > 0.1 else None,
                            self.fake.date_of_birth(minimum_age=1, maximum_age=90),
                            random.choice(["M", "F"]),
                            random.choice(cities),
                            self.fake.date_between(start_date="-1y", end_date="today"),
                        ),
                    )
                cursor.execute("SELECT id FROM patients")
                patient_ids = [r[0] for r in cursor.fetchall()]

                statuses = ["Scheduled", "Completed", "Cancelled", "No-Show"]
                for _ in range(500):
                    p_id = random.choices(patient_ids, weights=[1 / (i + 1) for i in range(len(patient_ids))], k=1)[0]
                    d_id = random.choices(doctor_ids, weights=[10 if i < 5 else 1 for i in range(len(doctor_ids))], k=1)[0]
                    cursor.execute(
                        "INSERT INTO appointments (patient_id, doctor_id, appointment_date, status, notes) VALUES (?, ?, ?, ?, ?)",
                        (
                            p_id,
                            d_id,
                            self.fake.date_time_between(start_date="-12M", end_date="now"),
                            random.choice(statuses),
                            self.fake.sentence() if random.random() > 0.5 else None,
                        ),
                    )

                cursor.execute("SELECT id FROM appointments WHERE status='Completed'")
                completed = [r[0] for r in cursor.fetchall()]
                treatment_cost_map = {}
                for _ in range(350):
                    if not completed:
                        break
                    appt_id = random.choice(completed)
                    cost = round(random.uniform(50, 5000), 2)
                    cursor.execute(
                        "INSERT INTO treatments (appointment_id, treatment_name, cost, duration_minutes) VALUES (?, ?, ?, ?)",
                        (appt_id, f"{self.fake.word().capitalize()} Treatment", cost, random.randint(15, 120)),
                    )
                    treatment_cost_map[appt_id] = treatment_cost_map.get(appt_id, 0) + cost

                for appt_id, total in treatment_cost_map.items():
                    cursor.execute("SELECT patient_id FROM appointments WHERE id=?", (appt_id,))
                    p_id = cursor.fetchone()[0]
                    status = random.choice(["Paid", "Pending", "Overdue"])
                    paid = total if status == "Paid" else round(random.uniform(0, total), 2)
                    cursor.execute(
                        "INSERT INTO invoices (patient_id, appointment_id, invoice_date, total_amount, paid_amount, status) VALUES (?, ?, ?, ?, ?, ?)",
                        (p_id, appt_id, self.fake.date_between(start_date="-12M", end_date="today"), total, paid, status),
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e


if __name__ == "__main__":
    db = DatabaseManager()
    print("Rebuilding database...")
    db.create_schema()
    print("Generating realistic data...")
    db.generate_dummy_data()
    print("Database setup complete ✅")
