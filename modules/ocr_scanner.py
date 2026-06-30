# modules/ocr_scanner.py
# OCR bill scanner using pytesseract + Pillow
# Works on Render after tesseract-ocr is installed via render.yaml

import re
import os
import base64
import io

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database", "pvpro.db"
)


def _try_set_tesseract_path():
    """Sets tesseract path for different environments."""
    import pytesseract
    possible_paths = [
        "/usr/bin/tesseract",                    # Linux (Render)
        "/usr/local/bin/tesseract",              # Linux alternative
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",  # Windows
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            print(f"[OCR] Tesseract found at: {path}")
            return True
    print("[OCR] Tesseract not found at standard paths — using default")
    return False


def extract_text_from_image(image_data):
    """
    Extracts all text from a pharmacy bill image using OCR.
    Accepts base64 image data from browser.
    Returns dict with success, text, error.
    """
    try:
        from PIL import Image
        import pytesseract
    except ImportError as e:
        return {
            "success": False,
            "text": "",
            "error": f"OCR library not installed: {e}"
        }

    try:
        _try_set_tesseract_path()

        # Decode base64 image from browser
        if "," in image_data:
            # Remove data URL header (data:image/jpeg;base64,...)
            image_data = image_data.split(",", 1)[1]

        image_bytes = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Pre-process for better OCR
        img = _preprocess_image(img)

        # Run OCR with multiple configurations for best result
        configs = [
            r"--oem 3 --psm 6",   # best for structured documents
            r"--oem 3 --psm 4",   # single column
            r"--oem 1 --psm 6",   # legacy engine
        ]

        best_text = ""
        for config in configs:
            try:
                text = pytesseract.image_to_string(img, config=config)
                if len(text.strip()) > len(best_text.strip()):
                    best_text = text
            except Exception as e:
                print(f"[OCR] Config {config} failed: {e}")
                continue

        if not best_text.strip():
            return {
                "success": False,
                "text": "",
                "error": "No text extracted. Ensure bill is well-lit and in focus."
            }

        print(f"[OCR] Successfully extracted {len(best_text)} characters")
        return {"success": True, "text": best_text, "error": None}

    except Exception as e:
        print(f"[OCR] Error: {e}")
        return {"success": False, "text": "", "error": str(e)}


def _preprocess_image(img):
    """Improves image quality for better OCR accuracy."""
    try:
        from PIL import ImageFilter, ImageEnhance

        # Convert to grayscale
        img = img.convert("L")

        # Resize if too small
        width, height = img.size
        if width < 1200:
            scale = 1200 / width
            new_w = int(width * scale)
            new_h = int(height * scale)
            img = img.resize((new_w, new_h))

        # Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        img = img.filter(ImageFilter.SHARPEN)

    except Exception as e:
        print(f"[OCR] Preprocessing warning: {e}")

    return img


def parse_bill_from_text(ocr_text):
    """
    Parses OCR text from a pharmacy bill.
    Handles Apollo, MedPlus, and all Indian pharmacy formats.
    Returns dict with patient_name, bill_date, invoice_no, drugs.
    """
    data = {
        "patient_name": None,
        "invoice_no":   None,
        "bill_date":    None,
        "drugs":        [],
        "source":       "Camera OCR"
    }

    lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
    full_text = ocr_text

    print(f"[OCR Parser] Processing {len(lines)} lines")

    # ── Patient name ──────────────────────────────────────────────────────
    name_patterns = [
        r"(?:Name|Patient|Pt\.?|Customer)\s*[:\-]\s*([A-Za-z][A-Za-z\s]{1,30})",
        r"M/s\.?\s*([A-Z][A-Za-z\s]{2,25})",
    ]
    for line in lines:
        for pattern in name_patterns:
            m = re.search(pattern, line, re.I)
            if m:
                name = m.group(1).strip()
                name = re.sub(
                    r"\s+(Mobile|Phone|No|Bill|Date|Mr|Mrs|Dr|Ms)\b.*",
                    "", name, flags=re.I
                ).strip()
                if 2 <= len(name) <= 30 and re.search(r"[A-Za-z]", name):
                    data["patient_name"] = name
                    break
        if data["patient_name"]:
            break

    # ── Bill number ───────────────────────────────────────────────────────
    for line in lines:
        m = re.search(
            r"(?:Bill|Invoice|Receipt|Ref)\.?\s*(?:No|#|Number)\.?\s*[:\-]?\s*"
            r"([A-Z0-9][A-Z0-9\-\/]{3,20})",
            line, re.I
        )
        if m:
            data["invoice_no"] = m.group(1).strip()
            break

    # ── Bill date ─────────────────────────────────────────────────────────
    date_patterns = [
        r"(\d{4}-\d{2}-\d{2}[\s\d:]*)",         # 2026-06-26 20:20:00
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",        # 26/06/2026
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{2})\b",      # 26/06/26
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[\-\s]\d{2,4})",                         # 26-Jun-26
    ]
    for line in lines:
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

    SKIP_WORDS = {
        "PRODUCT NAME", "ITEM NAME", "MEDICINE", "DESCRIPTION",
        "ITEM", "HSN CODE", "BATCH NO", "BATCH", "EXPIRY", "GST",
        "AMOUNT", "MRP", "TOTAL", "QTY", "QUANTITY", "SCH",
        "MFRS", "CGST", "SGST", "TAXABLE", "INVOICE", "BILL",
        "NAME", "APOLLO", "MEDPLUS", "PHARMACY", "REGISTERED",
        "THANK", "TERMS", "CONDITION"
    }

    for line in lines:
        line_upper = line.upper()

        # Skip header and footer lines
        if any(word in line_upper for word in SKIP_WORDS):
            continue
        if len(line) < 5:
            continue

        # Must contain a dosage pattern to be a drug line
        dose_match = re.search(
            r"\b(\d+\.?\d*)\s*(MG|MCG|ML|G|IU|MG/ML|MCG/ML)\b",
            line, re.I
        )
        if not dose_match:
            continue

        # Try to extract qty at start of line
        qty = "N/A"
        drug_name = ""
        mrp = "N/A"

        qty_match = re.match(r"^(\d+)\s+(.+)", line.strip())
        if qty_match:
            qty  = qty_match.group(1)
            rest = qty_match.group(2).strip()
        else:
            rest = line.strip()

        # Extract drug name — take up to the first multiple-space gap
        # or up to common trailing fields (HSN code = 8 digits)
        drug_match = re.match(
            r"([A-Z][A-Za-z0-9\s\-\.\']+?\d+\s*(?:MG|MCG|ML|G|IU)"
            r"(?:[A-Za-z\s\d\'\/\.]*?))\s{2,}",
            rest + "  ",
            re.I
        )
        if drug_match:
            drug_name = drug_match.group(1).strip()
        else:
            # Split on 2+ spaces or tabs
            parts = re.split(r"\s{2,}|\t", rest)
            drug_name = parts[0].strip()
            # Limit to reasonable length
            drug_name = drug_name[:60]

        # Try to find MRP in the line
        # Apollo format: ... EXPIRY | SCH | MRP | AMOUNT | GST%
        numbers = re.findall(r"\d+\.?\d*", rest)
        if len(numbers) >= 3:
            # In Apollo bills MRP is usually near the end
            # but before the last 2-3 values (AMOUNT, GST%)
            try:
                mrp = numbers[-3]
            except:
                mrp = "N/A"

        # Clean drug name
        drug_name = re.sub(r"\s+", " ", drug_name).strip()
        # Remove trailing standalone numbers or letters
        drug_name = re.sub(r"\s+[A-Z]\s*$", "", drug_name).strip()

        # Validate
        if (len(drug_name) > 4 and
                re.search(r"[A-Za-z]{2,}", drug_name) and
                re.search(r"\d", drug_name) and  # must have a number (dosage)
                drug_name.lower() not in seen):
            seen.add(drug_name.lower())
            drugs.append({
                "drug_name": drug_name,
                "quantity":  qty,
                "price":     mrp
            })
            print(f"[OCR Parser] Drug found: {drug_name} | Qty:{qty} | MRP:{mrp}")

    # Fallback: simpler pattern if no drugs found yet
    if not drugs:
        print("[OCR Parser] Primary extraction failed, trying fallback...")
        fallback = re.compile(
            r"([A-Z][A-Z0-9]+\s+\d+\.?\d*\s*(?:MG|MCG|ML|G|IU)"
            r"(?:\s+[A-Z]+)*(?:\s+\d+[SsMmLl])?)",
            re.I
        )
        for line in lines:
            for m in fallback.finditer(line):
                drug_name = re.sub(r"\s+", " ", m.group(1)).strip()
                if (len(drug_name) > 4 and
                        drug_name.lower() not in seen):
                    seen.add(drug_name.lower())
                    drugs.append({
                        "drug_name": drug_name,
                        "quantity":  "N/A",
                        "price":     "N/A"
                    })
                    print(f"[OCR Parser] Fallback drug: {drug_name}")

    data["drugs"] = drugs
    print(f"[OCR Parser] Total drugs found: {len(drugs)}")
    return data