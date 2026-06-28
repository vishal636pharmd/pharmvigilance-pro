# modules/ocr_scanner.py
# PURPOSE: Extracts medicine details from a photo of a pharmacy bill
# using OCR (Optical Character Recognition).
# Works for Apollo, MedPlus, local pharmacies — any printed bill.
# Uses pytesseract (free, open source, no API key needed).

import re
import os
import base64
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database", "pvpro.db"
)


def extract_text_from_image(image_data_or_path):
    """
    Extracts all text from a pharmacy bill image using OCR.

    Args:
        image_data_or_path: either a file path (str) or
                            base64 encoded image data (bytes/str)

    Returns:
        dict with extracted_text (str) and success (bool)
    """
    try:
        from PIL import Image
        import pytesseract
        import io

        # Load image
        if isinstance(image_data_or_path, str):
            if image_data_or_path.startswith("data:image"):
                # Base64 from browser camera
                header, data = image_data_or_path.split(",", 1)
                image_bytes = base64.b64decode(data)
                img = Image.open(io.BytesIO(image_bytes))
            elif os.path.exists(image_data_or_path):
                # File path
                img = Image.open(image_data_or_path)
            else:
                # Raw base64 without header
                image_bytes = base64.b64decode(image_data_or_path)
                img = Image.open(io.BytesIO(image_bytes))
        else:
            # Bytes directly
            img = Image.open(io.BytesIO(image_data_or_path))

        # Pre-process image for better OCR accuracy
        img = _preprocess_image(img)

        # Run OCR
        custom_config = r"--oem 3 --psm 6"
        text = pytesseract.image_to_string(img, config=custom_config)

        print(f"[OCR] Extracted {len(text)} characters from image")
        return {"success": True, "text": text, "error": None}

    except ImportError:
        return {
            "success": False,
            "text": "",
            "error": "pytesseract not installed on server"
        }
    except Exception as e:
        print(f"[OCR] Error: {e}")
        return {"success": False, "text": "", "error": str(e)}


def _preprocess_image(img):
    """
    Improves image quality for better OCR accuracy.
    Converts to grayscale and increases contrast.
    """
    try:
        from PIL import ImageFilter, ImageEnhance

        # Convert to grayscale
        img = img.convert("L")

        # Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        # Resize if too small (OCR works better on larger images)
        width, height = img.size
        if width < 1000:
            scale = 1000 / width
            img = img.resize(
                (int(width * scale), int(height * scale))
            )

    except Exception as e:
        print(f"[OCR] Preprocessing warning: {e}")

    return img


