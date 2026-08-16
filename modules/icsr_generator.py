# modules/icsr_generator.py
# PURPOSE: Generates ICSR reports in two formats:
#   1. CIOMS I PDF (standard paper report format)
#   2. E2B-style XML research export (for authorised AMC/MAH review)
#
# As a Pharm.D student, YOU are the reporter.
# No separate pharmacist needed — student reporters are valid in India.

import os
from datetime import datetime
from modules.patient_db import get_conn, q

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "reports", "generated_pdfs")


def get_report_data(report_id):
    """Fetches all data needed for ICSR from the database."""
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(q("""
            SELECT sr.report_id, sr.drug_name, sr.raw_symptom,
                   sr.meddra_pt, sr.meddra_soc, sr.severity,
                   sr.timing_ok, sr.drug_stopped, sr.symptom_improved,
                   sr.report_date,
                   pp.full_name, pp.age, pp.gender, pp.phone,
                   p.bill_date
            FROM symptom_reports sr
            JOIN patient_profile pp ON sr.patient_id = pp.patient_id
            JOIN purchase_drugs pd ON sr.drug_id = pd.drug_id
            JOIN purchases p ON pd.purchase_id = p.purchase_id
            WHERE sr.report_id = ?
        """), (report_id,))
        row = c.fetchone()
    except Exception as e:
        print(f"[ICSR] DB error: {e}")
        row = None
    conn.close()
    return row


def auto_confirm_by_score(report_id):
    """
    Auto-confirms an ADR report if confidence score >= 60
    and Naranjo category is Possible/Probable/Definite.
    Returns True if auto-confirmed.
    """
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(q("""
            SELECT confidence_score, naranjo_category
            FROM adr_assessments
            WHERE report_id = ? OR
            (SELECT drug_name FROM symptom_reports WHERE report_id=?) =
            drug_name
            ORDER BY assessment_id DESC LIMIT 1
        """), (report_id, report_id))
        row = c.fetchone()
        conn.close()
        if row:
            score, category = row
            if score >= 60 and category in ["Possible", "Probable", "Definite"]:
                return True
    except:
        conn.close()
    return False


