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


def parse_apollo_bill(html):
    """
    Parses real Apollo Pharmacy invoice page HTML.
    Updated based on actual Apollo bill structure:
    - Name: VISHAL   Mobile: 9445571426   Bill No: 16280SI00001432
    - Bill Date: 2026-06-26 20:20:00
    - Table: Qty | PRODUCT NAME | SCH | HSN CODE | MFRS | BATCH | EXPIRY | MRP | AMOUNT | GST%
    """
    soup = BeautifulSoup(html, "lxml")
    data = {}
    full_text = soup.get_text(separator="\n")

    # ── Patient name and mobile (real format: "Name: VISHAL  Mobile: 9445571426") ──
    m = re.search(r"Name[:\s]+([A-Z][A-Za-z\s]+?)\s+Mobile[:\s]+(\d{10})", full_text)
    if m:
        data["patient_name"] = m.group(1).strip()
        data["mobile"] = m.group(2).strip()

    # Fallback for name
    if "patient_name" not in data:
        m = re.search(r"Name[:\s]+([A-Z][A-Za-z\s]{1,30})", full_text)
        if m:
            data["patient_name"] = m.group(1).strip()

    # ── Bill number ──
    m = re.search(r"Bill\s*No[:\s]+([A-Z0-9]+)", full_text)
    if m:
        data["invoice_no"] = m.group(1).strip()

    # ── Bill date (real format: "2026-06-26 20:20:00") ──
    m = re.search(r"Bill\s*Date[:\s]+([\d\-]+\s+[\d:]+)", full_text)
    if m:
        data["bill_date"] = m.group(1).strip()
    if "bill_date" not in data:
        m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", full_text)
        if m:
            data["bill_date"] = m.group(1).strip()

    # ── Drug table extraction ──
    # Real Apollo table: Qty | PRODUCT NAME | SCH | HSN CODE | MFRS | BATCH | EXPIRY | MRP | AMOUNT | GST%
    drugs = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 8:
                continue
            # First column must be a number (Qty)
            if not cols[0].strip().isdigit():
                continue
            # Second column is the product name — must have real content
            product = cols[1].strip()
            if len(product) < 3:
                continue
            # Skip header-like rows
            if product.upper() in ["PRODUCT NAME", "MEDICINE", "ITEM", "DESCRIPTION"]:
                continue
            qty = cols[0].strip()
            mrp = cols[7].strip() if len(cols) > 7 else "N/A"
            # Clean MRP — remove ₹ symbol if present
            mrp = mrp.replace("₹", "").replace("Rs.", "").strip()
            drugs.append({
                "drug_name": product,
                "quantity": qty,
                "price": mrp
            })

    # Fallback regex for drug names with dose
    if not drugs:
        matches = re.findall(
            r"([A-Z][A-Za-z]+(?:\s[A-Za-z0-9]+){0,4}\s\d+\s*(?:MG|MCG|ML|G|IU)[A-Z\s\d'S]*)",
            full_text
        )
        seen = set()
        for d in matches:
            dc = re.sub(r"\s+", " ", d.strip())
            if dc.lower() not in seen and len(dc) > 4:
                seen.add(dc.lower())
                drugs.append({"drug_name": dc, "quantity": "N/A", "price": "N/A"})

    if drugs:
        data["drugs"] = drugs

    data["source"] = "Apollo"
    data["capture_method"] = "URL_FETCH"
    return data