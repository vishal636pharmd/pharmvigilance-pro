# webapp/app.py — PVPro Complete (All Modules, Clean Version)
from flask import (Flask, render_template, request,
                   redirect, url_for, session, send_file, jsonify)
import sqlite3, re, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.bill_parser        import auto_detect_and_parse
from modules.patient_db         import (
    init_db, create_or_get_profile, get_profile_by_id,
    save_purchase, get_purchase_history,
    get_all_reminders_for_patient, get_due_reminders,
    mark_reminder_sent, set_reminder_date_to_today,
    save_symptom_report, save_no_symptom_report,
    get_symptom_reports_for_patient, update_meddra_term,
    get_unprocessed_reports, save_adr_assessment,
    get_all_assessments, update_assessment_status)
from modules.reminder_system    import run_daily_reminders
from modules.nlp_engine         import standardize_symptom, process_all_unprocessed
from modules.meddra_mapper      import get_meddra_hierarchy
from modules.confidence_scorer  import calculate_confidence
from modules.naranjo_calculator import calculate_naranjo, NARANJO_QUESTIONS
from modules.signal_detector    import calculate_prr, run_signal_scan
from modules.report_generator   import generate_report
from modules.ocr_scanner        import extract_text_from_image, parse_bill_from_text

app = Flask(__name__)
app.secret_key = "pvpro_secure_key_2026"

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database", "pvpro.db"
)

init_db()

try:
    from modules.lexicomp_checker import init_lexicomp_table
    from modules.auto_icsr_pipeline import run_full_pipeline, get_icsr_queue
    from modules.icsr_generator import generate_cioms_pdf, generate_e2b_xml
    init_lexicomp_table()
    print("[PVPro] OpenFDA module ready.")
except Exception as e:
    print(f"[PVPro] OpenFDA module warning: {e}")

try:
    from modules.push_notifications import (
        init_push_table, save_subscription,
        send_reminder_push, VAPID_PUBLIC_KEY)
    init_push_table()
    print("[PVPro] Push notifications ready.")
except Exception as e:
    print(f"[PVPro] Push notifications warning: {e}")

print("[PVPro] All systems ready.")


# ── HOME ──────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "patient_id" in session:
        profile = get_profile_by_id(session["patient_id"])
        if profile:
            return render_template("dashboard.html",
                profile=profile,
                history=get_purchase_history(session["patient_id"]),
                reminders=get_all_reminders_for_patient(session["patient_id"]),
                symptom_reports=get_symptom_reports_for_patient(
                    session["patient_id"]))
    return render_template("signup.html")


# ── MODULE 1: SIGNUP ──────────────────────────────────────────────────────────
@app.route("/signup", methods=["POST"])
def signup():
    full_name = request.form.get("full_name", "").strip()
    phone     = request.form.get("phone", "").strip()
    age       = request.form.get("age", "0").strip()
    gender    = request.form.get("gender", "").strip()

    if not full_name or not phone:
        return render_template("signup.html",
                               error="Please fill in name and phone.")
    if not re.match(r"^\d{10}$", phone):
        return render_template("signup.html",
                               error="Enter a valid 10-digit phone number.")
    if not age.isdigit():
        return render_template("signup.html",
                               error="Please enter a valid age.")
    age_int = int(age)
    if age_int < 1 or age_int > 120:
        return render_template("signup.html",
                               error="Age must be between 1 and 120.")

    pid = create_or_get_profile(full_name, age_int, gender, phone)
    session["patient_id"] = pid

    redirect_target = session.pop("redirect_after_signup", None)
    if redirect_target:
        return redirect(redirect_target)
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.pop("patient_id", None)
    return redirect(url_for("index"))


# ── MODULE 1: CAMERA OCR BILL SCANNER ────────────────────────────────────────
@app.route("/scan-bill")
def scan_bill():
    """Camera bill scanner — works for any pharmacy."""
    if "patient_id" not in session:
        return redirect(url_for("index"))
    return render_template("scan_bill.html")