def generate_cioms_pdf(report_id):
    """
    Generates a CIOMS I format PDF report.
    This is the standard international ADR reporting form.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                        Paragraph, Spacer)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
    except ImportError:
        return None, "reportlab not installed. Run: pip install reportlab"

    row = get_report_data(report_id)
    if not row:
        return None, "Report not found in database"

    (report_id, drug_name, raw_symptom, meddra_pt, meddra_soc, severity,
     timing_ok, drug_stopped, symptom_improved, report_date,
     full_name, age, gender, phone, bill_date) = row

    os.makedirs(OUT_DIR, exist_ok=True)
    filename = f"CIOMS_I_Report_{report_id}_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    filepath = os.path.join(OUT_DIR, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    story = []

    # ── HEADER ───────────────────────────────────────────────────────────
    header_style = ParagraphStyle("header", parent=styles["Heading1"],
                                   fontSize=13, spaceAfter=4)
    story.append(Paragraph("CIOMS I — INDIVIDUAL CASE SAFETY REPORT", header_style))
    story.append(Paragraph(
        f"Report ID: PVPRO-{report_id:04d}  |  "
        f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}  |  "
        f"Source: PharmVigilance Pro (Student Prototype)",
        styles["Normal"]))
    story.append(Spacer(1, 0.3*cm))

    # ── SECTION A: PATIENT INFORMATION ───────────────────────────────────
    story.append(Paragraph("A. PATIENT INFORMATION", styles["Heading2"]))
    patient_data = [
        ["Field", "Value"],
        ["Patient Identifier",  f"PVPRO-PT-{report_id:04d} (anonymized)"],
        ["Age",                 f"{age} years"],
        ["Gender",              gender or "Not specified"],
        ["Country",             "India"],
        ["Reporter Contact",    phone or "N/A"],
    ]
    t = Table(patient_data, colWidths=[5.5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND",  (0,1), (0,-1), colors.HexColor("#e8f0fe")),
        ("FONTNAME",    (0,1), (0,-1), "Helvetica-Bold"),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (1,1), (-1,-1),
         [colors.white, colors.HexColor("#f8f9fa")]),
        ("PADDING",     (0,0), (-1,-1), 6),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*cm))

    # ── SECTION B: SUSPECTED DRUG ─────────────────────────────────────────
    story.append(Paragraph("B. SUSPECTED DRUG(S)", styles["Heading2"]))
    drug_data = [
        ["Field", "Value"],
        ["Drug Name",            drug_name or "N/A"],
        ["Route of Administration", "Oral (assumed)"],
        ["Indication",           "As dispensed by pharmacy"],
        ["Start Date",           bill_date or "N/A"],
        ["Action Taken",         "Drug stopped" if drug_stopped else "Drug continued"],
    ]
    t2 = Table(drug_data, colWidths=[5.5*cm, 12*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND",  (0,1), (0,-1), colors.HexColor("#e8f0fe")),
        ("FONTNAME",    (0,1), (0,-1), "Helvetica-Bold"),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (1,1), (-1,-1),
         [colors.white, colors.HexColor("#f8f9fa")]),
        ("PADDING",     (0,0), (-1,-1), 6),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.3*cm))

    # ── SECTION C: ADVERSE REACTION ───────────────────────────────────────
    story.append(Paragraph("C. ADVERSE REACTION", styles["Heading2"]))
    adr_data = [
        ["Field", "Value"],
        ["Patient Description",     raw_symptom or "N/A"],
        ["MedDRA Preferred Term",   meddra_pt or "Pending NLP processing"],
        ["MedDRA System Organ Class", meddra_soc or "N/A"],
        ["Severity",                severity or "N/A"],
        ["Onset Date",              report_date[:10] if report_date else "N/A"],
        ["Timing (after drug start)", "Yes" if timing_ok else "No/Unknown"],
        ["Symptom improved on stopping", "Yes" if symptom_improved else "No/Unknown"],
        ["Outcome",                 "Resolved" if symptom_improved else "Ongoing/Unknown"],
    ]
    t3 = Table(adr_data, colWidths=[5.5*cm, 12*cm])
    t3.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND",  (0,1), (0,-1), colors.HexColor("#fff3e0")),
        ("FONTNAME",    (0,1), (0,-1), "Helvetica-Bold"),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (1,1), (-1,-1),
         [colors.white, colors.HexColor("#f8f9fa")]),
        ("PADDING",     (0,0), (-1,-1), 6),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
    ]))
    story.append(t3)
    story.append(Spacer(1, 0.3*cm))

    # ── SECTION D: REPORTER ───────────────────────────────────────────────
    story.append(Paragraph("D. REPORTER INFORMATION", styles["Heading2"]))
    reporter_data = [
        ["Field", "Value"],
        ["Reporter Name",       "Vishal Raj P"],
        ["Qualification",       "Pharm.D Student (Year 2)"],
        ["Institution",         "Pharmacy College, India"],
        ["Report Type",         "Spontaneous — Student Research Project"],
        ["Report Date",         datetime.now().strftime("%d %b %Y")],
        ["System",              "PharmVigilance Pro (PVPro) — Portfolio Project"],
    ]
    t4 = Table(reporter_data, colWidths=[5.5*cm, 12*cm])
    t4.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND",  (0,1), (0,-1), colors.HexColor("#e8f5e9")),
        ("FONTNAME",    (0,1), (0,-1), "Helvetica-Bold"),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (1,1), (-1,-1),
         [colors.white, colors.HexColor("#f8f9fa")]),
        ("PADDING",     (0,0), (-1,-1), 6),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
    ]))
    story.append(t4)
    story.append(Spacer(1, 0.3*cm))

    # ── FOOTER ────────────────────────────────────────────────────────────
    story.append(Paragraph(
        "DISCLAIMER: This report is generated by PharmVigilance Pro, a student "
        "pharmacovigilance portfolio project. It is not for clinical use. "
        "For actual ADR reporting, submit through PvPI VigiFlow: "
        "https://vigiflow.ipc.gov.in",
        styles["Italic"]))

    doc.build(story)
    print(f"[ICSR] CIOMS I PDF generated: {filepath}")
    return filepath, None


def generate_e2b_xml(report_id):
    """
    Generates an E2B-style XML research export.
    It is not a certified gateway submission and must be reviewed by an
    authorised AMC/MAH before any official regulatory submission.
    """
    row = get_report_data(report_id)
    if not row:
        return None, "Report not found"

    (report_id, drug_name, raw_symptom, meddra_pt, meddra_soc, severity,
     timing_ok, drug_stopped, symptom_improved, report_date,
     full_name, age, gender, phone, bill_date) = row

    os.makedirs(OUT_DIR, exist_ok=True)
    filename = f"E2B_R3_Report_{report_id}_{datetime.now().strftime('%Y%m%d%H%M')}.xml"
    filepath = os.path.join(OUT_DIR, filename)

    # Severity code mapping (ICH E2B standard codes)
    seriousness = "2"  # 1=Serious, 2=Non-serious
    if severity == "Severe":
        seriousness = "1"

    # Outcome code
    outcome = "6"  # Unknown
    if symptom_improved:
        outcome = "1"  # Recovered/Resolved

    now = datetime.now().strftime("%Y%m%d%H%M%S")
    bill_date_clean = (bill_date or "")[:10].replace("-", "")

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ichicsr lang="en">
  <ichicsrmessageheader>
    <messagetype>ichicsr</messagetype>
    <messageformatversion>2.1</messageformatversion>
    <messageformatrelease>2</messageformatrelease>
    <messagenumb>PVPRO-{report_id:04d}-{now}</messagenumb>
    <messagesenderidentifier>PVPRO-STUDENT</messagesenderidentifier>
    <messagereceiveridentifier>IN-IPC-PVPI</messagereceiveridentifier>
    <messagedateformat>204</messagedateformat>
    <messagedate>{now}</messagedate>
  </ichicsrmessageheader>

  <safetyreport>
    <safetyreportversion>1</safetyreportversion>
    <safetyreportid>PVPRO-{report_id:04d}</safetyreportid>
    <primarysourcecountry>IN</primarysourcecountry>
    <occurcountry>IN</occurcountry>
    <transmissiondateformat>102</transmissiondateformat>
    <transmissiondate>{datetime.now().strftime('%Y%m%d')}</transmissiondate>
    <reporttype>1</reporttype>
    <serious>{seriousness}</serious>
    <seriousnessdeath>2</seriousnessdeath>
    <seriousnesslifethreatening>2</seriousnesslifethreatening>
    <seriousnesshospitalization>2</seriousnesshospitalization>
    <seriousnessdisabling>2</seriousnessdisabling>
    <seriousnesscongenitalanomali>2</seriousnesscongenitalanomali>
    <seriousnessother>2</seriousnessother>
    <receivedateformat>102</receivedateformat>
    <receivedate>{datetime.now().strftime('%Y%m%d')}</receivedate>
    <receiptdateformat>102</receiptdateformat>
    <receiptdate>{datetime.now().strftime('%Y%m%d')}</receiptdate>
    <additionaldocument>2</additionaldocument>
    <fulfillexpeditecriteria>2</fulfillexpeditecriteria>
    <companynumb>PVPRO-{report_id:04d}</companynumb>
    <medicallyconfirm>1</medicallyconfirm>

    <primarysource>
      <reportertitle>Mr</reportertitle>
      <reportergivename>Vishal Raj</reportergivename>
      <reporterfamilyname>P</reporterfamilyname>
      <reporterorganization>Pharmacy College India</reporterorganization>
      <reportercountry>IN</reportercountry>
      <qualification>3</qualification>
    </primarysource>

    <sender>
      <sendertype>2</sendertype>
      <senderorganization>PharmVigilance Pro Student Project</senderorganization>
      <senderfamilyname>PVPro</senderfamilyname>
      <sendergivename>System</sendergivename>
      <sendercountrycode>IN</sendercountrycode>
    </sender>

    <receiver>
      <receivertype>2</receivertype>
      <receiverorganization>PvPI - Pharmacovigilance Programme of India</receiverorganization>
      <receivercountrycode>IN</receivercountrycode>
    </receiver>

    <patient>
      <patientinitial>PVPRO-PT-{report_id:04d}</patientinitial>
      <patientonsetage>{age}</patientonsetage>
      <patientonsetageunit>801</patientonsetageunit>
      <patientsex>{'1' if gender == 'Male' else '2' if gender == 'Female' else '0'}</patientsex>

      <drug>
        <drugcharacterization>1</drugcharacterization>
        <medicinalproduct>{drug_name}</medicinalproduct>
        <drugstartdateformat>102</drugstartdateformat>
        <drugstartdate>{bill_date_clean or datetime.now().strftime('%Y%m%d')}</drugstartdate>
        <drugindication>As dispensed</drugindication>
        <drugadministrationroute>048</drugadministrationroute>
        <drugactiondrug>{'1' if drug_stopped else '6'}</drugactiondrug>
      </drug>

      <reaction>
        <primarysourcereaction>{raw_symptom}</primarysourcereaction>
        <reactionmeddraversionllt>26.0</reactionmeddraversionllt>
        <reactionmeddrallt>{meddra_pt or raw_symptom}</reactionmeddrallt>
        <reactionstartdateformat>102</reactionstartdateformat>
        <reactionstartdate>{(report_date or "")[:10].replace("-","")}</reactionstartdate>
        <reactionoutcome>{outcome}</reactionoutcome>
      </reaction>

      <summary>
        <narrativeincludeclinical>Patient reported: {raw_symptom}. 
MedDRA PT: {meddra_pt or "Pending"}. 
Severity: {severity}. 
Symptom appeared after drug: {'Yes' if timing_ok else 'Unknown'}. 
Drug stopped: {'Yes' if drug_stopped else 'No'}. 
Symptom improved on stopping: {'Yes' if symptom_improved else 'Unknown'}.
Report generated by PharmVigilance Pro (Student PV Project, India).</narrativeincludeclinical>
      </summary>
    </patient>
  </safetyreport>
</ichicsr>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"[ICSR] E2B(R3) XML generated: {filepath}")
    return filepath, None
