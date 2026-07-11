# modules/auto_icsr_pipeline.py
# Auto-pipeline: ADR detection → ICSR generation → Email to PvPI

import sqlite3
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from datetime             import datetime
from modules.naranjo_calculator import calculate_naranjo

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database", "pvpro.db"
)

# ── SET YOUR REAL GMAIL CREDENTIALS HERE ─────────────────────────────────────
# Step 1: Use your real Gmail address below
# Step 2: Go to myaccount.google.com → Security → App Passwords
#         → Generate a 16-character app password → paste it below
YOUR_EMAIL    = "vishal636pharmd@gmail.com"    # e.g. "vishal636pharmd@gmail.com"
YOUR_PASSWORD = "erbs mdeo ylpk hqrs "    # 16-char App Password e.g. "abcd efgh ijkl mnop"

# PvPI official email for ADR submission (legitimate alternate channel)
PVPI_EMAIL = "pvpi@cdsco.nic.in"
# ─────────────────────────────────────────────────────────────────────────────


def run_full_pipeline(report_id):
    """
    Complete ADR pipeline:
    1. Fetch report from DB
    2. Run NLP to get MedDRA term
    3. Calculate Naranjo score automatically
    4. Check OpenFDA — is this ADR known for this drug?
    5. If UNKNOWN → generate CIOMS PDF + E2B XML → email to PvPI
    6. Update ICSR queue
    """
    from modules.nlp_engine       import standardize_symptom
    from modules.meddra_mapper    import get_meddra_hierarchy
    from modules.lexicomp_checker import check_adr_in_lexicomp
    from modules.icsr_generator   import generate_cioms_pdf, generate_e2b_xml
    from modules.patient_db       import update_meddra_term, save_adr_assessment

    result = {
        "report_id":      report_id,
        "timestamp":      str(datetime.now()),
        "steps":          [],
        "final_action":   None,
        "icsr_generated": False,
        "email_sent":     False,
        "files":          {}
    }

    # ── STEP 1: Fetch report ──────────────────────────────────────────────
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
        "step": "1_fetch", "status": "OK",
        "data": {"drug": drug_name, "symptom": raw_symptom}
    })

    # ── STEP 2: NLP → MedDRA term ────────────────────────────────────────
    if not meddra_pt:
        nlp_result = standardize_symptom(raw_symptom)
        meddra_pt  = nlp_result["meddra_pt"]
        hierarchy  = get_meddra_hierarchy(meddra_pt)
        update_meddra_term(report_id, meddra_pt, hierarchy["soc"])
        result["steps"].append({
            "step": "2_nlp", "status": "processed",
            "meddra_pt": meddra_pt, "method": nlp_result["method"]
        })
    else:
        result["steps"].append({
            "step": "2_nlp", "status": "already_done",
            "meddra_pt": meddra_pt
        })

    result["drug_name"] = drug_name
    result["meddra_pt"] = meddra_pt

    # ── STEP 3: Auto-calculate Naranjo score ──────────────────────────────
    # Uses data already collected from symptom form:
    #   timing_ok       → Q2 (ADR appeared after drug?)
    #   symptom_improved → Q3 (improved after stopping?)
    #   drug_stopped    → Q10 (objective evidence)
    naranjo_answers = {
        "Q1":  "unknown",
        "Q2":  "yes" if timing_ok        else "no",
        "Q3":  "yes" if symptom_improved else "unknown",
        "Q4":  "unknown",
        "Q5":  "unknown",
        "Q6":  "unknown",
        "Q7":  "unknown",
        "Q8":  "unknown",
        "Q9":  "unknown",
        "Q10": "yes" if drug_stopped     else "unknown",
    }
    naranjo_result = calculate_naranjo(naranjo_answers)

    result["naranjo_score"]    = naranjo_result["score"]
    result["naranjo_category"] = naranjo_result["category"]
    result["steps"].append({
        "step": "3_naranjo", "status": "calculated",
        "score": naranjo_result["score"],
        "category": naranjo_result["category"]
    })

    # Save assessment with Naranjo score (appears in ICSR report)
    save_adr_assessment(
        patient_id, drug_name, meddra_pt,
        confidence_score=0,
        naranjo_score=naranjo_result["score"],
        naranjo_category=naranjo_result["category"]
    )

    # ── STEP 4: OpenFDA check — is this ADR documented? ──────────────────
    fda_check = check_adr_in_lexicomp(drug_name, meddra_pt)
    result["fda_check"] = fda_check
    result["steps"].append({
        "step":   "4_fda_check",
        "status": "found" if fda_check["found"] else "not_found",
        "action": fda_check["action"],
        "reason": fda_check["reason"]
    })

    # ── STEP 4a: KNOWN ADR → no report needed ────────────────────────────
    if fda_check["action"] == "no_icsr_needed":
        result["final_action"] = "no_icsr_needed"
        result["message"] = (
            f"'{meddra_pt}' is documented in the FDA label for "
            f"'{drug_name}'. No new ICSR needed — known reaction. "
            f"Naranjo score: {naranjo_result['score']} "
            f"({naranjo_result['category']})"
        )
        _update_icsr_queue(report_id, drug_name, meddra_pt,
                           "known_in_fda_label", "Not Required")
        return result

    # ── STEP 4b: UNKNOWN ADR → generate ICSR ────────────────────────────
    result["steps"].append({
        "step": "5_icsr_generation", "status": "starting",
        "reason": "ADR not in FDA label — generating ICSR"
    })

    # Generate CIOMS I PDF
    pdf_path, pdf_err = generate_cioms_pdf(report_id)
    if pdf_err:
        result["steps"].append({"step": "5a_pdf", "status": "error",
                                 "error": pdf_err})
    else:
        result["files"]["cioms_pdf"] = pdf_path
        result["icsr_generated"] = True
        result["steps"].append({"step": "5a_pdf", "status": "generated",
                                 "path": pdf_path})

    # Generate E2B(R3) XML
    xml_path, xml_err = generate_e2b_xml(report_id)
    if xml_err:
        result["steps"].append({"step": "5b_xml", "status": "error",
                                 "error": xml_err})
    else:
        result["files"]["e2b_xml"] = xml_path
        result["steps"].append({"step": "5b_xml", "status": "generated",
                                 "path": xml_path})

    # ── STEP 5: Email ICSR to PvPI + yourself ────────────────────────────
    if YOUR_EMAIL and YOUR_PASSWORD and result["icsr_generated"]:
        email_sent = _send_icsr_email(
            drug_name, meddra_pt, report_id,
            naranjo_result["score"], naranjo_result["category"],
            pdf_path if not pdf_err else None,
            xml_path if not xml_err else None
        )
        result["email_sent"] = email_sent
        result["steps"].append({
            "step": "6_email",
            "status": "sent" if email_sent else "failed",
            "recipients": [YOUR_EMAIL, PVPI_EMAIL]
        })
    else:
        result["steps"].append({
            "step": "6_email",
            "status": "skipped",
            "reason": "Email credentials not configured in auto_icsr_pipeline.py"
        })

    # ── STEP 6: Update queue ──────────────────────────────────────────────
    _update_icsr_queue(
        report_id, drug_name, meddra_pt,
        "unknown_in_fda_label", "Submitted_to_PvPI",
        pdf_path if not pdf_err else None,
        xml_path if not xml_err else None
    )

    result["final_action"] = "icsr_generated"
    result["message"] = (
        f"'{meddra_pt}' is NOT in the FDA label for '{drug_name}'. "
        f"ICSR auto-generated. Naranjo: {naranjo_result['score']} "
        f"({naranjo_result['category']}). "
        f"Report emailed to PvPI at {PVPI_EMAIL}."
    )
    return result


