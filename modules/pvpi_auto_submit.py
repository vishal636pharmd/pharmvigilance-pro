# modules/pvpi_auto_submit.py
#
# PURPOSE: Watches the reports/generated_pdfs/ folder for new E2B XML files.
# When a new XML file appears, it automatically opens PvPI VigiFlow in a
# headless browser, logs in, and uploads the file.
#
# ARCHITECTURE:
#   [PVPro generates XML] -> [Watchdog detects new file] ->
#   [Playwright logs into VigiFlow] -> [Uploads XML] ->
#   [Downloads acknowledgement] -> [Logs success]
#
# HOW TO RUN (on your local PC, separate terminal):
#   python modules/pvpi_auto_submit.py
#
# IMPORTANT:
#   - Set your VigiFlow credentials below
#   - Register at: https://vigiflow.ipc.gov.in
#   - This runs locally only — not deployed to Render

import os
import sys
import time
import shutil
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events    import FileSystemEventHandler

# ── YOUR VIGIFLOW CREDENTIALS ────────────────────────────────────────────────
# Register at https://vigiflow.ipc.gov.in to get these
VIGIFLOW_USERNAME = ""   # your VigiFlow username
VIGIFLOW_PASSWORD = ""   # your VigiFlow password
VIGIFLOW_URL      = "https://vigiflow.ipc.gov.in"
# ─────────────────────────────────────────────────────────────────────────────

WATCH_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "generated_pdfs"
)
SUBMITTED_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "submitted"
)


def submit_xml_to_vigiflow(xml_filepath):
    """
    Uses Playwright headless browser to log into PvPI VigiFlow
    and upload an E2B XML file.

    Args:
        xml_filepath: full path to the E2B XML file to upload

    Returns:
        True if submitted successfully, False if failed
    """
    if not VIGIFLOW_USERNAME or not VIGIFLOW_PASSWORD:
        print("[VigiFlow] Credentials not configured in pvpi_auto_submit.py")
        print("[VigiFlow] Register at https://vigiflow.ipc.gov.in to get credentials")
        return False

    print(f"[VigiFlow] Starting auto-submission for: {os.path.basename(xml_filepath)}")

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Launch browser (headless = invisible, set to False to watch it)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page    = context.new_page()

            # ── STEP 1: Open VigiFlow login page ─────────────────────────
            print("[VigiFlow] Opening login page...")
            page.goto(VIGIFLOW_URL, timeout=30000)
            page.wait_for_load_state("networkidle")

            # ── STEP 2: Log in ────────────────────────────────────────────
            print("[VigiFlow] Logging in...")
            try:
                # Try common login field selectors
                page.fill("input[name='username'], input[id='username'], input[type='text']",
                          VIGIFLOW_USERNAME)
                page.fill("input[name='password'], input[id='password'], input[type='password']",
                          VIGIFLOW_PASSWORD)
                page.click("button[type='submit'], input[type='submit'], button:has-text('Login')")
                page.wait_for_load_state("networkidle", timeout=15000)
                print("[VigiFlow] Login successful")
            except Exception as e:
                print(f"[VigiFlow] Login failed: {e}")
                browser.close()
                return False

            # ── STEP 3: Navigate to report submission ─────────────────────
            print("[VigiFlow] Navigating to submission page...")
            try:
                # Look for "New Report" or "Submit Report" or "Import" button
                page.click("a:has-text('New Report'), button:has-text('Submit'), "
                           "a:has-text('Import'), a:has-text('Upload')",
                           timeout=10000)
                page.wait_for_load_state("networkidle")
            except Exception as e:
                print(f"[VigiFlow] Could not find submission button: {e}")
                print("[VigiFlow] Taking screenshot for debugging...")
                page.screenshot(path="vigiflow_debug.png")
                browser.close()
                return False

            # ── STEP 4: Upload the XML file ───────────────────────────────
            print(f"[VigiFlow] Uploading {os.path.basename(xml_filepath)}...")
            try:
                # Find the file upload input
                file_input = page.locator("input[type='file']")
                file_input.set_input_files(xml_filepath)
                page.wait_for_timeout(2000)  # wait for file to be accepted

                # Click the final submit/upload button
                page.click("button[type='submit'], button:has-text('Upload'), "
                           "button:has-text('Submit')",
                           timeout=10000)
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception as e:
                print(f"[VigiFlow] Upload failed: {e}")
                page.screenshot(path="vigiflow_upload_debug.png")
                browser.close()
                return False

            # ── STEP 5: Get acknowledgement ───────────────────────────────
            ack_number = None
            try:
                # Look for acknowledgement number on the success page
                ack_text = page.locator(
                    "[class*='ack'], [id*='ack'], [class*='success'], "
                    "h2:has-text('Success'), p:has-text('ACK')"
                ).first.text_content(timeout=5000)
                ack_number = ack_text
                print(f"[VigiFlow] SUCCESS! Acknowledgement: {ack_number}")
            except:
                print("[VigiFlow] Submitted — could not extract acknowledgement number")
                print("[VigiFlow] Taking screenshot of result page...")
                page.screenshot(path="vigiflow_success.png")

            browser.close()

            # Move file to submitted folder
            os.makedirs(SUBMITTED_FOLDER, exist_ok=True)
            submitted_path = os.path.join(SUBMITTED_FOLDER,
                                          os.path.basename(xml_filepath))
            shutil.move(xml_filepath, submitted_path)
            print(f"[VigiFlow] File moved to submitted folder: {submitted_path}")

            # Log the submission
            _log_submission(xml_filepath, ack_number)

            return True

    except ImportError:
        print("[VigiFlow] Playwright not installed. Run: playwright install chromium")
        return False
    except Exception as e:
        print(f"[VigiFlow] Unexpected error: {e}")
        return False


