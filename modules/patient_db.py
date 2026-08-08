# modules/patient_db.py


import os
from datetime import datetime, timedelta

# Simple database connection that works both locally and on Render
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    def get_conn():
        return psycopg2.connect(DATABASE_URL)
    PH = "%s"
else:
    import sqlite3
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "database", "pvpro.db"
    )
    def get_conn():
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return sqlite3.connect(DB_PATH)
    PH = "?"


def q(sql):
    """Convert ? placeholders to %s for PostgreSQL."""
    return sql.replace("?", PH) if USE_POSTGRES else sql


def init_db():
    conn = get_conn()
    c = conn.cursor()

    if USE_POSTGRES:
        tables = [
            """CREATE TABLE IF NOT EXISTS patient_profile (
                patient_id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL, age INTEGER, gender TEXT,
                phone TEXT UNIQUE NOT NULL, created_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS purchases (
                purchase_id SERIAL PRIMARY KEY,
                patient_id INTEGER, bill_name TEXT, bill_date TEXT,
                invoice_no TEXT, source TEXT, captured_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS purchase_drugs (
                drug_id SERIAL PRIMARY KEY,
                purchase_id INTEGER, patient_id INTEGER,
                drug_name TEXT, quantity TEXT, mrp TEXT,
                reminder_date TEXT, reminder_sent INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS symptom_reports (
                report_id SERIAL PRIMARY KEY,
                patient_id INTEGER, drug_id INTEGER, drug_name TEXT,
                raw_symptom TEXT, meddra_pt TEXT, meddra_soc TEXT,
                severity TEXT, timing_ok INTEGER, drug_stopped INTEGER,
                symptom_improved INTEGER, report_date TEXT)""",
            """CREATE TABLE IF NOT EXISTS adr_knowledge_base (
                kb_id SERIAL PRIMARY KEY,
                drug_name TEXT, meddra_pt TEXT, meddra_soc TEXT,
                frequency TEXT, severity TEXT)""",
            """CREATE TABLE IF NOT EXISTS adr_assessments (
                assessment_id SERIAL PRIMARY KEY,
                patient_id INTEGER, drug_name TEXT, meddra_pt TEXT,
                confidence_score INTEGER, naranjo_score INTEGER,
                naranjo_category TEXT,
                pharmacist_status TEXT DEFAULT 'Pending',
                review_date TEXT)""",
            """CREATE TABLE IF NOT EXISTS signal_log (
                signal_id SERIAL PRIMARY KEY,
                drug_name TEXT, meddra_pt TEXT, month_year TEXT,
                report_count INTEGER, prr_value REAL, signal_flag TEXT)""",
            """CREATE TABLE IF NOT EXISTS openfda_cache (
                cache_id SERIAL PRIMARY KEY,
                drug_name TEXT UNIQUE, adverse_reactions_text TEXT,
                warnings_text TEXT, fetched_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS icsr_queue (
                queue_id SERIAL PRIMARY KEY,
                report_id INTEGER, drug_name TEXT, meddra_pt TEXT,
                check_result TEXT, icsr_status TEXT DEFAULT 'Pending',
                pdf_path TEXT, xml_path TEXT,
                created_at TEXT, submitted_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS push_subscriptions (
                sub_id SERIAL PRIMARY KEY,
                patient_id INTEGER, subscription_json TEXT,
                device_name TEXT, created_at TEXT)""",
        ]
    else:
        tables = [
            """CREATE TABLE IF NOT EXISTS patient_profile (
                patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL, age INTEGER, gender TEXT,
                phone TEXT UNIQUE NOT NULL, created_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS purchases (
                purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER, bill_name TEXT, bill_date TEXT,
                invoice_no TEXT, source TEXT, captured_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS purchase_drugs (
                drug_id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_id INTEGER, patient_id INTEGER,
                drug_name TEXT, quantity TEXT, mrp TEXT,
                reminder_date TEXT, reminder_sent INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS symptom_reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER, drug_id INTEGER, drug_name TEXT,
                raw_symptom TEXT, meddra_pt TEXT, meddra_soc TEXT,
                severity TEXT, timing_ok INTEGER, drug_stopped INTEGER,
                symptom_improved INTEGER, report_date TEXT)""",
            """CREATE TABLE IF NOT EXISTS adr_knowledge_base (
                kb_id INTEGER PRIMARY KEY AUTOINCREMENT,
                drug_name TEXT, meddra_pt TEXT, meddra_soc TEXT,
                frequency TEXT, severity TEXT)""",
            """CREATE TABLE IF NOT EXISTS adr_assessments (
                assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER, drug_name TEXT, meddra_pt TEXT,
                confidence_score INTEGER, naranjo_score INTEGER,
                naranjo_category TEXT,
                pharmacist_status TEXT DEFAULT 'Pending',
                review_date TEXT)""",
            """CREATE TABLE IF NOT EXISTS signal_log (
                signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                drug_name TEXT, meddra_pt TEXT, month_year TEXT,
                report_count INTEGER, prr_value REAL, signal_flag TEXT)""",
            """CREATE TABLE IF NOT EXISTS openfda_cache (
                cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
                drug_name TEXT UNIQUE, adverse_reactions_text TEXT,
                warnings_text TEXT, fetched_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS icsr_queue (
                queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER, drug_name TEXT, meddra_pt TEXT,
                check_result TEXT, icsr_status TEXT DEFAULT 'Pending',
                pdf_path TEXT, xml_path TEXT,
                created_at TEXT, submitted_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS push_subscriptions (
                sub_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER, subscription_json TEXT,
                device_name TEXT, created_at TEXT)""",
        ]

    for sql in tables:
        try:
            c.execute(sql)
        except Exception as e:
            print(f"[DB] Table note: {e}")

    conn.commit()
    conn.close()
    _seed_adr_kb()
    print(f"[DB] Ready. Mode: {'PostgreSQL/Supabase' if USE_POSTGRES else 'SQLite'}")


