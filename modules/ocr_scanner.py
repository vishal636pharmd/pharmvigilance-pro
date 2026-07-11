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
            "error": "Browser-side OCR used instead"}


def parse_bill_from_text(ocr_text):
    """
    Parses OCR text from any pharmacy bill.
    Flexible enough to handle OCR imperfections like:
    - Extra spaces between characters
    - Mixed case from OCR
    - Missing or extra characters
    """
    data = {
        "patient_name": None,
        "invoice_no":   None,
        "bill_date":    None,
        "drugs":        [],
        "source":       "Camera OCR"
    }

    # Normalize text — collapse multiple spaces
    ocr_text_clean = re.sub(r"[ \t]+", " ", ocr_text)
    lines = [l.strip() for l in ocr_text_clean.split("\n") if l.strip()]

    print(f"[OCR Parser] {len(lines)} lines")
    for i, line in enumerate(lines[:30]):
        print(f"  L{i:02d}: {line}")

    # ── Patient name ──────────────────────────────────────────────────────
    for line in lines:
        m = re.search(
            r"(?:Name|Patient|Customer)\s*[:\-\.]\s*([A-Za-z][A-Za-z\s]{1,20})",
            line, re.I
        )
        if m:
            name = m.group(1).strip()
            name = re.sub(
                r"\s+(Mobile|Phone|Bill|Date|Ref|No|TID)\b.*",
                "", name, flags=re.I
            ).strip()
            if 2 <= len(name) <= 20:
                data["patient_name"] = name
                print(f"[OCR Parser] Patient: {name}")
                break

    # ── Bill number ───────────────────────────────────────────────────────
    for line in lines:
        m = re.search(
            r"Bill\s*No\.?\s*[:\-]?\s*([A-Z0-9]{4,})",
            line, re.I
        )
        if m:
            data["invoice_no"] = m.group(1).strip()
            break

    # ── Bill date ─────────────────────────────────────────────────────────
    for line in lines:
        m = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", line)
        if m:
            data["bill_date"] = m.group(1)
            break
        m = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4})", line)
        if m:
            data["bill_date"] = m.group(1)
            break

    # ── Drug extraction ───────────────────────────────────────────────────
    drugs = []
    seen  = set()

    # Lines to skip — these are headers/footers not medicines
    SKIP_PATTERNS = [
        r"QTY\s+ITEM", r"PRODUCT\s+NAME", r"HSN\s+CODE",
        r"BATCH\s+NO", r"EXPIRY", r"TOTAL\s+AMOUNT",
        r"TAXABLE", r"APOLLO\s+PHARM", r"REGISTERED\s+OFFICE",
        r"DONATION", r"QR\s+CODE", r"GST\s+RATE",
        r"SGST", r"CGST", r"THANK\s+YOU",
        r"^\s*INVOICE\s*$",
    ]

    # Dosage units — a line must have one of these to be a drug
    DOSE_UNITS = r"(?:MG|MCG|ML|G|IU|MG/ML|MCG/ML)"

    for line in lines:
        lu = line.upper()

        # Skip obvious non-drug lines
        skip = False
        for pat in SKIP_PATTERNS:
            if re.search(pat, lu):
                skip = True
                break
        if skip:
            continue

        if len(line) < 6:
            continue

        # Must contain a dosage unit to be a medicine line
        if not re.search(DOSE_UNITS, lu):
            continue

        # ── Strategy 1: Qty at start of line ─────────────────────────────
        # Example: "10 PARACIP 500MG TAB 10'S H 30049069 CIPL..."
        # or with OCR artifacts: "10 PARAC IP 500MG TAB 10 S..."
        qty_match = re.match(r"^(\d{1,3})\s+(.+)", line.strip())
        if qty_match:
            qty  = qty_match.group(1)
            rest = qty_match.group(2).strip()

            # Find the drug name: starts at beginning,
            # ends at first 8-digit HSN code or double space
            # Try to find drug name ending at HSN code
            drug_match = re.match(
                r"(.+?\d+\.?\d*\s*(?:MG|MCG|ML|G|IU)"
                r"(?:\s+[A-Z0-9\'\.]+){0,5}?)"
                r"\s+(?:[A-Z]\s+)?\d{8}",
                rest, re.I
            )
            if drug_match:
                drug_name = drug_match.group(1).strip()
            else:
                # No HSN code found — take text up to first multi-space
                parts = re.split(r"\s{2,}", rest)
                drug_name = parts[0].strip()

            # Clean the drug name
            drug_name = re.sub(r"\s+", " ", drug_name).strip()

            # Must have letters and a dosage number
            if (re.search(r"[A-Za-z]{2,}", drug_name) and
                    re.search(DOSE_UNITS, drug_name, re.I) and
                    len(drug_name) > 4):
                drug_key = drug_name.lower()
                if drug_key not in seen:
                    seen.add(drug_key)
                    # Find price (decimal numbers near end of line)
                    prices = re.findall(r"\b\d+\.\d{2}\b", line)
                    mrp = prices[0] if prices else "N/A"
                    drugs.append({
                        "drug_name": drug_name,
                        "quantity":  qty,
                        "price":     mrp
                    })
                    print(f"[OCR P1] {drug_name} | Qty:{qty} | MRP:{mrp}")
                    continue

        # ── Strategy 2: Find drug name anywhere in line ───────────────────
        # For lines where qty might be missing or OCR merged it
        drug_match = re.search(
            r"([A-Z][A-Z]{2,}"           # starts with 3+ letters
            r"(?:\s*[A-Z0-9\'\.]+){0,4}" # optional words/numbers
            r"\s+\d+\.?\d*\s*"           # space + number
            r"(?:MG|MCG|ML|G|IU)"        # dosage unit
            r"(?:\s+[A-Z0-9\'\.]+){0,4})", # optional suffix like TAB 10'S
            lu
        )
        if drug_match:
            drug_name = drug_match.group(1).strip()
            drug_name = re.sub(r"\s+", " ", drug_name).strip()

            # Filter out false positives
            FALSE_POSITIVES = [
                "ITEM NAME", "HSN CODE", "APOLLO PHARM",
                "MEDPLUS", "REGISTERED", "INVOICE"
            ]
            if any(fp in drug_name for fp in FALSE_POSITIVES):
                continue

            if (len(drug_name) > 4 and
                    drug_name.lower() not in seen):
                seen.add(drug_name.lower())
                prices = re.findall(r"\b\d+\.\d{2}\b", line)
                mrp = prices[0] if prices else "N/A"
                qty_m = re.match(r"^(\d{1,3})\s", line.strip())
                qty = qty_m.group(1) if qty_m else "N/A"
                drugs.append({
                    "drug_name": drug_name.title(),
                    "quantity":  qty,
                    "price":     mrp
                })
                print(f"[OCR P2] {drug_name} | Qty:{qty} | MRP:{mrp}")

    # ── Fallback: very broad search ───────────────────────────────────────
    if not drugs:
        print("[OCR Parser] Using broad fallback...")
        broad = re.compile(
            r"\b([A-Z]{3,}\s+\d+\s*(?:MG|MCG|ML|G|IU)"
            r"(?:\s+[A-Z0-9]{2,}){0,4})\b",
            re.I
        )
        for line in lines:
            for m in broad.finditer(line.upper()):
                name = re.sub(r"\s+", " ", m.group(1)).strip()
                if (name.lower() not in seen and len(name) > 4):
                    seen.add(name.lower())
                    drugs.append({
                        "drug_name": name.title(),
                        "quantity":  "N/A",
                        "price":     "N/A"
                    })
                    print(f"[OCR Fallback] {name}")

    data["drugs"] = drugs
    print(f"[OCR Parser] Total: {len(drugs)} drug(s)")
    return data