def _log_submission(xml_filepath, ack_number):
    """Logs submission details to a local file for records."""
    log_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports", "submission_log.txt"
    )
    with open(log_path, "a") as f:
        f.write(f"{datetime.now()} | FILE: {os.path.basename(xml_filepath)} | "
                f"ACK: {ack_number or 'Not captured'}\n")


# ─────────────────────────────────────────────────────────────────────────────
# WATCHDOG — Folder Monitor
# ─────────────────────────────────────────────────────────────────────────────

class XMLFileHandler(FileSystemEventHandler):
    """
    Watchdog event handler. Fires whenever a new file appears
    in the watch folder.
    """
    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path

        # Only process E2B XML files
        if not filepath.endswith(".xml") or "E2B" not in filepath:
            return

        print(f"\n[Watchdog] New E2B XML detected: {os.path.basename(filepath)}")
        print(f"[Watchdog] Waiting 2 seconds for file to finish writing...")
        time.sleep(2)  # let the file finish being written

        # Submit to VigiFlow
        success = submit_xml_to_vigiflow(filepath)

        if success:
            print(f"[Watchdog] Auto-submission complete for {os.path.basename(filepath)}")
        else:
            print(f"[Watchdog] Auto-submission failed. File kept in: {filepath}")
            print(f"[Watchdog] You can manually submit at: {VIGIFLOW_URL}")


def start_folder_watcher():
    """
    Starts the background folder watcher.
    Run this in a separate terminal:
        python modules/pvpi_auto_submit.py
    """
    os.makedirs(WATCH_FOLDER,     exist_ok=True)
    os.makedirs(SUBMITTED_FOLDER, exist_ok=True)

    print("=" * 60)
    print("  PVPro — PvPI VigiFlow Auto-Submission Service")
    print("=" * 60)
    print(f"  Watching: {WATCH_FOLDER}")
    print(f"  New E2B XML files will be auto-submitted to VigiFlow")
    print(f"  Portal: {VIGIFLOW_URL}")
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)

    if not VIGIFLOW_USERNAME:
        print("\n  WARNING: VigiFlow credentials not set.")
        print("  Edit VIGIFLOW_USERNAME and VIGIFLOW_PASSWORD")
        print("  in modules/pvpi_auto_submit.py")
        print("  Register at: https://vigiflow.ipc.gov.in\n")

    event_handler = XMLFileHandler()
    observer      = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[Watchdog] Stopped.")
    observer.join()


if __name__ == "__main__":
    start_folder_watcher()