def _seed_adr_kb():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM adr_knowledge_base")
    if c.fetchone()[0] > 0:
        conn.close()
        return
    data = [
        ("Amlodipine","Peripheral oedema","Cardiac disorders","Common","Mild"),
        ("Amlodipine","Headache","Nervous system disorders","Common","Mild"),
        ("Metformin","Diarrhoea","Gastrointestinal disorders","Common","Mild"),
        ("Metformin","Nausea","Gastrointestinal disorders","Common","Mild"),
        ("Atorvastatin","Myalgia","Musculoskeletal disorders","Common","Moderate"),
        ("Amoxicillin","Rash","Skin disorders","Common","Mild"),
        ("Azithromycin","Nausea","Gastrointestinal disorders","Common","Mild"),
        ("Cetirizine","Somnolence","Nervous system disorders","Common","Mild"),
        ("Ibuprofen","Nausea","Gastrointestinal disorders","Common","Mild"),
        ("Paracetamol","Rash","Skin disorders","Rare","Mild"),
    ]
    ph = PH
    c.executemany(
        f"INSERT INTO adr_knowledge_base (drug_name,meddra_pt,meddra_soc,frequency,severity) "
        f"VALUES ({ph},{ph},{ph},{ph},{ph})", data)
    conn.commit()
    conn.close()


def create_or_get_profile(full_name, age, gender, phone):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("SELECT patient_id FROM patient_profile WHERE phone=?"), (phone,))
    row = c.fetchone()
    if row:
        pid = row[0]
    else:
        if USE_POSTGRES:
            c.execute(
                "INSERT INTO patient_profile (full_name,age,gender,phone,created_at) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING patient_id",
                (full_name, age, gender, phone, str(datetime.now())))
            pid = c.fetchone()[0]
        else:
            c.execute(
                "INSERT INTO patient_profile (full_name,age,gender,phone,created_at) "
                "VALUES (?,?,?,?,?)",
                (full_name, age, gender, phone, str(datetime.now())))
            pid = c.lastrowid
    conn.commit()
    conn.close()
    return pid


