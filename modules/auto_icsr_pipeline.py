# modules/auto_icsr_pipeline.py
# PURPOSE: Complete automated pipeline:
#   1. Check if ADR is in Lexicomp
#   2. If NOT in Lexicomp → auto-generate ICSR
#   3. Auto-send email with ICSR files attached
#   4. Queue for PvPI VigiFlow submission
#   5. Return full status report

import sqlite3
import smtplib
import os
from modules.naranjo_calculator import calculate_naranjo
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from datetime             import datetime
from modules.naranjo_calculator import calculate_naranjo
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")

# ── YOUR EMAIL FOR RECEIVING ICSR NOTIFICATIONS ───────────────────────────────
# Set this to your email to receive auto-generated ICSR reports
YOUR_EMAIL    = ""        # e.g. "vishal@gmail.com"
YOUR_PASSWORD = ""        # Gmail App Password (16 chars)
# Leave both empty to skip email sending (files still generated locally)


def run_full_pipeline(report_id):
    """
    MAIN PIPELINE FUNCTION.

    Runs the complete ADR → Lexicomp check → ICSR generation pipeline
    for a given symptom report.

    Steps:
        1. Fetch symptom report from DB
        2. Run NLP if meddra_pt not yet set
        3. Check Lexicomp
        4. If unknown ADR: generate CIOMS PDF + E2B XML + send email
        5. Update ICSR queue in DB
        6. Return complete status dict

    Args:
        report_id: int — the symptom_reports.report_id

    Returns:
        dict with full pipeline result
    """
    from modules.nlp_engine       import standardize_symptom
    from modules.meddra_mapper    import get_meddra_hierarchy
    from modules.lexicomp_checker import check_adr_in_lexicomp
    from modules.icsr_generator   import generate_cioms_pdf, generate_e2b_xml
    from modules.patient_db       import update_meddra_term

    result = {
        "report_id":      report_id,
        "timestamp":      str(datetime.now()),
        "steps":          [],
        "final_action":   None,
        "icsr_generated": False,
        "email_sent":     False,
        "files":          {}
    }

    # ── STEP 1: Fetch report ─────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT report_id, drug_name, raw_symptom, meddra_pt,
               severity, timing_ok, drug_stopped, symptom_improved,
               patient_id
        FROM symptom_reports WHERE report_id=?
    """, (report_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        result["error"] = f"Report ID {report_id} not found"
        return result

    (rid, drug_name, raw_symptom, meddra_pt, severity,
     timing_ok, drug_stopped, symptom_improved, patient_id) = row

    result["steps"].append({
        "step": "1_fetch",
        "status": "OK",
        "data": {"drug": drug_name, "symptom": raw_symptom}
    })

    # ── STEP 2: Run NLP if meddra_pt not set ────────────────────────────
    if not meddra_pt or meddra_pt == "":
        nlp_result = standardize_symptom(raw_symptom)
        meddra_pt  = nlp_result["meddra_pt"]
        hierarchy  = get_meddra_hierarchy(meddra_pt)
        update_meddra_term(report_id, meddra_pt, hierarchy["soc"])
        result["steps"].append({
            "step": "2_nlp",
            "status": "processed",
            "meddra_pt": meddra_pt,
            "method": nlp_result["method"]
        })
    else:
        result["steps"].append({
            "step": "2_nlp",
            "status": "already_done",
            "meddra_pt": meddra_pt
        })

    result["drug_name"] = drug_name
    result["meddra_pt"] = meddra_pt

    # ── STEP 3: Check Lexicomp ───────────────────────────────────────────
    lexicomp_check = check_adr_in_lexicomp(drug_name, meddra_pt)
    result["lexicomp_check"] = lexicomp_check
    result["steps"].append({
        "step":   "3_lexicomp_check",
        "status": "found" if lexicomp_check["found"] else "not_found",
        "action": lexicomp_check["action"],
        "reason": lexicomp_check["reason"]
    })

    # ── STEP 4a: ADR is KNOWN in Lexicomp → No ICSR needed ──────────────
    if lexicomp_check["action"] == "no_icsr_needed":
        result["final_action"] = "no_icsr_needed"
        result["message"] = (
            f"ADR '{meddra_pt}' for drug '{drug_name}' is already "
            f"documented in Lexicomp. No new ICSR submission required. "
            f"This is an expected, known adverse reaction."
        )
        _update_icsr_queue(report_id, drug_name, meddra_pt,
                           "known_in_lexicomp", "Not Required")
        return result
# ── STEP 3.5: AUTO-CALCULATE NARANJO SCORE ───────────────────────────
    naranjo_answers = {
        "Q1": "unknown",
        "Q2": "yes" if timing_ok else "no",
        "Q3": "yes" if symptom_improved else "unknown",
        "Q4": "unknown",
        "Q5": "unknown",
        "Q6": "unknown",
        "Q7": "unknown",
        "Q8": "unknown",
        "Q9": "unknown",
        "Q10": "yes" if drug_stopped else "unknown",
    }
    naranjo_result = calculate_naranjo(naranjo_answers)

    result["naranjo_score"]    = naranjo_result["score"]
    result["naranjo_category"] = naranjo_result["category"]
    result["steps"].append({
        "step": "3.5_naranjo",
        "status": "calculated",
        "score": naranjo_result["score"],
        "category": naranjo_result["category"],
        "note": "Auto-calculated from symptom form data (timing, dechallenge)"
    })

    from modules.patient_db import save_adr_assessment
    save_adr_assessment(
        patient_id, drug_name, meddra_pt,
        confidence_score=0,
        naranjo_score=naranjo_result["score"],
        naranjo_category=naranjo_result["category"]
    )
    # ── STEP 4b: ADR is UNKNOWN → Generate ICSR ─────────────────────────
    result["steps"].append({
        "step": "4_icsr_generation",
        "status": "starting",
        "reason": "ADR not found in Lexicomp — auto-generating ICSR"
    })

    # Generate CIOMS I PDF
    pdf_path, pdf_err = generate_cioms_pdf(report_id)
    if pdf_err:
        result["steps"].append({"step": "4a_pdf", "status": "error", "error": pdf_err})
    else:
        result["files"]["cioms_pdf"] = pdf_path
        result["icsr_generated"] = True
        result["steps"].append({"step": "4a_pdf", "status": "generated", "path": pdf_path})

    # Generate E2B(R3) XML
    xml_path, xml_err = generate_e2b_xml(report_id)
    if xml_err:
        result["steps"].append({"step": "4b_xml", "status": "error", "error": xml_err})
    else:
        result["files"]["e2b_xml"] = xml_path
        result["steps"].append({"step": "4b_xml", "status": "generated", "path": xml_path})

    # ── STEP 5: Send email with ICSR files ───────────────────────────────
    if YOUR_EMAIL and YOUR_PASSWORD and result["icsr_generated"]:
        email_sent = _send_icsr_email(
            drug_name, meddra_pt, report_id,
            pdf_path if not pdf_err else None,
            xml_path if not xml_err else None
        )
        result["email_sent"] = email_sent
        result["steps"].append({
            "step": "5_email",
            "status": "sent" if email_sent else "failed"
        })
    else:
        result["steps"].append({
            "step": "5_email",
            "status": "skipped",
            "reason": "Email not configured (files saved locally)"
        })

    # ── STEP 6: Update ICSR queue ─────────────────────────────────────────
    _update_icsr_queue(
        report_id, drug_name, meddra_pt,
        "unknown_in_lexicomp", "Ready_for_Submission",
        pdf_path if not pdf_err else None,
        xml_path if not xml_err else None
    )

    result["final_action"] = "icsr_generated"
    result["message"] = (
        f"ADR '{meddra_pt}' is NOT in Lexicomp for '{drug_name}'. "
        f"ICSR has been auto-generated. "
        f"Please submit the XML file to PvPI VigiFlow: "
        f"https://vigiflow.ipc.gov.in"
    )
    result["pvpi_portal"] = "https://vigiflow.ipc.gov.in"

    return result


def _send_icsr_email(drug_name, meddra_pt, report_id, pdf_path, xml_path):
    """Sends email with ICSR files attached."""
    try:
        msg = MIMEMultipart()
        msg["From"]    = YOUR_EMAIL
        msg["To"]      = YOUR_EMAIL
        msg["Subject"] = (f"PVPro ICSR Alert — Unlisted ADR Detected: "
                          f"{drug_name} → {meddra_pt}")

        body = f"""
