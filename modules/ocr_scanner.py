# modules/ocr_scanner.py
import re
import os

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database", "pvpro.db"
)


def extract_text_from_image(image_data):
    """Not used — browser handles OCR via Tesseract.js"""
    return {"success": False, "text": "",
            "error": "Browser-side OCR used"}


def parse_bill_from_text(ocr_text):
    """
    Parses OCR text from Apollo, MedPlus, or any Indian pharmacy bill.
    Handles both portrait and landscape bill formats.
    """
    data = {
        "patient_name": None,
        "invoice_no":   None,
        "bill_date":    None,
        "drugs":        [],
        "source":       "Camera OCR"
    }

    # Normalize spacing
    text = re.sub(r"[ \t]+", " ", ocr_text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    print(f"[OCR] {len(lines)} lines received")
    for i, l in enumerate(lines[:40]):
        print(f"  [{i:02d}] {l}")

    # ── Patient name ──────────────────────────────────────────────────────
    for line in lines:
        m = re.search(
            r"(?:Patient\s*Name|Name)\s*[:\-\.]\s*([A-Za-z][A-Za-z\s]{1,20})",
            line, re.I
        )
        if m:
            name = m.group(1).strip()
            name = re.sub(
                r"\s+(Age|Gender|Cust|Mobile|Phone|Bill|Date|Ref)\b.*",
                "", name, flags=re.I
            ).strip()
            if 2 <= len(name) <= 20 and re.search(r"[A-Za-z]{2}", name):
                data["patient_name"] = name
                print(f"[OCR] Patient: {name}")
                break

    # ── Bill/Invoice number ───────────────────────────────────────────────
    for line in lines:
        m = re.search(
            r"(?:Bill|Invoice|Serial\s*Invoice)\s*No\.?\s*[:\-]?\s*"
            r"([A-Z0-9]{6,})",
            line, re.I
        )
        if m:
            data["invoice_no"] = m.group(1)
            break

    # ── Date ─────────────────────────────────────────────────────────────
    for line in lines:
        m = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4})", line)
        if m:
            data["bill_date"] = m.group(1)
            break
        m = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", line)
        if m:
            data["bill_date"] = m.group(1)
            break

    # ── Drug extraction — tries 4 different strategies ────────────────────
    drugs = _extract_drugs(lines)
    data["drugs"] = drugs
    print(f"[OCR] Total drugs: {len(drugs)}")
    return data


def _extract_drugs(lines):
    """
    Tries multiple extraction strategies in order of reliability.
    Stops as soon as any strategy finds drugs.
    """
    drugs = []

    # Strategy 1: MedPlus format
    # Line: "1 OKACET TAB 5 1.80 9.00"
    # Starts with serial number, then drug name, then qty and price
    drugs = _strategy_medplus(lines)
    if drugs:
        print(f"[OCR] Strategy 1 (MedPlus) found {len(drugs)}")
        return drugs

    # Strategy 2: Apollo format
    # Line: "15 DOLO 500MG TAB 15'S H 30049069 MIER BGA50375 2028-Nov H 0.94"
    # Starts with qty, then drug name, then HSN code (8 digits)
    drugs = _strategy_apollo(lines)
    if drugs:
        print(f"[OCR] Strategy 2 (Apollo) found {len(drugs)}")
        return drugs

    # Strategy 3: Any line with known drug form words
    # Catches "OKACET TAB", "DOLO 500MG", "PARACIP 500MG TAB" etc
    drugs = _strategy_form_words(lines)
    if drugs:
        print(f"[OCR] Strategy 3 (form words) found {len(drugs)}")
        return drugs

    # Strategy 4: Any line with dosage pattern (MG, ML, etc)
    drugs = _strategy_dosage(lines)
    if drugs:
        print(f"[OCR] Strategy 4 (dosage) found {len(drugs)}")
        return drugs

    print("[OCR] All strategies failed — no drugs found")
    return []


