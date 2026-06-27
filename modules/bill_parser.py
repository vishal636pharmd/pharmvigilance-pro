# modules/bill_parser.py
from bs4 import BeautifulSoup
import re


def parse_apollo_bill(html):
    """
    Parses real Apollo Pharmacy invoice page.
    Handles format: Name: VISHAL  Mobile: 9445571426
    Bill No: 16280SI00001432  Bill Date: 2026-06-26 20:20:00
    Table: Qty | PRODUCT NAME | SCH | HSN CODE | MFRS | BATCH | EXPIRY | MRP | AMOUNT | GST%
    """
    soup = BeautifulSoup(html, "lxml")
    data = {}
    full_text = soup.get_text(separator="\n")

    # Patient name and mobile
    m = re.search(r"Name[:\s]+([A-Z][A-Za-z\s]+?)\s+Mobile[:\s]+(\d{10})", full_text)
    if m:
        data["patient_name"] = m.group(1).strip()
        data["mobile"]       = m.group(2).strip()

    if "patient_name" not in data:
        m = re.search(r"Name[:\s]+([A-Z][A-Za-z\s]{1,30})", full_text)
        if m:
            data["patient_name"] = m.group(1).strip()

    # Bill number
    m = re.search(r"Bill\s*No[:\s]+([A-Z0-9]+)", full_text)
    if m:
        data["invoice_no"] = m.group(1).strip()

    # Bill date
    m = re.search(r"Bill\s*Date[:\s]+([\d\-]+\s+[\d:]+)", full_text)
    if m:
        data["bill_date"] = m.group(1).strip()
    if "bill_date" not in data:
        m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", full_text)
        if m:
            data["bill_date"] = m.group(1).strip()

    # Drug table
    drugs = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 8:
                continue
            if not cols[0].strip().isdigit():
                continue
            product = cols[1].strip()
            if len(product) < 3:
                continue
            if product.upper() in ["PRODUCT NAME", "MEDICINE", "ITEM", "DESCRIPTION"]:
                continue
            qty = cols[0].strip()
            mrp = cols[7].strip() if len(cols) > 7 else "N/A"
            mrp = mrp.replace("₹", "").replace("Rs.", "").strip()
            drugs.append({
                "drug_name": product,
                "quantity":  qty,
                "price":     mrp
            })

    # Fallback regex if table parsing found nothing
    if not drugs:
        matches = re.findall(
            r"([A-Z][A-Za-z]+(?:\s[A-Za-z0-9]+){0,4}\s\d+\s*"
            r"(?:MG|MCG|ML|G|IU)[A-Z\s\d'S]*)",
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

    data["source"]         = "Apollo"
    data["capture_method"] = "URL_FETCH"
    return data


def parse_medplus_bill(html):
    """
    Parses MedPlus pharmacy invoice pages.
    """
    soup = BeautifulSoup(html, "lxml")
    data = {}
    full_text = soup.get_text(separator="\n")

    # Patient name
    m = re.search(r"(?:Customer|Patient|Name)\s*[:\-]\s*([A-Za-z\s]{1,40})", full_text, re.I)
    if m:
        data["patient_name"] = m.group(1).strip()

    # Invoice number
    m = re.search(r"(?:Bill|Invoice)\s*(?:No|#)\.?\s*:?\s*([\w\-\/]{3,20})", full_text, re.I)
    if m:
        data["invoice_no"] = m.group(1)

    # Date
    m = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})", full_text)
    if m:
        data["bill_date"] = m.group(1).strip()

    # Drugs
    matches = re.findall(
        r"([A-Za-z][A-Za-z\s]{2,25}\d+\s*(?:mg|mcg|ml|g|IU))",
        full_text, re.I
    )
    if matches:
        seen = set()
        drugs = []
        for d in matches:
            dc = d.strip()
            if dc.lower() not in seen:
                seen.add(dc.lower())
                drugs.append({"drug_name": dc, "quantity": "N/A", "price": "N/A"})
        data["drugs"] = drugs

    data["source"] = "MedPlus"
    return data


def auto_detect_and_parse(html, url):
    """
    Auto-detects pharmacy source from URL and parses accordingly.
    Works for ANY Apollo link regardless of the token in the URL.
    The parser reads page content, not the URL token — so it works
    for every new bill link Apollo generates.
    """
    url_lower = url.lower()

    if ("apollo" in url_lower or
            "apmails" in url_lower or
            "afterotpvalidation" in url_lower or
            "apollopharmacy" in url_lower):
        return parse_apollo_bill(html)

    elif "medplus" in url_lower:
        return parse_medplus_bill(html)

    else:
        # Unknown source — try Apollo parser first, then MedPlus
        result = parse_apollo_bill(html)
        if not result.get("drugs"):
            result = parse_medplus_bill(html)
        result["source"] = "Unknown"
        return result