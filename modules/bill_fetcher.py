# modules/bill_fetcher.py
# PURPOSE: Fetches the bill page HTML from a given URL.
#
# ABOUT THE OTP STEP:
# Apollo's bill link (https://apmails.in/APLPHR/xxxxx) first shows an OTP
# verification page. The patient enters the OTP manually in their browser.
# Once verified, Apollo redirects to invoice.apollopharmacy.in/... — THAT
# final URL is what gets passed to fetch_bill_html() below.

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; Pixel 6) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/112.0.0.0 Mobile Safari/537.36"
    )
}


def fetch_bill_html(url: str) -> dict:
    """
    Fetches the Apollo/MedPlus INVOICE page HTML
    (the page AFTER OTP verification has already happened).

    Returns:
        { "success": bool, "html": str or None, "error": str or None }
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            return {"success": True, "html": response.text, "error": None}

        return {
            "success": False,
            "html":    None,
            "error":   f"Server returned status code {response.status_code}"
        }

    except requests.exceptions.Timeout:
        return {"success": False, "html": None, "error": "Request timed out."}

    except requests.exceptions.ConnectionError:
        return {"success": False, "html": None, "error": "Cannot connect. Check internet."}

    except Exception as e:
        return {"success": False, "html": None, "error": str(e)}
