# modules/symptom_db.py
# PURPOSE: All database operations for Module 3 — Symptom Collection.
#
# ADDS two new tables to pvpro.db:
#   - "symptom_reports": stores each patient's symptom report
#     (raw text, MedDRA PT, severity, which drug triggered it)
#   - "adr_knowledge_base": reference table of known drug-ADR pairs
#     (used by Module 4 onwards for ADR matching and confidence scoring)
#
# This file is ADDED to your existing pvpro_final project.
# Your existing patient_db.py, bill_fetcher.py, bill_parser.py,
# reminder_system.py are all unchanged.

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")


def init_symptom_tables():
    """
    Creates the symptom_reports and adr_knowledge_base tables.
    Called at app startup alongside init_db() from patient_db.py.
    Safe to call multiple times — will not overwrite existing data.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # ── TABLE: symptom_reports ────────────────────────────────────────────
    # One row per symptom report submitted by a patient.
    # A patient can submit multiple reports (Day 3, Day 7, Day 14, Day 30).
    # Each report is linked to a specific drug (drug_id from purchase_drugs).
    c.execute("""
        CREATE TABLE IF NOT EXISTS symptom_reports (
            report_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id       INTEGER NOT NULL,
            drug_id          INTEGER NOT NULL,
            drug_name        TEXT,
            raw_symptom      TEXT,       -- Patient's own words, e.g. "my feet are swollen"
            meddra_pt        TEXT,       -- Standardized MedDRA term (filled by NLP in Module 4)
            meddra_soc       TEXT,       -- System Organ Class (filled by MedDRA mapper)
            severity         TEXT,       -- Mild / Moderate / Severe
            timing_ok        INTEGER,    -- 1 if symptom appeared after starting drug, else 0
            drug_stopped     INTEGER,    -- 1 if patient stopped the drug
            symptom_improved INTEGER,    -- 1 if symptom improved after stopping
            report_date      TEXT,
            FOREIGN KEY (patient_id) REFERENCES patient_profile(patient_id),
            FOREIGN KEY (drug_id)    REFERENCES purchase_drugs(drug_id)
        )
    """)

    # ── TABLE: adr_knowledge_base ─────────────────────────────────────────
    # Reference table: known drug → ADR pairs.
    # Used in Module 4 (ADR Matcher) and Module 5 (Confidence Scorer).
    # Pre-seeded with common Indian pharmacy drugs.
    c.execute("""
        CREATE TABLE IF NOT EXISTS adr_knowledge_base (
            kb_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name  TEXT,
            meddra_pt  TEXT,
            meddra_soc TEXT,
            frequency  TEXT,    -- Common / Uncommon / Rare
            severity   TEXT     -- Mild / Moderate / Severe
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Symptom tables ready.")


def seed_adr_knowledge_base():
    """
    Seeds the adr_knowledge_base table with common drug-ADR pairs for
    Indian pharmacy drugs. Only inserts if the table is empty — safe to
    call on every app startup.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("SELECT COUNT(*) FROM adr_knowledge_base")
    if c.fetchone()[0] > 0:
        conn.close()
        print("[DB] ADR knowledge base already seeded.")
        return

    ADR_DATA = [
        # (drug_name, meddra_pt, meddra_soc, frequency, severity)
        ("Amlodipine",   "Peripheral oedema",  "Cardiac disorders",                 "Common",   "Mild"),
        ("Amlodipine",   "Headache",            "Nervous system disorders",          "Common",   "Mild"),
        ("Amlodipine",   "Dizziness",           "Nervous system disorders",          "Common",   "Mild"),
        ("Amlodipine",   "Palpitations",        "Cardiac disorders",                 "Uncommon", "Mild"),
        ("Metformin",    "Diarrhoea",           "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Metformin",    "Nausea",              "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Metformin",    "Abdominal pain",      "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Atorvastatin", "Myalgia",             "Musculoskeletal disorders",         "Common",   "Moderate"),
        ("Atorvastatin", "Headache",            "Nervous system disorders",          "Common",   "Mild"),
        ("Amoxicillin",  "Rash",                "Skin disorders",                    "Common",   "Mild"),
        ("Amoxicillin",  "Diarrhoea",           "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Amoxicillin",  "Nausea",              "Gastrointestinal disorders",        "Uncommon", "Mild"),
        ("Azithromycin", "Nausea",              "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Azithromycin", "Diarrhoea",           "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Omeprazole",   "Headache",            "Nervous system disorders",          "Common",   "Mild"),
        ("Omeprazole",   "Diarrhoea",           "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Losartan",     "Dizziness",           "Nervous system disorders",          "Common",   "Mild"),
        ("Cetirizine",   "Somnolence",          "Nervous system disorders",          "Common",   "Mild"),
        ("Cetirizine",   "Dry mouth",           "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Cetirizine",   "Fatigue",             "General disorders",                 "Common",   "Mild"),
        ("Paracetamol",  "Rash",                "Skin disorders",                    "Rare",     "Mild"),
        ("Pantoprazole", "Headache",            "Nervous system disorders",          "Common",   "Mild"),
        ("LIMCEE",       "Diarrhoea",           "Gastrointestinal disorders",        "Rare",     "Mild"),
        ("LIMCEE",       "Abdominal pain",      "Gastrointestinal disorders",        "Rare",     "Mild"),
        ("Vitamin C",    "Diarrhoea",           "Gastrointestinal disorders",        "Rare",     "Mild"),
        ("Ibuprofen",    "Nausea",              "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Ibuprofen",    "Abdominal pain",      "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Aspirin",      "Nausea",              "Gastrointestinal disorders",        "Common",   "Mild"),
        ("Aspirin",      "Abdominal pain",      "Gastrointestinal disorders",        "Common",   "Mild"),
    ]

    c.executemany("""
        INSERT INTO adr_knowledge_base (drug_name, meddra_pt, meddra_soc, frequency, severity)
        VALUES (?, ?, ?, ?, ?)
    """, ADR_DATA)

    conn.commit()
    conn.close()
    print(f"[DB] ADR knowledge base seeded with {len(ADR_DATA)} entries.")


def save_symptom_report(patient_id: int, drug_id: int, drug_name: str,
                        raw_symptom: str, severity: str,
                        timing_ok: bool, drug_stopped: bool,
                        symptom_improved: bool) -> int:
    """
    Saves a patient's symptom report to the database.

    Args:
        patient_id:       patient's permanent profile ID
        drug_id:          which drug triggered this report
        drug_name:        drug name (stored for quick reference)
        raw_symptom:      patient's own words, e.g. "my feet became swollen"
        severity:         "Mild" / "Moderate" / "Severe"
        timing_ok:        True if symptom appeared after starting the drug
        drug_stopped:     True if patient stopped taking the drug
        symptom_improved: True if symptom improved after stopping

    Returns:
        report_id (int)
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("""
        INSERT INTO symptom_reports
        (patient_id, drug_id, drug_name, raw_symptom, severity,
         timing_ok, drug_stopped, symptom_improved, report_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        patient_id,
        drug_id,
        drug_name,
        raw_symptom,
        severity,
        1 if timing_ok        else 0,
        1 if drug_stopped     else 0,
        1 if symptom_improved else 0,
        str(datetime.now())
    ))

    report_id = c.lastrowid
    conn.commit()
    conn.close()

    print(f"[DB] Symptom report saved: report_id={report_id}, "
          f"patient_id={patient_id}, drug={drug_name}, severity={severity}")

    return report_id


def save_no_symptom_report(patient_id: int, drug_id: int, drug_name: str) -> int:
    """
    Saves a 'No symptoms' response — patient explicitly said they feel fine.
    Stored with raw_symptom='No symptoms' and severity='None'.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("""
        INSERT INTO symptom_reports
        (patient_id, drug_id, drug_name, raw_symptom, severity,
         timing_ok, drug_stopped, symptom_improved, report_date)
        VALUES (?, ?, ?, 'No symptoms', 'None', 0, 0, 0, ?)
    """, (patient_id, drug_id, drug_name, str(datetime.now())))

    report_id = c.lastrowid
    conn.commit()
    conn.close()

    print(f"[DB] No-symptom report saved: report_id={report_id}, drug={drug_name}")
    return report_id


def get_symptom_reports_for_patient(patient_id: int) -> list:
    """Returns all symptom reports for a given patient, newest first."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("""
        SELECT report_id, drug_name, raw_symptom, meddra_pt,
               severity, timing_ok, report_date
        FROM symptom_reports
        WHERE patient_id = ?
        ORDER BY report_date DESC
    """, (patient_id,))

    rows = c.fetchall()
    conn.close()

    return [
        {
            "report_id":  r[0],
            "drug_name":  r[1],
            "raw_symptom": r[2],
            "meddra_pt":  r[3],
            "severity":   r[4],
            "timing_ok":  r[5],
            "report_date": r[6]
        }
        for r in rows
    ]


def get_unprocessed_reports() -> list:
    """
    Returns symptom reports that have NOT yet been processed by the NLP engine
    (meddra_pt is NULL or empty). Used by Module 4 (NLP Engine).
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute("""
        SELECT report_id, drug_name, raw_symptom, severity, patient_id, drug_id
        FROM symptom_reports
        WHERE (meddra_pt IS NULL OR meddra_pt = '')
          AND raw_symptom != 'No symptoms'
        ORDER BY report_date ASC
    """)

    rows = c.fetchall()
    conn.close()

    return [
        {
            "report_id":   r[0],
            "drug_name":   r[1],
            "raw_symptom": r[2],
            "severity":    r[3],
            "patient_id":  r[4],
            "drug_id":     r[5]
        }
        for r in rows
    ]


def update_meddra_term(report_id: int, meddra_pt: str, meddra_soc: str):
    """
    Updates a symptom report with the standardized MedDRA term.
    Called by Module 4 (NLP Engine) after processing raw symptom text.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        UPDATE symptom_reports
        SET meddra_pt = ?, meddra_soc = ?
        WHERE report_id = ?
    """, (meddra_pt, meddra_soc, report_id))
    conn.commit()
    conn.close()