def parse_bill_from_text(ocr_text):
    """
    Parses the OCR text from a pharmacy bill and extracts
    structured medicine data.

    Handles Apollo, MedPlus, and generic pharmacy formats.

    Returns:
        dict with patient_name, bill_date, invoice_no, drugs list
    """
    data = {
        "patient_name": None,
        "invoice_no":   None,
        "bill_date":    None,
        "drugs":        [],
        "source":       "Camera OCR"
    }

    lines = ocr_text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

    # ── Patient name ──────────────────────────────────────────────────────
    for line in cleaned_lines:
        m = re.search(
            r"(?:Name|Patient|Customer)\s*[:\-]\s*([A-Za-z\s]{2,40})",
            line, re.I
        )
        if m:
            name = m.group(1).strip()
            # Remove trailing words that aren't names
            name = re.sub(
                r"\s+(Mobile|Phone|No|Bill|Date|Mr|Mrs|Dr).*",
                "", name, flags=re.I
            ).strip()
            if len(name) > 1:
                data["patient_name"] = name
                break

    # ── Bill number ───────────────────────────────────────────────────────
    for line in cleaned_lines:
        m = re.search(
            r"(?:Bill|Invoice|Receipt)\s*(?:No|#|Number)\.?\s*[:\-]?\s*"
            r"([A-Z0-9\-\/]{4,20})",
            line, re.I
        )
        if m:
            data["invoice_no"] = m.group(1).strip()
            break

    # ── Bill date ─────────────────────────────────────────────────────────
    date_patterns = [
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",  # 2026-06-26 20:20:00
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",              # 26/06/2026
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4})",                                   # 26 Jun 2026
    ]
    for line in cleaned_lines:
        for pattern in date_patterns:
            m = re.search(pattern, line, re.I)
            if m:
                data["bill_date"] = m.group(1).strip()
                break
        if data["bill_date"]:
            break

    # ── Drug extraction ───────────────────────────────────────────────────
    drugs = []
    seen  = set()

    # Pattern 1: Lines with dosage info (most reliable)
    # e.g. "10  PARACIP 500MG TAB 10S  H  30049069  CIPL  CH50394  0.96"
    for line in cleaned_lines:
        # Skip header lines
        if any(word in line.upper() for word in
               ["PRODUCT NAME", "MEDICINE", "DESCRIPTION",
                "ITEM", "HSN", "BATCH", "EXPIRY", "GST%",
                "AMOUNT", "MRP", "SCH", "MFRS"]):
            continue

        # Check if line contains a drug dosage pattern
        dose_match = re.search(
            r"(\d+)\s*(?:MG|MCG|ML|G|IU|MG/ML)", line, re.I
        )
        if not dose_match:
            continue

        # Try to extract: qty at start + drug name
        qty_match = re.match(r"^(\d+)\s+(.+)", line.strip())
        if qty_match:
            qty      = qty_match.group(1)
            rest     = qty_match.group(2).strip()
            # Drug name ends before extra codes/numbers
            # e.g. "PARACIP 500MG TAB 10S  H  30049069"
            drug_match = re.match(
                r"([A-Z][A-Za-z0-9\s]+?\d+\s*(?:MG|MCG|ML|G|IU)"
                r"[A-Za-z\s\d\']*?)\s{2,}",
                rest + "  ", re.I
            )
            if drug_match:
                drug_name = drug_match.group(1).strip()
            else:
                # Take everything up to first double space or code
                parts     = re.split(r"\s{2,}|\t", rest)
                drug_name = parts[0].strip() if parts else rest[:40]

            # Try to extract MRP (usually last number before GST%)
            mrp = "N/A"
            numbers = re.findall(r"\d+\.?\d*", rest)
            if len(numbers) >= 2:
                mrp = numbers[-2]  # second to last is usually MRP

        else:
            # No qty at start — take whole line as drug name
            qty       = "N/A"
            drug_name = line.strip()[:50]
            mrp       = "N/A"

        # Clean drug name
        drug_name = re.sub(r"\s+", " ", drug_name).strip()

        # Validate: must have letter + digit (e.g. 500MG)
        if (len(drug_name) > 3 and
                re.search(r"[A-Za-z]", drug_name) and
                drug_name.lower() not in seen):
            seen.add(drug_name.lower())
            drugs.append({
                "drug_name": drug_name,
                "quantity":  qty,
                "price":     mrp
            })

    # Pattern 2: Common medicine name patterns (fallback)
    if not drugs:
        medicine_pattern = re.compile(
            r"([A-Z][A-Za-z]+(?:\s[A-Za-z0-9]+){0,3}"
            r"\s\d+\s*(?:MG|MCG|ML|G|IU)[A-Za-z\s\d\']*)",
            re.I
        )
        for line in cleaned_lines:
            for m in medicine_pattern.finditer(line):
                drug_name = re.sub(r"\s+", " ", m.group(1)).strip()
                if (len(drug_name) > 3 and
                        drug_name.lower() not in seen):
                    seen.add(drug_name.lower())
                    drugs.append({
                        "drug_name": drug_name,
                        "quantity":  "N/A",
                        "price":     "N/A"
                    })

    data["drugs"] = drugs

    print(f"[OCR] Parsed: {len(drugs)} drug(s) found")
    for d in drugs:
        print(f"  -> {d['drug_name']} | Qty:{d['quantity']} | MRP:{d['price']}")

    return data