@app.route("/scan-bill/process", methods=["POST"])
def scan_bill_process():
    """Receives photo → runs OCR → extracts medicines."""
    if "patient_id" not in session:
        return redirect(url_for("index"))

    image_data = request.form.get("image_data", "").strip()
    if not image_data:
        return render_template("scan_bill.html",
                               error="No image received. Please try again.")

    # Run OCR
    ocr_result = extract_text_from_image(image_data)

    if not ocr_result["success"]:
        return render_template("scan_bill.html",
                               error=(
                                   f"OCR not available on server: "
                                   f"{ocr_result['error']}. "
                                   f"Use the text paste method instead — "
                                   f"open your Apollo bill, "
                                   f"select all text, copy and paste at "
                                   f"/paste-bill-text"
                               ))

    ocr_text = ocr_result["text"]
    print(f"[Scan] OCR text preview: {ocr_text[:200]}")

    if not ocr_text or len(ocr_text.strip()) < 10:
        return render_template("scan_bill.html",
                               error=(
                                   "Could not read text from image. "
                                   "Tips: ensure good lighting, "
                                   "hold camera steady, make sure "
                                   "the medicine table row is clearly visible."
                               ))

    extracted = parse_bill_from_text(ocr_text)

    if not extracted.get("drugs"):
        # Show the raw OCR text so user can see what was read
        preview = ocr_text[:300].replace("<", "").replace(">", "")
        return render_template("scan_bill.html",
                               error=(
                                   f"Medicines not found in the scanned text. "
                                   f"Raw text detected: '{preview}...'. "
                                   f"Please retake with better lighting "
                                   f"or use text paste at /paste-bill-text"
                               ))

    pid     = session["patient_id"]
    profile = get_profile_by_id(pid)
    save_purchase(pid, extracted)

    return render_template("saved.html",
                           error=None,
                           drugs=extracted.get("drugs", []),
                           patient=profile,
                           bill_name_on_invoice=extracted.get(
                               "patient_name", "N/A"),
                           bill_date=extracted.get("bill_date", "N/A"))
@app.route("/scan-bill/process-text", methods=["POST"])
def scan_bill_process_text():
    """
    Receives OCR text extracted by Tesseract.js in the browser.
    Browser does the heavy OCR work — server just parses the text.
    No memory issues on Render free tier.
    """
    if "patient_id" not in session:
        return redirect(url_for("index"))

    ocr_text = request.form.get("ocr_text", "").strip()

    if not ocr_text or len(ocr_text) < 10:
        return render_template("scan_bill.html",
                               error="No text received from OCR. Please try again.")

    print(f"[Scan] Browser OCR text received: {len(ocr_text)} chars")
    print(f"[Scan] Preview: {ocr_text[:200]}")

    # Parse the OCR text
    extracted = parse_bill_from_text(ocr_text)

    if not extracted.get("drugs"):
        # Show what was read so user knows what went wrong
        preview = ocr_text[:200].replace("<","").replace(">","")
        return render_template("scan_bill.html",
                               error=(
                                   f"Medicines not found in scanned text. "
                                   f"Text detected: '{preview}'. "
                                   f"Try better lighting or use "
                                   f"'Add Bill by Text' instead."
                               ))

    pid     = session["patient_id"]
    profile = get_profile_by_id(pid)
    save_purchase(pid, extracted)

    return render_template("saved.html",
                           error=None,
                           drugs=extracted.get("drugs", []),
                           patient=profile,
                           bill_name_on_invoice=extracted.get(
                               "patient_name", "N/A"),
                           bill_date=extracted.get("bill_date", "N/A"))
