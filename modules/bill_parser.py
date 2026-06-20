# modules/bill_parser.py
# PURPOSE: Parses the Apollo bill page (invoice.apollopharmacy.in)
#          Extracts: drug names, quantity, MRP, bill date, invoice no.
#
# IMPORTANT: The "Name:" field on this bill is captured as "patient_name"
# but is NEVER used for patient identification — it's stored for reference
# only (real Apollo bills often show a generic counter name like "RAM").
#
# Based on real Apollo invoice structure:
#   Name: RAM   Mobile: 9445571426   Bill No: 16280WS0097250
#   Bill Date: 2026-06-13 23:08:00
#   Table columns: Qty | PRODUCT NAME | SCH | HSN CODE | MFRS | BATCH | EXPIRY | MRP | AMOUNT | GST%

from bs4 import BeautifulSoup
import re


def parse_apollo_bill(html: str) -> dict:
    """
    Parses the Apollo invoice page HTML (invoice.apollopharmacy.in/...).

    Layer 1: structured tag-based extraction matching the real Apollo invoice table
    Layer 2: regex fallback on plain text (resilient if Apollo updates their HTML)
    """
    soup = BeautifulSoup(html, "lxml")
    data = {}
    full_text = soup.get_text(separator="\n")

    # ── LAYER 1: Structured extraction ──────────────────────────────────────
    try:
        # "Name: RAM   Mobile: 9445571426"
        m = re.search(r"Name\s*:\s*([A-Za-z\s]{1,40}?)\s+Mobile\s*:\s*(\d{10})", full_text, re.I)
        if m:
            data["patient_name"] = m.group(1).strip()
            data["mobile"]       = m.group(2).strip()

        # "Bill No: 16280WS0097250"
        m = re.search(r"Bill\s*No\.?\s*:\s*([\w]+)", full_text, re.I)
        if m:
            data["invoice_no"] = m.group(1).strip()

        # "Bill Date: 2026-06-13 23:08:00"
        m = re.search(r"Bill\s*Date\s*:\s*([\d\-]+\s+[\d:]+)", full_text, re.I)
        if m:
            data["bill_date"] = m.group(1).strip()

        # ── Drug table extraction ───────────────────────────────────────────
        # Apollo invoice table header: Qty | PRODUCT NAME | SCH | HSN CODE |
        #                               MFRS | BATCH | EXPIRY | MRP | AMOUNT | GST%
        tables = soup.find_all("table")
        drugs = []

        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]

                if not cols or len(cols) < 8:
                    continue

                # Skip header rows: first column should be a number (Qty)
                if not cols[0].isdigit():
                    continue

                qty          = cols[0]
                product_name = cols[1]
                mrp          = cols[7] if len(cols) > 7 else "N/A"

                if product_name and len(product_name) > 2:
                    drugs.append({
                        "drug_name": product_name,
                        "quantity":  qty,
                        "price":     mrp
                    })

        if drugs:
            data["drugs"] = drugs

    except Exception as e:
        data["parse_layer1_error"] = str(e)

    # ── LAYER 2: Regex Fallback ────────────────────────────────────────────
    if "patient_name" not in data:
        m = re.search(r"Name\s*:\s*([A-Za-z\s]{1,40})", full_text, re.I)
        if m:
            data["patient_name"] = m.group(1).strip()

    if "mobile" not in data:
        m = re.search(r"Mobile\s*:\s*(\d{10})", full_text, re.I)
        if m:
            data["mobile"] = m.group(1).strip()

    if "invoice_no" not in data:
        m = re.search(r"Bill\s*No\.?\s*:?\s*([\w]+)", full_text, re.I)
        if m:
            data["invoice_no"] = m.group(1).strip()

    if "bill_date" not in data:
        m = re.search(r"(\d{4}-\d{2}-\d{2}[\s\d:]*)", full_text)
        if m:
            data["bill_date"] = m.group(1).strip()
        else:
            m2 = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})", full_text)
            if m2:
                data["bill_date"] = m2.group(1).strip()

    if "drugs" not in data:
        matches = re.findall(
            r"([A-Z][A-Za-z]+(?:\s[A-Za-z0-9]+){0,3}\s\d+\s*(?:MG|MCG|ML|G|IU)[A-Z\s\d']*)",
            full_text, re.I
        )
        if matches:
            seen = set()
            unique_drugs = []
            for d in matches:
                d_clean = re.sub(r"\s+", " ", d.strip())
                if d_clean.lower() not in seen and len(d_clean) > 4:
                    seen.add(d_clean.lower())
                    unique_drugs.append({"drug_name": d_clean, "quantity": "N/A", "price": "N/A"})
            if unique_drugs:
                data["drugs"] = unique_drugs

    data["source"]         = "Apollo"
    data["capture_method"] = "URL_FETCH"
    return data