def get_profile_by_id(patient_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("SELECT * FROM patient_profile WHERE patient_id=?"), (patient_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {}
    return {"patient_id":row[0],"full_name":row[1],"age":row[2],
            "gender":row[3],"phone":row[4],"created_at":row[5]}


def save_purchase(patient_id, extracted_data):
    conn = get_conn()
    c = conn.cursor()
    bill_date_str = extracted_data.get("bill_date", "")
    bill_date = None
    for fmt in ["%Y-%m-%d %H:%M:%S","%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"]:
        try:
            bill_date = datetime.strptime(bill_date_str, fmt)
            break
        except:
            continue
    if not bill_date:
        bill_date = datetime.today()
    reminder_date = bill_date + timedelta(days=3)

    if USE_POSTGRES:
        c.execute(
            "INSERT INTO purchases (patient_id,bill_name,bill_date,invoice_no,source,captured_at) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING purchase_id",
            (patient_id, extracted_data.get("patient_name","N/A"),
             extracted_data.get("bill_date", str(datetime.today().date())),
             extracted_data.get("invoice_no","N/A"),
             extracted_data.get("source","Unknown"), str(datetime.now())))
        purchase_id = c.fetchone()[0]
    else:
        c.execute(
            "INSERT INTO purchases (patient_id,bill_name,bill_date,invoice_no,source,captured_at) "
            "VALUES (?,?,?,?,?,?)",
            (patient_id, extracted_data.get("patient_name","N/A"),
             extracted_data.get("bill_date", str(datetime.today().date())),
             extracted_data.get("invoice_no","N/A"),
             extracted_data.get("source","Unknown"), str(datetime.now())))
        purchase_id = c.lastrowid

    drugs = extracted_data.get("drugs",[]) or [{"drug_name":"Unknown","quantity":"N/A","price":"N/A"}]
    for drug in drugs:
        c.execute(q(
            "INSERT INTO purchase_drugs (purchase_id,patient_id,drug_name,quantity,mrp,reminder_date) "
            "VALUES (?,?,?,?,?,?)"),
            (purchase_id, patient_id,
             drug.get("drug_name","Unknown"),
             drug.get("quantity","N/A"),
             drug.get("price", drug.get("mrp","N/A")),
             str(reminder_date.date())))
    conn.commit()
    conn.close()
    return purchase_id


def get_purchase_history(patient_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("""SELECT p.purchase_id,p.bill_date,p.invoice_no,p.source,
               pd.drug_name,pd.quantity,pd.mrp,pd.drug_id,pd.reminder_date,pd.reminder_sent
               FROM purchases p JOIN purchase_drugs pd ON p.purchase_id=pd.purchase_id
               WHERE p.patient_id=? ORDER BY p.purchase_id DESC"""), (patient_id,))
    rows = c.fetchall()
    conn.close()
    return [{"purchase_id":r[0],"bill_date":r[1],"invoice_no":r[2],"source":r[3],
             "drug_name":r[4],"quantity":r[5],"mrp":r[6],"drug_id":r[7],
             "reminder_date":r[8],"reminder_sent":r[9]} for r in rows]


def get_all_reminders_for_patient(patient_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("SELECT drug_id,drug_name,reminder_date,reminder_sent "
                "FROM purchase_drugs WHERE patient_id=? ORDER BY reminder_date ASC"),
              (patient_id,))
    rows = c.fetchall()
    conn.close()
    return [{"drug_id":r[0],"drug_name":r[1],"reminder_date":r[2],"reminder_sent":r[3]}
            for r in rows]


def get_due_reminders():
    conn = get_conn()
    c = conn.cursor()
    today = str(datetime.today().date())
    c.execute(q("""SELECT pd.drug_id,pd.patient_id,pd.drug_name,pd.reminder_date,
               pp.full_name,pp.phone FROM purchase_drugs pd
               JOIN patient_profile pp ON pd.patient_id=pp.patient_id
               WHERE pd.reminder_date<=? AND pd.reminder_sent=0"""), (today,))
    rows = c.fetchall()
    conn.close()
    return [{"drug_id":r[0],"patient_id":r[1],"drug_name":r[2],
             "reminder_date":r[3],"full_name":r[4],"phone":r[5]} for r in rows]


def mark_reminder_sent(drug_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("UPDATE purchase_drugs SET reminder_sent=1 WHERE drug_id=?"), (drug_id,))
    conn.commit()
    conn.close()


def set_reminder_date_to_today(drug_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("UPDATE purchase_drugs SET reminder_date=?,reminder_sent=0 WHERE drug_id=?"),
              (str(datetime.today().date()), drug_id))
    conn.commit()
    conn.close()


def save_symptom_report(patient_id, drug_id, drug_name, raw_symptom,
                        severity, timing_ok, drug_stopped, symptom_improved):
    conn = get_conn()
    c = conn.cursor()
    vals = (patient_id, drug_id, drug_name, raw_symptom, severity,
            1 if timing_ok else 0, 1 if drug_stopped else 0,
            1 if symptom_improved else 0, str(datetime.now()))
    if USE_POSTGRES:
        c.execute(
            "INSERT INTO symptom_reports "
            "(patient_id,drug_id,drug_name,raw_symptom,severity,"
            "timing_ok,drug_stopped,symptom_improved,report_date) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING report_id", vals)
        report_id = c.fetchone()[0]
    else:
        c.execute(
            "INSERT INTO symptom_reports "
            "(patient_id,drug_id,drug_name,raw_symptom,severity,"
            "timing_ok,drug_stopped,symptom_improved,report_date) "
            "VALUES (?,?,?,?,?,?,?,?,?)", vals)
        report_id = c.lastrowid
    conn.commit()
    conn.close()
    return report_id


def save_no_symptom_report(patient_id, drug_id, drug_name):
    conn = get_conn()
    c = conn.cursor()
    vals = (patient_id, drug_id, drug_name, str(datetime.now()))
    if USE_POSTGRES:
        c.execute(
            "INSERT INTO symptom_reports "
            "(patient_id,drug_id,drug_name,raw_symptom,severity,"
            "timing_ok,drug_stopped,symptom_improved,report_date) "
            "VALUES (%s,%s,%s,'No symptoms','None',0,0,0,%s) RETURNING report_id", vals)
        report_id = c.fetchone()[0]
    else:
        c.execute(
            "INSERT INTO symptom_reports "
            "(patient_id,drug_id,drug_name,raw_symptom,severity,"
            "timing_ok,drug_stopped,symptom_improved,report_date) "
            "VALUES (?,?,?,'No symptoms','None',0,0,0,?)", vals)
        report_id = c.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_symptom_reports_for_patient(patient_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("""SELECT report_id,drug_name,raw_symptom,meddra_pt,
               severity,timing_ok,report_date FROM symptom_reports
               WHERE patient_id=? ORDER BY report_date DESC"""), (patient_id,))
    rows = c.fetchall()
    conn.close()
    return [{"report_id":r[0],"drug_name":r[1],"raw_symptom":r[2],
             "meddra_pt":r[3],"severity":r[4],"timing_ok":r[5],
             "report_date":r[6]} for r in rows]


def get_unprocessed_reports():
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(q("""SELECT report_id,drug_name,raw_symptom,severity,patient_id,drug_id
                   FROM symptom_reports
                   WHERE (meddra_pt IS NULL OR meddra_pt='')
                   AND raw_symptom!='No symptoms'"""))
        rows = c.fetchall()
    except:
        rows = []
    conn.close()
    return [{"report_id":r[0],"drug_name":r[1],"raw_symptom":r[2],
             "severity":r[3],"patient_id":r[4],"drug_id":r[5]} for r in rows]


def update_meddra_term(report_id, meddra_pt, meddra_soc):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("UPDATE symptom_reports SET meddra_pt=?,meddra_soc=? WHERE report_id=?"),
              (meddra_pt, meddra_soc, report_id))
    conn.commit()
    conn.close()


def save_adr_assessment(patient_id, drug_name, meddra_pt,
                        confidence_score, naranjo_score, naranjo_category):
    conn = get_conn()
    c = conn.cursor()
    vals = (patient_id, drug_name, meddra_pt, confidence_score,
            naranjo_score, naranjo_category, str(datetime.now()))
    if USE_POSTGRES:
        c.execute(
            "INSERT INTO adr_assessments "
            "(patient_id,drug_name,meddra_pt,confidence_score,"
            "naranjo_score,naranjo_category,review_date) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING assessment_id", vals)
        aid = c.fetchone()[0]
    else:
        c.execute(
            "INSERT INTO adr_assessments "
            "(patient_id,drug_name,meddra_pt,confidence_score,"
            "naranjo_score,naranjo_category,review_date) "
            "VALUES (?,?,?,?,?,?,?)", vals)
        aid = c.lastrowid
    conn.commit()
    conn.close()
    return aid


def get_all_assessments():
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("""SELECT a.assessment_id,pp.full_name,a.drug_name,a.meddra_pt,
                   a.confidence_score,a.naranjo_score,a.naranjo_category,
                   a.pharmacist_status,a.review_date
                   FROM adr_assessments a
                   JOIN patient_profile pp ON a.patient_id=pp.patient_id
                   ORDER BY a.assessment_id DESC""")
        rows = c.fetchall()
    except:
        rows = []
    conn.close()
    return [{"assessment_id":r[0],"patient_name":r[1],"drug_name":r[2],
             "meddra_pt":r[3],"confidence_score":r[4],"naranjo_score":r[5],
             "naranjo_category":r[6],"pharmacist_status":r[7],
             "review_date":r[8]} for r in rows]


def update_assessment_status(assessment_id, status):
    conn = get_conn()
    c = conn.cursor()
    c.execute(q("UPDATE adr_assessments SET pharmacist_status=?,review_date=? "
                "WHERE assessment_id=?"),
              (status, str(datetime.now()), assessment_id))
    conn.commit()
    conn.close()