SKIP_WORDS = [
    "MEDPLUS", "APOLLO", "PHARMACY", "PHARMACIES",
    "REGISTERED OFFICE", "ADMIN OFFICE", "GROUND FLOOR",
    "TAX INVOICE", "RETAIL INVOICE", "SERIAL INVOICE",
    "PATIENT NAME", "CUSTID", "DR.NAME", "DR NAME",
    "SNO DESCRIPTION", "DESCRIPTION OF GOODS",
    "HSN SCH BATCH", "EXP MRP", "TAXVAL CGST",
    "MANUFACTURER", "TOTAL", "DISCOUNT", "NET TOTAL",
    "AMOUNT SAVED", "PAYMENT", "NINE RUPEES", "RUPEES",
    "SGST", "CGST", "CESS", "FSSAI", "GSTIN",
    "STATE CODE", "STORE ID", "PHONE",
    "INVOICE NO", "BILL NO", "DATE",
    "INSULINS", "VACCINES", "GOODS ONCE SOLD",
    "E & O.E", "FOR APOLLO", "FOR MEDPLUS",
    "QTY ITEM NAME", "QTY  ITEM", "SNU DESCRIPTION",
]


def _should_skip(line):
    lu = line.upper()
    return any(skip in lu for skip in SKIP_WORDS)


def _strategy_medplus(lines):
    """
    MedPlus format:
    Line N:   '1 OKACET TAB 5 1.80 9.00'
    Starts with a 1-2 digit serial number followed by drug name.
    """
    drugs = []
    seen = set()

    for line in lines:
        if _should_skip(line):
            continue

        # Must start with serial number (1-2 digits)
        m = re.match(r"^(\d{1,2})\s+([A-Z][A-Z0-9\s\-\'\.]+)", line.upper())
        if not m:
            continue

        serial = m.group(1)
        rest = m.group(2).strip()

        # Drug name must contain a known form word to be valid
        FORMS = r"\b(TAB|CAP|SYP|INJ|GEL|CRM|CREAM|TABLET|CAPSULE|SYRUP|DROPS|OINT)\b"
        if not re.search(FORMS, rest, re.I):
            continue

        # Extract drug name — up to the qty number
        # e.g. "OKACET TAB 5 1.80 9.00" → drug = "OKACET TAB"
        name_m = re.match(
            r"([A-Z][A-Z0-9\s\-\'\.]*?"
            r"(?:TAB|CAP|SYP|INJ|GEL|CREAM|TABLET|CAPSULE|SYRUP|DROPS|OINT))"
            r"\s+(\d+)\s+(\d+\.\d{2})",
            rest, re.I
        )
        if name_m:
            drug_name = name_m.group(1).strip()
            qty = name_m.group(2)
            mrp = name_m.group(3)
        else:
            # Simpler: take everything before first standalone number
            parts = re.split(r"\s+\d+\s+\d+\.\d{2}", rest)
            drug_name = parts[0].strip()
            qty = "N/A"
            prices = re.findall(r"\d+\.\d{2}", line)
            mrp = prices[0] if prices else "N/A"

        drug_name = re.sub(r"\s+", " ", drug_name).strip()

        if len(drug_name) > 2 and drug_name.lower() not in seen:
            seen.add(drug_name.lower())
            drugs.append({
                "drug_name": drug_name,
                "quantity": qty,
                "price": mrp
            })
            print(f"[MedPlus] {drug_name} | {qty} | {mrp}")

    return drugs


def _strategy_apollo(lines):
    """
    Apollo format:
    Line: '15 DOLO 500MG TAB 15'S H 30049069 MIER BGA50375 2028-Nov H 0.94'
    Starts with qty, drug name contains dosage (500MG), followed by HSN code.
    """
    drugs = []
    seen = set()

    for line in lines:
        if _should_skip(line):
            continue

        lu = line.upper()

        # Must have a dosage unit
        if not re.search(r"\d+\s*(?:MG|MCG|ML|G|IU)\b", lu):
            continue

        m = re.match(r"^(\d{1,3})\s+(.+)", line.strip())
        qty = "N/A"
        rest = line.strip()
        if m:
            qty = m.group(1)
            rest = m.group(2).strip()

        # Find drug name — ends at HSN code (8 digits) or double space
        drug_m = re.match(
            r"([A-Z][A-Z0-9\s\-\'\.]+?\d+\.?\d*\s*(?:MG|MCG|ML|G|IU)"
            r"(?:\s+[A-Z0-9\'\.]+){0,5}?)\s+(?:[A-Z]\s+)?\d{8}",
            rest.upper()
        )
        if drug_m:
            drug_name = drug_m.group(1).strip()
        else:
            parts = re.split(r"\s{2,}|\t", rest)
            drug_name = parts[0].strip()
            drug_name_m = re.match(
                r"([A-Z][A-Z0-9\s\-\'\.]+?\d+\.?\d*\s*(?:MG|MCG|ML|G|IU)"
                r"(?:\s+[A-Z0-9\'\.]+){0,4})",
                drug_name.upper()
            )
            if drug_name_m:
                drug_name = drug_name_m.group(1).strip()

        drug_name = re.sub(r"\s+", " ", drug_name).strip()

        if not re.search(r"[A-Za-z]{2,}", drug_name):
            continue
        if not re.search(r"\d+\s*(?:MG|MCG|ML|G|IU)", drug_name, re.I):
            continue

        prices = re.findall(r"\b\d+\.\d{2}\b", line)
        mrp = prices[0] if prices else "N/A"

        if len(drug_name) > 3 and drug_name.lower() not in seen:
            seen.add(drug_name.lower())
            drugs.append({
                "drug_name": drug_name,
                "quantity": qty,
                "price": mrp
            })
            print(f"[Apollo] {drug_name} | {qty} | {mrp}")

    return drugs


