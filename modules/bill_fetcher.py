# modules/bill_fetcher.py
import requests

# These headers make the request look like a real Chrome browser
# Apollo checks these before serving the invoice page
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; Pixel 6) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/112.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
    "Referer": "https://www.apollopharmacy.in/",
}


def fetch_bill_html(url):
    """
    Fetches the Apollo invoice page HTML.
    Uses real browser headers to bypass Apollo's bot detection.
    """
    try:
        session = requests.Session()

        # First visit Apollo's homepage to get cookies
        # (Apollo checks for valid session cookies)
        try:
            session.get(
                "https://www.apollopharmacy.in/",
                headers=HEADERS,
                timeout=8
            )
        except Exception:
            pass  # Even if homepage fails, try the invoice URL directly

        # Now fetch the actual invoice
        response = session.get(
            url,
            headers=HEADERS,
            timeout=15,
            allow_redirects=True
        )

        if response.status_code == 200:
            html = response.text
            # Check if we got a real invoice page or a login/error page
            if any(keyword in html.lower() for keyword in
                   ["product name", "bill no", "paracip", "invoice",
                    "apollo", "qty", "mrp"]):
                return {"success": True, "html": html, "error": None}
            else:
                return {
                    "success": False,
                    "html": None,
                    "error": (
                        "Apollo returned a page but it doesn't contain "
                        "bill details. The link may have expired or requires "
                        "a new OTP. Please use 'Paste Bill Content' instead."
                    )
                }

        elif response.status_code == 403:
            return {
                "success": False, "html": None,
                "error": (
                    "Apollo blocked the request (403). "
                    "Please use 'Paste Bill Content' tab instead — "
                    "open your Apollo link, select all text, copy and paste it."
                )
            }
        elif response.status_code == 404:
            return {
                "success": False, "html": None,
                "error": "Bill link not found (404). The link may have expired."
            }
        else:
            return {
                "success": False, "html": None,
                "error": f"Apollo returned status {response.status_code}. Try the text paste method."
            }

    except requests.exceptions.Timeout:
        return {
            "success": False, "html": None,
            "error": (
                "Request timed out — Apollo's server is slow or blocking. "
                "Please use 'Paste Bill Content' tab: "
                "open your Apollo link → select all text → copy → paste here."
            )
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False, "html": None,
            "error": "Cannot connect. Check your internet connection."
        }
    except Exception as e:
        return {"success": False, "html": None, "error": str(e)}