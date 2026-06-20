# modules/report_generator.py
# MODULE 9: Generates CIOMS I-style ADR report PDF
import os, sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "reports", "generated_pdfs")


def generate_report(assessment_id):
    """
    Generates PDF for a confirmed ADR assessment.
    Returns (filepath, None) on success or (None, error_message) on failure.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
    except ImportError:
        return None, "reportlab not installed. Run: pip install reportlab"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""SELECT a.drug_name,a.meddra_pt,a.naranjo_score,a.naranjo_category,
                            a.confidence_score,a.pharmacist_status,a.review_date,
                            pp.full_name,pp.age,pp.gender,pp.phone
                     FROM adr_assessments a
                     JOIN patient_profile pp ON a.patient_id=pp.patient_id
                     WHERE a.assessment_id=?""", (assessment_id,))
        row = c.fetchone()
    except:
        row = None
    conn.close()

    if not row:
        return None, "Assessment not found"

    drug, pt, naranjo_score, naranjo_cat, conf, status, review_date, name, age, gender, phone = row

    os.makedirs(OUT_DIR, exist_ok=True)
    filepath = os.path.join(OUT_DIR, f"ADR_Report_{assessment_id}_{datetime.now().strftime('%Y%m%d')}.pdf")

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("ADVERSE DRUG REACTION REPORT", styles["Heading1"]))
    story.append(Paragraph("CIOMS I Format — PharmVigilance Pro (Student Prototype)", styles["Normal"]))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph("SECTION A — PATIENT INFORMATION", styles["Heading2"]))

    t1 = Table([
        ["Patient Name",    name or "N/A"],
        ["Age / Gender",    f"{age} years / {gender}"],
        ["Phone",           phone or "N/A"],
    ], colWidths=[5*cm, 12*cm])
    t1.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(0,-1), colors.HexColor("#1e40af")),
        ("TEXTCOLOR",   (0,0),(0,-1), colors.white),
        ("FONTNAME",    (0,0),(0,-1), "Helvetica-Bold"),
        ("BACKGROUND",  (1,0),(1,-1), colors.HexColor("#f0f4ff")),
        ("GRID",        (0,0),(-1,-1), 0.5, colors.grey),
        ("PADDING",     (0,0),(-1,-1), 6),
    ]))
    story.append(t1)
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph("SECTION B — ADR DETAILS", styles["Heading2"]))

    t2 = Table([
        ["Suspected Drug",          drug or "N/A"],
        ["Adverse Event (MedDRA PT)", pt or "N/A"],
        ["Naranjo Score",           f"{naranjo_score} — {naranjo_cat}"],
        ["Confidence Score",        f"{conf}/100"],
        ["Pharmacist Status",       status or "Pending"],
        ["Review Date",             review_date or "N/A"],
    ], colWidths=[5*cm, 12*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(0,-1), colors.HexColor("#0f172a")),
        ("TEXTCOLOR",   (0,0),(0,-1), colors.white),
        ("FONTNAME",    (0,0),(0,-1), "Helvetica-Bold"),
        ("BACKGROUND",  (1,0),(1,-1), colors.HexColor("#fefce8")),
        ("GRID",        (0,0),(-1,-1), 0.5, colors.grey),
        ("PADDING",     (0,0),(-1,-1), 6),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')} | "
        "PVPro Student Prototype | Not for clinical use",
        styles["Normal"]))
    doc.build(story)
    return filepath, None