def _send_icsr_email(drug_name, meddra_pt, report_id,
                     naranjo_score, naranjo_category,
                     pdf_path, xml_path):
    """
    Sends ICSR email to:
    1. YOUR_EMAIL (your Gmail — for your records)
    2. pvpi@cdsco.nic.in (PvPI official — legitimate submission)
    """
    try:
        msg = MIMEMultipart()
        msg["From"]    = YOUR_EMAIL
        msg["To"]      = f"{YOUR_EMAIL}, {PVPI_EMAIL}"
        msg["Subject"] = (
            f"Spontaneous ADR Report — {drug_name} / {meddra_pt} "
            f"| PVPRO-{report_id:04d} | India"
        )

        body = f"""
ADVERSE DRUG REACTION REPORT
Pharmacovigilance Programme of India (PvPI)
============================================

Report Reference : PVPRO-{report_id:04d}
Date             : {datetime.now().strftime('%d %b %Y %H:%M')}
Report Type      : Spontaneous ADR (Student Reporter)

DRUG              : {drug_name}
ADVERSE REACTION  : {meddra_pt}
NARANJO SCORE     : {naranjo_score} — {naranjo_category}

REPORTER DETAILS
  Name            : Vishal Raj P
  Qualification   : Pharm.D Student (Year 2)
  Institution     : Pharmacy College, India
  Email           : {YOUR_EMAIL}

NOTE:
This ADR was not found in the FDA drug label for the above drug.
It has been flagged as a potentially undocumented reaction.

ATTACHED FILES:
  1. CIOMS I PDF — standard paper format report
  2. ICH E2B(R3) XML — electronic format for VigiFlow upload

Alternative submission: pvpi@cdsco.nic.in | 1800-180-3024

Generated by PharmVigilance Pro — Student PV Project, India.
"""
        msg.attach(MIMEText(body, "plain"))

        # Attach CIOMS I PDF
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename=CIOMS_Report_{report_id}.pdf"
                )
                msg.attach(part)

        # Attach E2B XML
        if xml_path and os.path.exists(xml_path):
            with open(xml_path, "rb") as f:
                part = MIMEBase("application", "xml")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename=E2B_Report_{report_id}.xml"
                )
                msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(YOUR_EMAIL, YOUR_PASSWORD)
            server.sendmail(
                YOUR_EMAIL,
                [YOUR_EMAIL, PVPI_EMAIL],
                msg.as_string()
            )

        print(f"[ICSR Email] Sent to {YOUR_EMAIL} and {PVPI_EMAIL}")
        return True

    except Exception as e:
        print(f"[ICSR Email] Failed: {e}")
        print(f"[ICSR Email] Tip: Check your Gmail App Password")
        return False


def _update_icsr_queue(report_id, drug_name, meddra_pt,
                       check_result, status,
                       pdf_path=None, xml_path=None):
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT queue_id, report_id, drug_name, meddra_pt,
                   check_result, icsr_status, pdf_path, xml_path, created_at
            FROM icsr_queue ORDER BY created_at DESC
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