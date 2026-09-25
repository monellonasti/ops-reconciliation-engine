"""Generate the synthetic demo datasets in ``data/``.

Everything here is invented: names are drawn from short lists, emails use the
reserved ``example.com`` domain and IBANs are random digits with no valid
checksum. Running the script twice produces identical files (fixed seed).

    python scripts/generate_demo_data.py
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED = 20240901
EMPLOYEE_COUNT = 200

COLUMNS = [
    "employee_id",
    "first_name",
    "last_name",
    "email",
    "iban",
    "contract_type",
    "department",
    "working_hours",
    "monthly_salary",
    "bonus",
    "overtime_hours",
    "start_date",
    "end_date",
]

FIRST_NAMES = [
    "Ada", "Bruno", "Carla", "Dario", "Elena", "Fabio", "Giulia", "Hamid", "Irene", "Jonas",
    "Katia", "Luca", "Marta", "Nadia", "Omar", "Paola", "Quirino", "Rosa", "Sergio", "Teresa",
    "Ugo", "Vera", "Walter", "Ximena", "Yara", "Zeno", "Alma", "Bekir", "Chiara", "Davide",
    "Emma", "Franco", "Greta", "Hugo", "Ilaria", "Jamal", "Klara", "Lorenzo", "Mira", "Nils",
]
LAST_NAMES = [
    "Rossi", "Bianchi", "Conti", "Esposito", "Ferrari", "Galli", "Greco", "Lombardi", "Marino",
    "Moretti", "Ricci", "Romano", "Russo", "Santoro", "Serra", "Vitale", "Weber", "Novak",
    "Kowalski", "Fischer", "Dubois", "Martin", "Silva", "Costa", "Haddad", "Okafor", "Yilmaz",
    "Petrov", "Nilsen", "Brandt", "Rinaldi", "Caruso", "Fontana", "Leone", "Longo", "Mancini",
    "Pellegrini", "Sartori", "Testa", "Villa",
]
DEPARTMENTS = {
    "Engineering": (2600, 4800),
    "Operations": (1900, 3200),
    "Finance": (2200, 4000),
    "Sales": (1900, 3600),
    "HR": (2000, 3400),
    "Customer Support": (1700, 2600),
    "Marketing": (2000, 3500),
}
CONTRACT_TYPES = ["full_time"] * 14 + ["part_time"] * 3 + ["fixed_term"] * 2 + ["apprenticeship"]

Record = dict[str, str]


def main() -> None:
    rng = random.Random(SEED)
    previous = [base_record(index, rng) for index in range(1, EMPLOYEE_COUNT + 1)]
    # EMP-00125 mirrors the example in the project brief (2,100 -> 3,000).
    by_id(previous, "EMP-00125")["monthly_salary"] = "2100"
    by_id(previous, "EMP-00150")["monthly_salary"] = "2800"

    current, changes = current_cycle(previous, rng)

    DATA_DIR.mkdir(exist_ok=True)
    write_csv(DATA_DIR / "demo_previous.csv", previous)
    write_csv(DATA_DIR / "demo_current.csv", current)
    with (DATA_DIR / "demo_current.csv").open("a", encoding="utf-8", newline="") as handle:
        # One structurally broken line (an extra field) to show how the loader reacts.
        handle.write("EMP-00206,Broken,Row,broken.row@example.com,IT00Q0000000000000000000206,"
                     "full_time,Operations,40,2400,0,2,2024-08-01,,UNEXPECTED\n")
    changes.append(("EMP-00206", "malformed row with an extra field (skipped by the loader)"))

    print(f"Wrote {len(previous)} previous and {len(current)} current records to {DATA_DIR}")
    print("Injected scenarios:")
    for employee_id, description in changes:
        print(f"  {employee_id}: {description}")


# --- base population ---------------------------------------------------------------


def base_record(index: int, rng: random.Random) -> Record:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    department = rng.choice(list(DEPARTMENTS))
    low, high = DEPARTMENTS[department]
    contract = rng.choice(CONTRACT_TYPES)
    hours = 40 if contract != "part_time" else rng.choice([20, 24, 30])
    salary = round(rng.randint(low, high) / 50) * 50
    if contract == "part_time":
        salary = round(salary * hours / 40 / 50) * 50
    if contract == "apprenticeship":
        salary = round(salary * 0.7 / 50) * 50
    bonus = 0 if rng.random() < 0.7 else round(salary * rng.uniform(0.02, 0.12) / 10) * 10
    start = f"{rng.randint(2012, 2024)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    return {
        "employee_id": f"EMP-{index:05d}",
        "first_name": first,
        "last_name": last,
        "email": f"{first}.{last}{index}@example.com".lower(),
        "iban": synthetic_iban(rng, index),
        "contract_type": contract,
        "department": department,
        "working_hours": str(hours),
        "monthly_salary": str(salary),
        "bonus": str(bonus),
        "overtime_hours": str(rng.choice([0, 0, 0, 2, 4, 6, 8, 10, 12, 16, 20])),
        "start_date": start,
        "end_date": "",
    }


def synthetic_iban(rng: random.Random, index: int) -> str:
    # Looks like an Italian IBAN (27 characters) but carries no valid check digits.
    digits = "".join(str(rng.randint(0, 9)) for _ in range(17))
    return f"IT{rng.randint(10, 99)}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{digits}{index:05d}"


# --- current cycle -----------------------------------------------------------------


def current_cycle(previous: list[Record], rng: random.Random) -> tuple[list[Record], list[tuple[str, str]]]:
    """Copy the previous cycle and inject a known set of changes and data problems."""
    current = [dict(record) for record in previous]
    changes: list[tuple[str, str]] = []

    def note(employee_id: str, description: str) -> None:
        changes.append((employee_id, description))

    # Removed employees.
    for employee_id in ("EMP-00017", "EMP-00088", "EMP-00143"):
        current.remove(by_id(current, employee_id))
        note(employee_id, "removed from the current cycle")

    # New employees.
    for index in (201, 202, 203, 204):
        record = base_record(index, rng)
        record["start_date"] = f"2024-09-{rng.randint(1, 15):02d}"
        current.append(record)
        note(record["employee_id"], "new record")
    by_id(current, "EMP-00203")["contract_type"] = ""
    note("EMP-00203", "new record with missing contract_type")

    # Salary changes at different magnitudes.
    for employee_id, factor, label in (
        ("EMP-00005", 1.03, "+3% (info)"),
        ("EMP-00042", 1.08, "+8% (info)"),
        ("EMP-00061", 1.12, "+12% (info)"),
        ("EMP-00077", 1.18, "+18% (warning)"),
        ("EMP-00099", 1.22, "+22% (warning)"),
        ("EMP-00112", 0.90, "-10% (info)"),
        ("EMP-00136", 0.65, "-35% (critical)"),
    ):
        record = by_id(current, employee_id)
        record["monthly_salary"] = str(round(float(record["monthly_salary"]) * factor))
        note(employee_id, f"salary {label}")
    by_id(current, "EMP-00125")["monthly_salary"] = "3000"
    note("EMP-00125", "salary 2,100 -> 3,000 (+42.86%, critical)")
    by_id(current, "EMP-00150")["monthly_salary"] = "28000"
    note("EMP-00150", "salary 2,800 -> 28,000 (+900%, looks like a typo)")

    # IBAN changes.
    for employee_id in ("EMP-00023", "EMP-00158"):
        by_id(current, employee_id)["iban"] = synthetic_iban(rng, 900 + int(employee_id[-3:]))
        note(employee_id, "IBAN changed")

    # Duplicate employee_id: the same person exported twice with different salaries.
    duplicate = dict(by_id(current, "EMP-00064"))
    duplicate["monthly_salary"] = str(int(duplicate["monthly_salary"]) + 250)
    current.insert(current.index(by_id(current, "EMP-00064")) + 1, duplicate)
    note("EMP-00064", "duplicated employee_id with two different salaries")

    # Missing required data.
    by_id(current, "EMP-00071")["last_name"] = ""
    note("EMP-00071", "missing last_name")
    by_id(current, "EMP-00093")["monthly_salary"] = ""
    note("EMP-00093", "missing monthly_salary")
    orphan = base_record(205, rng)
    orphan["employee_id"] = ""
    current.append(orphan)
    note("(row without ID)", "record with an empty employee_id")

    # Department, contract and working-hour changes.
    by_id(current, "EMP-00012")["department"] = "Marketing"
    note("EMP-00012", "department changed to Marketing")
    by_id(current, "EMP-00119")["department"] = "Customer Support"
    note("EMP-00119", "department changed to Customer Support")
    record = by_id(current, "EMP-00034")
    record.update(contract_type="full_time", working_hours="40")
    record["monthly_salary"] = str(round(float(record["monthly_salary"]) * 40 / float(by_id(previous, "EMP-00034")["working_hours"]) / 50) * 50)
    note("EMP-00034", "part_time -> full_time with working hours and salary adjusted")
    by_id(current, "EMP-00147")["contract_type"] = "fixed_term"
    note("EMP-00147", "contract_type changed to fixed_term")
    by_id(current, "EMP-00108")["working_hours"] = "32"
    note("EMP-00108", "working_hours 40 -> 32")

    # Overtime anomalies.
    for employee_id, hours in (("EMP-00050", "72"), ("EMP-00081", "110"), ("EMP-00164", "-5")):
        by_id(current, employee_id)["overtime_hours"] = hours
        note(employee_id, f"overtime_hours = {hours}")

    # Bonus anomalies.
    for employee_id, ratio in (("EMP-00029", 0.6), ("EMP-00176", 1.5)):
        record = by_id(current, employee_id)
        record["bonus"] = str(round(float(record["monthly_salary"]) * ratio))
        note(employee_id, f"bonus = {ratio:.0%} of monthly salary")

    # Invalid dates.
    by_id(current, "EMP-00131")["start_date"] = "2024-02-30"
    note("EMP-00131", "impossible start_date 2024-02-30")
    record = by_id(current, "EMP-00188")
    record["end_date"] = "2010-01-01"
    note("EMP-00188", "end_date earlier than start_date")

    # Leavers and a corrected start date.
    by_id(current, "EMP-00045")["end_date"] = "2024-09-30"
    by_id(current, "EMP-00172")["end_date"] = "2024-10-15"
    note("EMP-00045", "end_date added")
    note("EMP-00172", "end_date added")
    by_id(current, "EMP-00102")["start_date"] = "2019-03-01"
    note("EMP-00102", "start_date changed")

    # Email problems.
    by_id(current, "EMP-00056")["email"] = "name.surname-example.com"
    note("EMP-00056", "malformed email")
    by_id(current, "EMP-00183")["email"] = by_id(current, "EMP-00019")["email"]
    note("EMP-00183", "email duplicated from EMP-00019")

    return current, changes


# --- helpers ---------------------------------------------------------------------------


def by_id(records: list[Record], employee_id: str) -> Record:
    for record in records:
        if record["employee_id"] == employee_id:
            return record
    raise KeyError(employee_id)


def write_csv(path: Path, records: list[Record]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


if __name__ == "__main__":
    main()
