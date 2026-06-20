# modules/patient_db.py
import sqlite3
from datetime import datetime, timedelta
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS patient_profile (
        patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL, age INTEGER, gender TEXT,
        phone TEXT UNIQUE NOT NULL, created_at TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS purchases (
        purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, bill_name TEXT, bill_date TEXT,
        invoice_no TEXT, source TEXT, captured_at TEXT,
        FOREIGN KEY (patient_id) REFERENCES patient_profile(patient_id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS purchase_drugs (
        drug_id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_id INTEGER, patient_id INTEGER,
        drug_name TEXT, quantity TEXT, mrp TEXT,
        reminder_date TEXT, reminder_sent INTEGER DEFAULT 0,
        FOREIGN KEY (purchase_id) REFERENCES purchases(purchase_id),
        FOREIGN KEY (patient_id) REFERENCES patient_profile(patient_id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS symptom_reports (
        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, drug_id INTEGER, drug_name TEXT,
        raw_symptom TEXT, meddra_pt TEXT, meddra_soc TEXT,
        severity TEXT, timing_ok INTEGER, drug_stopped INTEGER,
        symptom_improved INTEGER, report_date TEXT,
        FOREIGN KEY (patient_id) REFERENCES patient_profile(patient_id),
        FOREIGN KEY (drug_id) REFERENCES purchase_drugs(drug_id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS adr_knowledge_base (
        kb_id INTEGER PRIMARY KEY AUTOINCREMENT,
        drug_name TEXT, meddra_pt TEXT, meddra_soc TEXT,
        frequency TEXT, severity TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS adr_assessments (
        assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, drug_name TEXT, meddra_pt TEXT,
        confidence_score INTEGER, naranjo_score INTEGER,
        naranjo_category TEXT,
        pharmacist_status TEXT DEFAULT 'Pending',
        review_date TEXT,
        FOREIGN KEY (patient_id) REFERENCES patient_profile(patient_id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS signal_log (
        signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        drug_name TEXT, meddra_pt TEXT, month_year TEXT,
        report_count INTEGER, prr_value REAL, signal_flag TEXT)""")

    conn.commit()
    conn.close()
    _seed_adr_kb()
    print(f"[DB] Database ready at: {DB_PATH}")


def _seed_adr_kb():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM adr_knowledge_base")
    if c.fetchone()[0] > 0:
        conn.close()
        return
    data = [
        ("Amlodipine","Peripheral oedema","Cardiac disorders","Common","Mild"),
        ("Amlodipine","Headache","Nervous system disorders","Common","Mild"),
        ("Amlodipine","Dizziness","Nervous system disorders","Common","Mild"),
        ("Amlodipine","Palpitations","Cardiac disorders","Uncommon","Mild"),
        ("Metformin","Diarrhoea","Gastrointestinal disorders","Common","Mild"),
        ("Metformin","Nausea","Gastrointestinal disorders","Common","Mild"),
        ("Metformin","Abdominal pain","Gastrointestinal disorders","Common","Mild"),
        ("Atorvastatin","Myalgia","Musculoskeletal disorders","Common","Moderate"),
        ("Atorvastatin","Headache","Nervous system disorders","Common","Mild"),
        ("Amoxicillin","Rash","Skin disorders","Common","Mild"),
        ("Amoxicillin","Diarrhoea","Gastrointestinal disorders","Common","Mild"),
        ("Azithromycin","Nausea","Gastrointestinal disorders","Common","Mild"),
        ("Azithromycin","Diarrhoea","Gastrointestinal disorders","Common","Mild"),
        ("Omeprazole","Headache","Nervous system disorders","Common","Mild"),
        ("Omeprazole","Diarrhoea","Gastrointestinal disorders","Common","Mild"),
        ("Losartan","Dizziness","Nervous system disorders","Common","Mild"),
        ("Cetirizine","Somnolence","Nervous system disorders","Common","Mild"),
        ("Cetirizine","Dry mouth","Gastrointestinal disorders","Common","Mild"),
        ("Cetirizine","Fatigue","General disorders","Common","Mild"),
        ("Paracetamol","Rash","Skin disorders","Rare","Mild"),
        ("Pantoprazole","Headache","Nervous system disorders","Common","Mild"),
        ("LIMCEE","Diarrhoea","Gastrointestinal disorders","Rare","Mild"),
        ("LIMCEE","Abdominal pain","Gastrointestinal disorders","Rare","Mild"),
        ("Ibuprofen","Nausea","Gastrointestinal disorders","Common","Mild"),
        ("Aspirin","Nausea","Gastrointestinal disorders","Common","Mild"),
        ("Aspirin","Abdominal pain","Gastrointestinal disorders","Common","Mild"),
    ]
    c.executemany("""INSERT INTO adr_knowledge_base
                     (drug_name,meddra_pt,meddra_soc,frequency,severity)
                     VALUES (?,?,?,?,?)""", data)
    conn.commit()
    conn.close()
    print(f"[DB] ADR knowledge base seeded: {len(data)} entries")


# ── PROFILE FUNCTIONS ─────────────────────────────────────────────────────────

def create_or_get_profile(full_name, age, gender, phone):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT patient_id FROM patient_profile WHERE phone=?", (phone,))
    row = c.fetchone()
    if row:
        pid = row[0]
    else:
        c.execute("""INSERT INTO patient_profile
                     (full_name,age,gender,phone,created_at)
                     VALUES (?,?,?,?,?)""",
                  (full_name, age, gender, phone, str(datetime.now())))
        pid = c.lastrowid
    conn.commit()
    conn.close()
    return pid


def get_profile_by_id(patient_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM patient_profile WHERE patient_id=?", (patient_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {}
    return {"patient_id": row[0], "full_name": row[1], "age": row[2],
            "gender": row[3], "phone": row[4], "created_at": row[5]}


# ── PURCHASE FUNCTIONS ────────────────────────────────────────────────────────

def save_purchase(patient_id, extracted_data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO purchases
                 (patient_id,bill_name,bill_date,invoice_no,source,captured_at)
                 VALUES (?,?,?,?,?,?)""",
              (patient_id,
               extracted_data.get("patient_name", "N/A"),
               extracted_data.get("bill_date", str(datetime.today().date())),
               extracted_data.get("invoice_no", "N/A"),
               extracted_data.get("source", "Unknown"),
               str(datetime.now())))
    purchase_id = c.lastrowid

    bill_date_str = extracted_data.get("bill_date", "")
    bill_date = None
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            bill_date = datetime.strptime(bill_date_str, fmt)
            break
        except:
            continue
    if not bill_date:
        bill_date = datetime.today()
    reminder_date = bill_date + timedelta(days=3)

    drugs = extracted_data.get("drugs", []) or \
            [{"drug_name": "Unknown", "quantity": "N/A", "price": "N/A"}]
    for drug in drugs:
        c.execute("""INSERT INTO purchase_drugs
                     (purchase_id,patient_id,drug_name,quantity,mrp,reminder_date)
                     VALUES (?,?,?,?,?,?)""",
                  (purchase_id, patient_id,
                   drug.get("drug_name", "Unknown"),
                   drug.get("quantity", "N/A"),
                   drug.get("price", drug.get("mrp", "N/A")),
                   str(reminder_date.date())))
    conn.commit()
    conn.close()
    return purchase_id


def get_purchase_history(patient_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT p.purchase_id,p.bill_date,p.invoice_no,p.source,
                        pd.drug_name,pd.quantity,pd.mrp,pd.drug_id,
                        pd.reminder_date,pd.reminder_sent
                 FROM purchases p
                 JOIN purchase_drugs pd ON p.purchase_id=pd.purchase_id
                 WHERE p.patient_id=?
                 ORDER BY p.purchase_id DESC""", (patient_id,))
    rows = c.fetchall()
    conn.close()
    return [{"purchase_id": r[0], "bill_date": r[1], "invoice_no": r[2],
             "source": r[3], "drug_name": r[4], "quantity": r[5],
             "mrp": r[6], "drug_id": r[7], "reminder_date": r[8],
             "reminder_sent": r[9]} for r in rows]


# ── REMINDER FUNCTIONS ────────────────────────────────────────────────────────

def get_all_reminders_for_patient(patient_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT drug_id,drug_name,reminder_date,reminder_sent
                 FROM purchase_drugs WHERE patient_id=?
                 ORDER BY reminder_date ASC""", (patient_id,))
    rows = c.fetchall()
    conn.close()
    return [{"drug_id": r[0], "drug_name": r[1],
             "reminder_date": r[2], "reminder_sent": r[3]} for r in rows]


def get_due_reminders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = str(datetime.today().date())
    c.execute("""SELECT pd.drug_id,pd.patient_id,pd.drug_name,pd.reminder_date,
                        pp.full_name,pp.phone
                 FROM purchase_drugs pd
                 JOIN patient_profile pp ON pd.patient_id=pp.patient_id
                 WHERE pd.reminder_date<=? AND pd.reminder_sent=0""", (today,))
    rows = c.fetchall()
    conn.close()
    return [{"drug_id": r[0], "patient_id": r[1], "drug_name": r[2],
             "reminder_date": r[3], "full_name": r[4], "phone": r[5]}
            for r in rows]


def mark_reminder_sent(drug_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE purchase_drugs SET reminder_sent=1 WHERE drug_id=?",
              (drug_id,))
    conn.commit()
    conn.close()


def set_reminder_date_to_today(drug_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE purchase_drugs
                 SET reminder_date=?, reminder_sent=0
                 WHERE drug_id=?""",
              (str(datetime.today().date()), drug_id))
    conn.commit()
    conn.close()


# ── SYMPTOM FUNCTIONS (Module 3) ──────────────────────────────────────────────

def save_symptom_report(patient_id, drug_id, drug_name, raw_symptom,
                        severity, timing_ok, drug_stopped, symptom_improved):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO symptom_reports
                 (patient_id,drug_id,drug_name,raw_symptom,severity,
                  timing_ok,drug_stopped,symptom_improved,report_date)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (patient_id, drug_id, drug_name, raw_symptom, severity,
               1 if timing_ok else 0,
               1 if drug_stopped else 0,
               1 if symptom_improved else 0,
               str(datetime.now())))
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    print(f"[DB] Symptom saved: report_id={report_id}, drug={drug_name}")
    return report_id


def save_no_symptom_report(patient_id, drug_id, drug_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO symptom_reports
                 (patient_id,drug_id,drug_name,raw_symptom,severity,
                  timing_ok,drug_stopped,symptom_improved,report_date)
                 VALUES (?,?,?,'No symptoms','None',0,0,0,?)""",
              (patient_id, drug_id, drug_name, str(datetime.now())))
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_symptom_reports_for_patient(patient_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT report_id,drug_name,raw_symptom,meddra_pt,
                        severity,timing_ok,report_date
                 FROM symptom_reports
                 WHERE patient_id=?
                 ORDER BY report_date DESC""", (patient_id,))
    rows = c.fetchall()
    conn.close()
    return [{"report_id": r[0], "drug_name": r[1], "raw_symptom": r[2],
             "meddra_pt": r[3], "severity": r[4], "timing_ok": r[5],
             "report_date": r[6]} for r in rows]


def get_unprocessed_reports():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""SELECT report_id,drug_name,raw_symptom,severity,
                            patient_id,drug_id
                     FROM symptom_reports
                     WHERE (meddra_pt IS NULL OR meddra_pt='')
                       AND raw_symptom!='No symptoms'""")
        rows = c.fetchall()
    except:
        rows = []
    conn.close()
    return [{"report_id": r[0], "drug_name": r[1], "raw_symptom": r[2],
             "severity": r[3], "patient_id": r[4], "drug_id": r[5]}
            for r in rows]


def update_meddra_term(report_id, meddra_pt, meddra_soc):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE symptom_reports
                 SET meddra_pt=?, meddra_soc=?
                 WHERE report_id=?""", (meddra_pt, meddra_soc, report_id))
    conn.commit()
    conn.close()


# ── ADR ASSESSMENT FUNCTIONS (Modules 5-9) ───────────────────────────────────

def save_adr_assessment(patient_id, drug_name, meddra_pt,
                        confidence_score, naranjo_score, naranjo_category):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO adr_assessments
                 (patient_id,drug_name,meddra_pt,confidence_score,
                  naranjo_score,naranjo_category,review_date)
                 VALUES (?,?,?,?,?,?,?)""",
              (patient_id, drug_name, meddra_pt, confidence_score,
               naranjo_score, naranjo_category, str(datetime.now())))
    aid = c.lastrowid
    conn.commit()
    conn.close()
    return aid


def get_all_assessments():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""SELECT a.assessment_id,pp.full_name,a.drug_name,
                            a.meddra_pt,a.confidence_score,a.naranjo_score,
                            a.naranjo_category,a.pharmacist_status,a.review_date
                     FROM adr_assessments a
                     JOIN patient_profile pp ON a.patient_id=pp.patient_id
                     ORDER BY a.assessment_id DESC""")
        rows = c.fetchall()
    except:
        rows = []
    conn.close()
    return [{"assessment_id": r[0], "patient_name": r[1], "drug_name": r[2],
             "meddra_pt": r[3], "confidence_score": r[4], "naranjo_score": r[5],
             "naranjo_category": r[6], "pharmacist_status": r[7],
             "review_date": r[8]} for r in rows]


def update_assessment_status(assessment_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE adr_assessments
                 SET pharmacist_status=?, review_date=?
                 WHERE assessment_id=?""",
              (status, str(datetime.now()), assessment_id))
    conn.commit()
    conn.close()