# ── MODULE 1: ONE-CLICK DEMO BILL ─────────────────────────────────────────────
@app.route("/demo-bill-link")
def demo_bill_link():
    """One-click demo — simulates Apollo bill capture."""
    if "patient_id" not in session:
        session["redirect_after_signup"] = "/demo-bill-link"
        return redirect(url_for("index"))

    from datetime import datetime as _dt
    sample_html = f"""<html><body>
    <p>Name: VISHAL   Mobile: 9445571426</p>
    <p>Bill No: 16280WS0097250</p>
    <p>Bill Date: {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <table>
      <tr><td>Qty</td><td>PRODUCT NAME</td><td>SCH</td>
          <td>HSN CODE</td><td>MFRS</td><td>BATCH</td>
          <td>EXPIRY</td><td>MRP</td><td>AMOUNT</td><td>GST%</td></tr>
      <tr><td>15</td><td>IBUPROFEN 400MG TAB 15S</td><td>H</td>
          <td>30045090</td><td>ABBO</td><td>LBR26194</td>
          <td>Jan-28</td><td>164</td><td>2460</td><td>5.00</td></tr>
    </table>
    </body></html>"""

    extracted = auto_detect_and_parse(
        sample_html, "https://invoice.apollopharmacy.in/demo")
    pid     = session["patient_id"]
    profile = get_profile_by_id(pid)
    save_purchase(pid, extracted)

    return render_template("saved.html",
                           error=None,
                           drugs=extracted.get("drugs", []),
                           patient=profile,
                           bill_name_on_invoice=extracted.get(
                               "patient_name", "N/A"),
                           bill_date=extracted.get("bill_date", "N/A"))


# ── MODULE 2: REMINDERS ───────────────────────────────────────────────────────
@app.route("/reminders")
def check_reminders():
    fired = run_daily_reminders()
    return jsonify({"fired": len(fired), "items": fired,
                    "tip": "Use /demo-trigger-reminder/<drug_id> if 0 fired"})


@app.route("/my-reminders")
def my_reminders():
    if "patient_id" not in session:
        return redirect(url_for("index"))
    return jsonify({
        "reminders": get_all_reminders_for_patient(session["patient_id"])})


@app.route("/demo-trigger-reminder/<int:drug_id>")
def demo_trigger(drug_id):
    if "patient_id" not in session:
        return redirect(url_for("index"))
    set_reminder_date_to_today(drug_id)
    return jsonify({
        "status": f"drug_id={drug_id} set to today",
        "next": "Visit /reminders"})