PVPro Automated ICSR Alert
===========================

An unlisted Adverse Drug Reaction has been detected:

Drug:       {drug_name}
ADR:        {meddra_pt}
Report ID:  PVPRO-{report_id:04d}
Timestamp:  {datetime.now().strftime('%d %b %Y %H:%M')}

This ADR is NOT documented in Lexicomp for this drug.
An ICSR has been automatically generated.

ACTION REQUIRED:
1. Review the attached CIOMS I PDF
2. Upload the attached E2B XML to PvPI VigiFlow
3. Portal: https://vigiflow.ipc.gov.in

Files attached:
- CIOMS_I_Report (PDF) — human-readable format
- E2B_R3_Report (XML) — upload to VigiFlow

Generated by PharmVigilance Pro (Student PV Project)
Reporter: Vishal Raj P, Pharm.D Student
"""
        msg.attach(MIMEText(body, "plain"))

        # Attach PDF
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f"attachment; filename={os.path.basename(pdf_path)}")
                msg.attach(part)

        # Attach XML
        if xml_path and os.path.exists(xml_path):
            with open(xml_path, "rb") as f:
                part = MIMEBase("application", "xml")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f"attachment; filename={os.path.basename(xml_path)}")
                msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(YOUR_EMAIL, YOUR_PASSWORD)
            server.sendmail(YOUR_EMAIL, YOUR_EMAIL, msg.as_string())

        print(f"[ICSR Email] Sent to {YOUR_EMAIL}")
        return True

    except Exception as e:
        print(f"[ICSR Email] Failed: {e}")
        return False


def _update_icsr_queue(report_id, drug_name, meddra_pt,
                       check_result, status, pdf_path=None, xml_path=None):
    """Updates the ICSR queue table."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO icsr_queue
        (report_id, drug_name, meddra_pt, check_result,
         icsr_status, pdf_path, xml_path, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (report_id, drug_name, meddra_pt, check_result,
          status, pdf_path, xml_path, str(datetime.now())))
    conn.commit()
    conn.close()


def get_icsr_queue():
    """Returns all items in the ICSR queue."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT queue_id, report_id, drug_name, meddra_pt,
                   check_result, icsr_status, pdf_path, xml_path, created_at
            FROM icsr_queue
            ORDER BY created_at DESC
        """)
        rows = c.fetchall()
    except:
        rows = []
    conn.close()
    return [
        {"queue_id": r[0], "report_id": r[1], "drug_name": r[2],
         "meddra_pt": r[3], "check_result": r[4], "icsr_status": r[5],
         "pdf_path": r[6], "xml_path": r[7], "created_at": r[8]}
        for r in rows
    ]