def _strategy_form_words(lines):
    """
    Finds lines containing drug form words: TAB, CAP, SYP, INJ etc.
    Works when qty and dosage format is unknown.
    """
    drugs = []
    seen = set()
    FORMS = r"\b(TAB|CAP|SYP|INJ|GEL|OINT|CREAM|TABLET|CAPSULE|SYRUP)\b"

    for line in lines:
        if _should_skip(line):
            continue
        lu = line.upper()
        if not re.search(FORMS, lu):
            continue

        m = re.search(
            r"([A-Z][A-Z0-9\-\'\.]+(?:\s+[A-Z0-9\-\'\.]+){0,4}"
            r"\s+(?:TAB|CAP|SYP|INJ|GEL|OINT|CREAM|TABLET|CAPSULE|SYRUP)"
            r"(?:\s+[A-Z0-9\'\.]+){0,3})",
            lu
        )
        if m:
            drug_name = re.sub(r"\s+", " ", m.group(1)).strip()
            FALSE_POS = ["ITEM NAME", "DESCRIPTION", "APOLLO PHARM",
                         "MEDPLUS", "REGISTERED", "INVOICE"]
            if any(fp in drug_name for fp in FALSE_POS):
                continue
            if len(drug_name) > 3 and drug_name.lower() not in seen:
                seen.add(drug_name.lower())
                qty_m = re.match(r"^(\d{1,3})\s", line.strip())
                qty = qty_m.group(1) if qty_m else "N/A"
                prices = re.findall(r"\b\d+\.\d{2}\b", line)
                mrp = prices[0] if prices else "N/A"
                drugs.append({
                    "drug_name": drug_name.title(),
                    "quantity": qty,
                    "price": mrp
                })
                print(f"[Forms] {drug_name} | {qty} | {mrp}")

    return drugs


def _strategy_dosage(lines):
    """
    Last resort: any line with a dosage number (500MG, 10ML etc).
    """
    drugs = []
    seen = set()

    for line in lines:
        if _should_skip(line):
            continue
        lu = line.upper()
        if not re.search(r"\d+\s*(?:MG|MCG|ML|G|IU)\b", lu):
            continue

        m = re.search(
            r"([A-Z][A-Z]{2,}(?:\s+[A-Z0-9\'\.]+){0,3}"
            r"\s+\d+\.?\d*\s*(?:MG|MCG|ML|G|IU)"
            r"(?:\s+[A-Z0-9\'\.]+){0,3})",
            lu
        )
        if m:
            drug_name = re.sub(r"\s+", " ", m.group(1)).strip()
            if len(drug_name) > 4 and drug_name.lower() not in seen:
                seen.add(drug_name.lower())
                prices = re.findall(r"\b\d+\.\d{2}\b", line)
                mrp = prices[0] if prices else "N/A"
                qty_m = re.match(r"^(\d{1,3})\s", line.strip())
                qty = qty_m.group(1) if qty_m else "N/A"
                drugs.append({
                    "drug_name": drug_name.title(),
                    "quantity": qty,
                    "price": mrp
                })
                print(f"[Dosage] {drug_name} | {qty} | {mrp}")

    return drugs