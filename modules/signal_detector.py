# modules/signal_detector.py
# MODULE 8: PRR-based safety signal detection
import sqlite3, os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")


def calculate_prr(drug_name, meddra_pt):
    """
    Proportional Reporting Ratio (PRR) signal detection.
    PRR >= 2 with >= 3 reports = safety signal.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM adr_assessments")
        total_d = c.fetchone()[0] or 1
        c.execute("SELECT COUNT(*) FROM adr_assessments WHERE LOWER(meddra_pt)=LOWER(?)", (meddra_pt,))
        total_event = c.fetchone()[0] or 1
        c.execute("SELECT COUNT(*) FROM adr_assessments WHERE LOWER(drug_name) LIKE LOWER(?)", (f"%{drug_name}%",))
        total_drug = c.fetchone()[0] or 1
        c.execute("SELECT COUNT(*) FROM adr_assessments WHERE LOWER(drug_name) LIKE LOWER(?) AND LOWER(meddra_pt)=LOWER(?)",
                  (f"%{drug_name}%", meddra_pt))
        a = c.fetchone()[0] or 0
        conn.close()
    except:
        return {"signal": False, "prr": 0, "count": 0, "signal_flag": "Normal", "reason": "DB error"}

    if a < 3:
        return {"signal": False, "prr": 0, "count": a,
                "signal_flag": "Normal", "reason": "Need at least 3 reports"}

    prr = (a / total_drug) / (total_event / total_d)
    flag = "Alert" if prr >= 3 else ("Watch" if prr >= 2 else "Normal")
    return {"drug_name": drug_name, "meddra_pt": meddra_pt,
            "prr": round(prr, 2), "count": a, "signal": prr >= 2, "signal_flag": flag}


def run_signal_scan():
    """Scans all confirmed assessments and logs any signals found."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT drug_name,meddra_pt FROM adr_assessments WHERE pharmacist_status='Confirmed'")
        pairs = c.fetchall()
        conn.close()
    except:
        return []

    found = []
    for drug, pt in pairs:
        result = calculate_prr(drug, pt)
        if result.get("signal"):
            try:
                conn2 = sqlite3.connect(DB_PATH)
                c2 = conn2.cursor()
                c2.execute("""INSERT INTO signal_log
                              (drug_name,meddra_pt,month_year,report_count,prr_value,signal_flag)
                              VALUES (?,?,?,?,?,?)""",
                           (drug, pt, datetime.now().strftime("%Y-%m"),
                            result["count"], result["prr"], result["signal_flag"]))
                conn2.commit()
                conn2.close()
            except:
                pass
            found.append(result)
    return found