# ── MODULE 3: SYMPTOM FORM ────────────────────────────────────────────────────
@app.route("/symptom")
def symptom_form():
    patient_id = (request.args.get("patient_id", type=int) or
                  session.get("patient_id"))
    drug_id    = request.args.get("drug_id", type=int)
    if not patient_id:
        return redirect(url_for("index"))
    profile = get_profile_by_id(patient_id)
    if not profile:
        return redirect(url_for("index"))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if drug_id:
        c.execute("""SELECT drug_id,drug_name,reminder_date
                     FROM purchase_drugs
                     WHERE drug_id=? AND patient_id=?""",
                  (drug_id, patient_id))
    else:
        c.execute("""SELECT drug_id,drug_name,reminder_date
                     FROM purchase_drugs WHERE patient_id=?
                     ORDER BY reminder_date ASC LIMIT 1""",
                  (patient_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return redirect(url_for("index"))
    return render_template("symptom_form.html", patient=profile,
                           drug={"drug_id": row[0], "drug_name": row[1],
                                 "reminder_date": row[2]})


@app.route("/symptom/submit", methods=["POST"])
def symptom_submit():
    patient_id       = request.form.get("patient_id", type=int)
    drug_id          = request.form.get("drug_id",    type=int)
    drug_name        = request.form.get("drug_name",  "Unknown")
    raw_symptom      = request.form.get("symptom_text", "").strip()
    severity         = request.form.get("severity", "Mild")
    timing_ok        = request.form.get("timing_ok",        "1") == "1"
    drug_stopped     = request.form.get("drug_stopped",     "0") == "1"
    symptom_improved = request.form.get("symptom_improved", "0") == "1"
    if not patient_id or not drug_id or not raw_symptom:
        return redirect(url_for("symptom_form"))
    report_id = save_symptom_report(
        patient_id, drug_id, drug_name, raw_symptom,
        severity, timing_ok, drug_stopped, symptom_improved)
    mark_reminder_sent(drug_id)
    result    = standardize_symptom(raw_symptom)
    hierarchy = get_meddra_hierarchy(result["meddra_pt"])
    update_meddra_term(report_id, result["meddra_pt"], hierarchy["soc"])
    return render_template("symptom_thankyou.html",
                           no_symptom=False, drug_name=drug_name,
                           symptom=raw_symptom,
                           meddra_pt=result["meddra_pt"],
                           severity=severity)


@app.route("/symptom/none", methods=["POST"])
def symptom_none():
    patient_id = request.form.get("patient_id", type=int)
    drug_id    = request.form.get("drug_id",    type=int)
    drug_name  = request.form.get("drug_name",  "Unknown")
    if patient_id and drug_id:
        save_no_symptom_report(patient_id, drug_id, drug_name)
        mark_reminder_sent(drug_id)
    return render_template("symptom_thankyou.html",
                           no_symptom=True, drug_name=drug_name,
                           symptom=None, meddra_pt=None, severity=None)


# ── MODULE 4: NLP ─────────────────────────────────────────────────────────────
@app.route("/nlp-process")
def nlp_process():
    processed = process_all_unprocessed()
    return jsonify({"processed": len(processed), "results": processed})


@app.route("/nlp-test")
def nlp_test():
    text      = request.args.get("text", "swollen feet")
    result    = standardize_symptom(text)
    hierarchy = get_meddra_hierarchy(result["meddra_pt"])
    return jsonify({"input": text, "meddra_pt": result["meddra_pt"],
                    "soc": hierarchy["soc"], "method": result["method"]})


# ── MODULE 5: CONFIDENCE + ADR ASSESSMENT ────────────────────────────────────
@app.route("/adr-assess/<int:report_id>")
def adr_assess(report_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT patient_id,drug_name,meddra_pt,severity,
                        timing_ok,symptom_improved
                 FROM symptom_reports WHERE report_id=?""", (report_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Report not found"})
    patient_id, drug_name, meddra_pt, severity, timing_ok, symptom_improved = row
    conf    = calculate_confidence(drug_name, meddra_pt or "",
                                   bool(timing_ok), bool(symptom_improved),
                                   severity or "Mild")
    answers = {f"Q{i}": "unknown" for i in range(1, 11)}
    answers["Q2"] = "yes" if timing_ok else "no"
    answers["Q3"] = "yes" if symptom_improved else "unknown"
    naranjo = calculate_naranjo(answers)
    aid     = save_adr_assessment(patient_id, drug_name, meddra_pt or "Unknown",
                                  conf["score"], naranjo["score"],
                                  naranjo["category"])
    return jsonify({"assessment_id": aid, "drug": drug_name,
                    "meddra_pt": meddra_pt, "confidence": conf,
                    "naranjo": naranjo,
                    "next": f"Visit /pharmacist to review #{aid}"})


# ── MODULE 6: PHARMACIST + NARANJO ───────────────────────────────────────────
@app.route("/pharmacist")
def pharmacist():
    return render_template("pharmacist.html",
                           assessments=get_all_assessments(),
                           naranjo_questions=NARANJO_QUESTIONS)


@app.route("/pharmacist/update/<int:assessment_id>", methods=["POST"])
def pharmacist_update(assessment_id):
    update_assessment_status(assessment_id,
                             request.form.get("status", "Pending"))
    return redirect(url_for("pharmacist"))


@app.route("/naranjo", methods=["GET", "POST"])
def naranjo_page():
    result = None
    if request.method == "POST":
        answers = {f"Q{i}": request.form.get(f"Q{i}", "unknown")
                   for i in range(1, 11)}
        result = calculate_naranjo(answers)
    return render_template("naranjo.html",
                           questions=NARANJO_QUESTIONS, result=result)


# ── MODULE 8: SIGNAL DETECTION ───────────────────────────────────────────────
@app.route("/signals")
def signals():
    drug = request.args.get("drug", "")
    pt   = request.args.get("pt",   "")
    if drug and pt:
        return jsonify(calculate_prr(drug, pt))
    return jsonify({"usage": "/signals?drug=Ibuprofen&pt=Nausea"})


@app.route("/signals/scan")
def signals_scan():
    found = run_signal_scan()
    return jsonify({"signals_found": len(found), "signals": found})


# ── MODULE 9: PDF REPORT ──────────────────────────────────────────────────────
@app.route("/report/<int:assessment_id>")
def download_report(assessment_id):
    filepath, error = generate_report(assessment_id)
    if error:
        return jsonify({"error": error, "tip": "pip install reportlab"})
    return send_file(filepath, as_attachment=True)


# ── MODULE 10: NOTIFICATIONS ──────────────────────────────────────────────────
@app.route("/notifications")
def notifications_page():
    from modules.patient_db import get_due_reminders
    from datetime import datetime
    due = get_due_reminders()
    return render_template("notification_demo.html",
                           reminders_due=due,
                           current_time=datetime.now().strftime("%I:%M %p"))


# ── MODULE 11: ICSR PIPELINE ──────────────────────────────────────────────────
@app.route("/check-adr/<int:report_id>")
def check_adr(report_id):
    try:
        result = run_full_pipeline(report_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/run-all-checks")
def run_all_checks():
    try:
        from modules.patient_db import get_unprocessed_reports
        reports = get_unprocessed_reports()
        if not reports:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            try:
                c.execute("""SELECT report_id FROM symptom_reports
                             WHERE raw_symptom != 'No symptoms'
                             ORDER BY report_date DESC LIMIT 20""")
                rows    = c.fetchall()
                reports = [{"report_id": r[0]} for r in rows]
            except:
                reports = []
            conn.close()
        results = []
        for report in reports:
            result = run_full_pipeline(report["report_id"])
            results.append({
                "report_id":    result.get("report_id"),
                "drug":         result.get("drug_name"),
                "meddra_pt":    result.get("meddra_pt"),
                "final_action": result.get("final_action"),
                "message":      result.get("message")
            })
        return jsonify({
            "total_checked":  len(results),
            "icsr_generated": sum(1 for r in results
                                  if r["final_action"] == "icsr_generated"),
            "no_icsr_needed": sum(1 for r in results
                                  if r["final_action"] == "no_icsr_needed"),
            "results": results
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/icsr-queue")
def icsr_queue_page():
    try:
        queue = get_icsr_queue()
    except:
        queue = []
    return render_template("icsr_queue.html", queue=queue)


@app.route("/icsr/download/pdf/<int:report_id>")
def download_icsr_pdf(report_id):
    try:
        filepath, error = generate_cioms_pdf(report_id)
        if error:
            return jsonify({"error": error})
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/icsr/download/xml/<int:report_id>")
def download_icsr_xml(report_id):
    try:
        filepath, error = generate_e2b_xml(report_id)
        if error:
            return jsonify({"error": error})
        return send_file(filepath, as_attachment=True,
                         mimetype="application/xml")
    except Exception as e:
        return jsonify({"error": str(e)})


# ── MODULE 12: PUSH NOTIFICATIONS ────────────────────────────────────────────
@app.route("/push/vapid-public-key")
def vapid_public_key():
    try:
        return jsonify({"publicKey": VAPID_PUBLIC_KEY})
    except:
        return jsonify({"publicKey": ""})


@app.route("/push/subscribe", methods=["POST"])
def push_subscribe():
    if "patient_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data              = request.get_json()
    subscription_json = json.dumps(data.get("subscription", {}))
    device_name       = request.headers.get("User-Agent", "Unknown")[:50]
    save_subscription(session["patient_id"], subscription_json, device_name)
    return jsonify({"status": "subscribed"})


@app.route("/push/test")
def push_test():
    if "patient_id" not in session:
        return jsonify({"error": "Not logged in"})
    try:
        from modules.push_notifications import send_push_to_patient
        profile = get_profile_by_id(session["patient_id"])
        sent    = send_push_to_patient(
            patient_id=session["patient_id"],
            title="PVPro — Test Notification",
            body=f"Hi {profile.get('full_name','')}, "
                 f"this is a real push notification from PVPro!",
            url="/"
        )
        return jsonify({
            "sent": sent,
            "message": ("Notification sent! Check your phone." if sent
                        else "Not sent — subscribe to notifications first.")
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# ── MISC ──────────────────────────────────────────────────────────────────────
@app.route("/my-symptoms")
def my_symptoms():
    if "patient_id" not in session:
        return redirect(url_for("index"))
    return jsonify({
        "reports": get_symptom_reports_for_patient(session["patient_id"])})


if __name__ == "__main__":
    print("=" * 50)
    print("  PharmVigilance Pro (PVPro)")
    print("  Running at: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5000)