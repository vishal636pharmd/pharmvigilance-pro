# modules/ocr_scanner.py
import re
import os
import base64
import io

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database", "pvpro.db"
)


def extract_text_from_image(image_data):
    """Server-side OCR fallback (not used in browser-OCR mode)."""
    return {"success": False, "text": "",
            "error": "Using browser-side OCR instead"}


def parse_bill_from_text(ocr_text):
    """
    Parses OCR text from any pharmacy bill.
    Handles Apollo format: PARACIP 500MG TAB 10'S
    Also handles MedPlus and generic pharmacy bills.
    """
    data = {
        "patient_name": None,
        "invoice_no":   None,
        "bill_date":    None,
        "drugs":        [],
        "source":       "Camera OCR"
    }

    lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
    print(f"[OCR Parser] Processing {len(lines)} lines")
    print(f"[OCR Parser] Full text preview:\n{ocr_text[:500]}")

    # ── Patient name ──────────────────────────────────────────────────────
    for line in lines:
        m = re.search(
            r"(?:Name|Patient|Pt\.?|Customer)\s*[:\-]\s*([A-Za-z][A-Za-z\s]{1,25})",
            line, re.I
        )
        if m:
            name = m.group(1).strip()
            name = re.sub(
                r"\s+(Mobile|Phone|No|Bill|Date|Mr|Mrs|Dr)\b.*",
                "", name, flags=re.I
            ).strip()
            if 2 <= len(name) <= 25:
                data["patient_name"] = name
                break

    # ── Bill number ───────────────────────────────────────────────────────
    for line in lines:
        m = re.search(
            r"(?:Bill|Invoice|Receipt)\s*(?:No|#)\.?\s*[:\-]?\s*"
            r"([A-Z0-9][A-Z0-9\-]{3,20})",
            line, re.I
        )
        if m:
            data["invoice_no"] = m.group(1).strip()
            break

    # ── Bill date ─────────────────────────────────────────────────────────
    for line in lines:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if m:
            data["bill_date"] = m.group(1)
            break
        m = re.search(r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})", line)
        if m:
            data["bill_date"] = m.group(1)
            break

    # ── Drug extraction ───────────────────────────────────────────────────
    drugs = []
    seen  = set()

    # Words that appear in header rows — skip these lines
    SKIP_WORDS = [
        "PRODUCT NAME", "ITEM NAME", "MEDICINE NAME", "DESCRIPTION",
        "HSN CODE", "BATCH NO", "EXPIRY", "TOTAL AMOUNT", "TAXABLE",
        "INVOICE", "APOLLO", "MEDPLUS", "PHARMACY", "REGISTERED",
        "THANK YOU", "TERMS", "SGST", "CGST", "GST%", "COSTY",
        "MFRS", "BATCH", "SCH", "QTY", "MRP", "AMOUNT"
    ]

    for line in lines:
        line_upper = line.upper()

        # Skip header/footer lines
        if any(word in line_upper for word in SKIP_WORDS):
            continue
        if len(line) < 5:
            continue

        # PATTERN 1: Apollo format
        # "10   PARACIP 500MG TAB 10'S   H   30049069   CIPL   ..."
        # Qty at start, drug name with dosage
        m = re.match(
            r"^(\d{1,3})\s+([A-Z][A-Z0-9\s\-\.\'\/]+?"
            r"\d+\.?\d*\s*(?:MG|MCG|ML|G|IU|MG/ML)"
            r"[A-Z0-9\s\'\.]*?)\s{2,}",
            line_upper + "  "
        )
        if m:
            qty       = m.group(1)
            drug_name = m.group(2).strip()
            # Get MRP — look for price pattern near end
            mrp = "N/A"
            prices = re.findall(r"\d+\.\d{2}", line)
            if prices:
                mrp = prices[0]  # first price is usually MRP
            drug_name = re.sub(r"\s+", " ", drug_name).strip()
            if len(drug_name) > 4 and drug_name.lower() not in seen:
                seen.add(drug_name.lower())
                drugs.append({
                    "drug_name": drug_name.title(),
                    "quantity":  qty,
                    "price":     mrp
                })
                print(f"[OCR Parser] P1 found: {drug_name} | {qty} | {mrp}")
                continue

        # PATTERN 2: Drug name anywhere in line with dosage
        # Catches "PARACIP 500MG TAB 10'S" even without qty prefix
        m = re.search(
            r"([A-Z][A-Z0-9]{2,}"
            r"(?:\s+[A-Z0-9\'\.]+){0,5}"
            r"\s+\d+\.?\d*\s*(?:MG|MCG|ML|G|IU)"
            r"(?:\s+[A-Z0-9\'\.]+){0,4})",
            line_upper
        )
        if m:
            drug_name = m.group(1).strip()
            drug_name = re.sub(r"\s+", " ", drug_name)
            # Remove trailing single letters (OCR artifacts)
            drug_name = re.sub(r"\s+[A-Z]\s*$", "", drug_name).strip()

            if (len(drug_name) > 5 and
                    drug_name.lower() not in seen and
                    not any(skip in drug_name for skip in
                            ["INVOICE", "APOLLO", "PHARMACY", "REGISTERED"])):
                seen.add(drug_name.lower())
                mrp = "N/A"
                prices = re.findall(r"\d+\.\d{2}", line)
                if prices:
                    mrp = prices[0]
                # Try to find qty
                qty = "N/A"
                qty_m = re.match(r"^(\d{1,3})\s", line.strip())
                if qty_m:
                    qty = qty_m.group(1)

                drugs.append({
                    "drug_name": drug_name.title(),
                    "quantity":  qty,
                    "price":     mrp
                })
                print(f"[OCR Parser] P2 found: {drug_name} | {qty} | {mrp}")

    # PATTERN 3: Final fallback — very flexible, catches anything
    # with a dosage number
    if not drugs:
        print("[OCR Parser] Trying fallback pattern...")
        fallback = re.compile(
            r"([A-Z][A-Z]+\s+\d+\s*(?:MG|MCG|ML|G|IU)"
            r"(?:\s+[A-Z0-9\'\.]+){0,3})",
            re.I
        )
        for line in lines:
            for m in fallback.finditer(line.upper()):
                drug_name = re.sub(r"\s+", " ", m.group(1)).strip()
                if (len(drug_name) > 4 and
                        drug_name.lower() not in seen):
                    seen.add(drug_name.lower())
                    drugs.append({
                        "drug_name": drug_name.title(),
                        "quantity":  "N/A",
                        "price":     "N/A"
                    })
                    print(f"[OCR Parser] Fallback found: {drug_name}")

    data["drugs"] = drugs
    print(f"[OCR Parser] Total drugs: {len(drugs)}")
    return data