def parse_medplus_bill(html: str) -> dict:
    """Parses a MedPlus bill HTML page. Same two-layer approach as Apollo."""
    soup = BeautifulSoup(html, "lxml")
    data = {}
    full_text = soup.get_text(separator="\n")

    try:
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                text = row.get_text(separator=" | ", strip=True)

                if re.search(r"customer|patient|member", text, re.I):
                    for cell in row.find_all("td"):
                        cell_text = cell.get_text(strip=True)
                        if re.search(r"customer|patient|member", cell_text, re.I):
                            value = cell_text.split(":")[-1].strip()
                            if value and len(value) > 1:
                                data["patient_name"] = value

                if re.search(r"bill\s*no|invoice\s*no", text, re.I):
                    m = re.search(r"(MP[\w\-]+|[A-Z]{2,5}\d{4,}|\d{6,})", text)
                    if m:
                        data["invoice_no"] = m.group(1)

        drug_rows = soup.find_all("tr", class_=re.compile(r"item|product|medicine|drug", re.I))
        drugs = []
        for row in drug_rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                drug_name = cols[0].get_text(strip=True)
                if drug_name and len(drug_name) > 2:
                    drugs.append({
                        "drug_name": drug_name,
                        "quantity":  cols[1].get_text(strip=True) if len(cols) > 1 else "N/A",
                        "price":     cols[-1].get_text(strip=True)
                    })
        if drugs:
            data["drugs"] = drugs

    except Exception as e:
        data["parse_layer1_error"] = str(e)

    if "patient_name" not in data:
        m = re.search(r"(?:Customer|Patient|Member|Name)\s*[:\-]\s*([A-Za-z\s]{1,40})", full_text, re.I)
        if m:
            data["patient_name"] = m.group(1).strip()

    if "invoice_no" not in data:
        m = re.search(r"(?:Bill|Invoice|Receipt)\s*(?:No|#)\.?\s*[:\-]?\s*([\w\-\/]{3,20})", full_text, re.I)
        if m:
            data["invoice_no"] = m.group(1)

    if "bill_date" not in data:
        m = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})", full_text)
        if m:
            data["bill_date"] = m.group(1).strip()

    if "drugs" not in data:
        matches = re.findall(
            r"([A-Za-z][A-Za-z\s]{2,25}\d+\s*(?:mg|mcg|ml|g|IU))",
            full_text, re.I
        )
        if matches:
            seen = set()
            unique_drugs = []
            for d in matches:
                d_clean = d.strip()
                if d_clean.lower() not in seen:
                    seen.add(d_clean.lower())
                    unique_drugs.append({"drug_name": d_clean, "quantity": "N/A", "price": "N/A"})
            data["drugs"] = unique_drugs

    data["source"]         = "MedPlus"
    data["capture_method"] = "URL_FETCH"
    return data


def auto_detect_and_parse(html: str, url: str) -> dict:
    """Auto-detects Apollo or MedPlus from URL and routes to correct parser."""
    url_lower = url.lower()

    if "apollo" in url_lower or "apmails" in url_lower or "ap.ph" in url_lower:
        return parse_apollo_bill(html)
    elif "medplus" in url_lower:
        return parse_medplus_bill(html)
    else:
        result = parse_apollo_bill(html)
        if not result.get("drugs"):
            result = parse_medplus_bill(html)
        result["source"] = "Unknown"
        return result
