# modules/lexicomp_checker.py
# Uses OpenFDA only — no Lexicomp, no API key needed

import sqlite3
import os
import re
import requests
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")

OPENFDA_BASE_URL = "https://api.fda.gov/drug/label.json"
_fda_label_cache = {}


def init_lexicomp_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS openfda_cache (
            cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name TEXT UNIQUE,
            adverse_reactions_text TEXT,
            warnings_text TEXT,
            fetched_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS icsr_queue (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER,
            drug_name TEXT,
            meddra_pt TEXT,
            check_result TEXT,
            icsr_status TEXT DEFAULT 'Pending',
            pdf_path TEXT,
            xml_path TEXT,
            created_at TEXT,
            submitted_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("[OpenFDA] Tables ready.")


def _clean_drug_name(drug_name):
    name = drug_name.lower()
    name = re.sub(r"\d+\s*(mg|mcg|ml|g|iu)\b", "", name)
    name = re.sub(r"\b(tab|tablet|cap|capsule|syrup|injection|inj|s)\b", "", name)
    name = re.sub(r"\b\d+\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def fetch_fda_label(drug_name):
    clean_name = _clean_drug_name(drug_name)
    if not clean_name:
        return {"found": False, "adverse_reactions_text": "", "warnings_text": "", "source": "invalid_name"}

    if clean_name in _fda_label_cache:
        return _fda_label_cache[clean_name]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT adverse_reactions_text, warnings_text FROM openfda_cache WHERE drug_name=?", (clean_name,))
    row = c.fetchone()
    conn.close()

    if row:
        result = {"found": True, "adverse_reactions_text": row[0] or "", "warnings_text": row[1] or "", "source": "local_cache"}
        _fda_label_cache[clean_name] = result
        return result

    result = _call_openfda_api(clean_name)

    if result["found"]:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO openfda_cache
                     (drug_name, adverse_reactions_text, warnings_text, fetched_at)
                     VALUES (?, ?, ?, datetime('now'))""",
                  (clean_name, result["adverse_reactions_text"], result["warnings_text"]))
        conn.commit()
        conn.close()

    _fda_label_cache[clean_name] = result
    return result


def _call_openfda_api(clean_name):
    """Calls OpenFDA. Handles all error cases gracefully so the app never crashes."""
    if not clean_name or len(clean_name) < 2:
        return {"found": False, "adverse_reactions_text": "", "warnings_text": "", "source": "name_too_short"}

    search_attempts = [
        f'openfda.generic_name:"{clean_name}"',
        f'openfda.brand_name:"{clean_name}"',
        f'openfda.substance_name:"{clean_name}"',
    ]

    for search_query in search_attempts:
        try:
            response = requests.get(
                OPENFDA_BASE_URL,
                params={"search": search_query, "limit": 1},
                timeout=8
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results:
                    label = results[0]
                    adverse_reactions = " ".join(label.get("adverse_reactions", []))
                    warnings = " ".join(label.get("warnings", []) + label.get("warnings_and_cautions", []))
                    print(f"[OpenFDA] FOUND label for '{clean_name}'")
                    return {"found": True, "adverse_reactions_text": adverse_reactions,
                            "warnings_text": warnings, "source": "OpenFDA API"}
            elif response.status_code == 404:
                # Normal — this search variant just had no match, try next
                pass
            else:
                print(f"[OpenFDA] Unexpected status {response.status_code} for '{clean_name}'")

            time.sleep(0.3)

        except requests.exceptions.Timeout:
            print(f"[OpenFDA] Timeout for '{clean_name}' — check your internet connection")
            continue
        except requests.exceptions.ConnectionError:
            print(f"[OpenFDA] No internet connection available")
            return {"found": False, "adverse_reactions_text": "", "warnings_text": "", "source": "no_internet"}
        except Exception as e:
            print(f"[OpenFDA] Error: {e}")
            continue

    print(f"[OpenFDA] No FDA label found for '{clean_name}'")
    return {"found": False, "adverse_reactions_text": "", "warnings_text": "", "source": "not_found_in_openfda"}


def _meddra_pt_to_search_terms(meddra_pt):
    SEARCH_TERM_MAP = {
        "peripheral oedema": ["edema", "oedema", "swelling", "swollen"],
        "diarrhoea": ["diarrhea", "diarrhoea", "loose stool"],
        "abdominal pain": ["abdominal pain", "stomach pain", "stomach upset"],
        "rash": ["rash", "skin eruption"],
        "pruritus": ["itching", "pruritus", "itch"],
        "headache": ["headache"],
        "dizziness": ["dizziness", "dizzy", "vertigo"],
        "nausea": ["nausea", "nauseous"],
        "vomiting": ["vomiting", "vomit", "emesis"],
        "pyrexia": ["fever", "pyrexia"],
        "tachycardia": ["tachycardia", "rapid heart", "palpitation"],
        "palpitations": ["palpitation", "heart racing"],
        "dyspnoea": ["dyspnea", "shortness of breath", "breathing difficulty"],
        "cough": ["cough"],
        "myalgia": ["myalgia", "muscle pain", "muscle ache"],
        "arthralgia": ["arthralgia", "joint pain"],
        "fatigue": ["fatigue", "tiredness", "weakness", "asthenia"],
        "insomnia": ["insomnia", "sleep disturbance"],
        "somnolence": ["somnolence", "drowsiness", "sedation"],
        "dry mouth": ["dry mouth", "xerostomia"],
        "tongue oedema": ["tongue swelling", "tongue edema"],
        "lip oedema": ["lip swelling", "lip edema"],
    }
    pt_lower = meddra_pt.lower().strip()
    return SEARCH_TERM_MAP.get(pt_lower, [pt_lower])


def check_adr_in_lexicomp(drug_name, meddra_pt):
    """Main check function — uses OpenFDA exclusively."""
    label_data = fetch_fda_label(drug_name)

    if not label_data["found"]:
        reason_detail = {
            "no_internet": "No internet connection — cannot reach OpenFDA.",
            "not_found_in_openfda": f"No FDA label found for '{drug_name}' in OpenFDA database.",
            "invalid_name": f"Could not parse drug name '{drug_name}'.",
            "name_too_short": f"Drug name '{drug_name}' too short to search."
        }.get(label_data["source"], f"FDA label unavailable for '{drug_name}'.")

        return {
            "found": False,
            "action": "auto_submit_icsr",
            "reason": f"{reason_detail} ICSR auto-generated as a precaution since safety cannot be confirmed.",
            "lexicomp_data": {"found": False, "drug_name": drug_name, "meddra_pt": meddra_pt,
                              "frequency": "Unknown", "source": label_data["source"]}
        }

    full_text = (label_data["adverse_reactions_text"] + " " + label_data["warnings_text"]).lower()
    search_terms = _meddra_pt_to_search_terms(meddra_pt)
    matched_term = None

    for term in search_terms:
        if term in full_text:
            matched_term = term
            break

    if matched_term:
        return {
            "found": True,
            "action": "no_icsr_needed",
            "reason": f"'{meddra_pt}' (matched as '{matched_term}') IS documented in the FDA label for '{drug_name}'. No new ICSR needed.",
            "lexicomp_data": {"found": True, "drug_name": drug_name, "meddra_pt": meddra_pt,
                              "frequency": "Documented", "source": label_data["source"], "matched_term": matched_term}
        }
    else:
        return {
            "found": False,
            "action": "auto_submit_icsr",
            "reason": f"'{meddra_pt}' is NOT mentioned in the FDA label for '{drug_name}'. ICSR auto-generated for PvPI submission.",
            "lexicomp_data": {"found": False, "drug_name": drug_name, "meddra_pt": meddra_pt,
                              "frequency": "Not documented", "source": label_data["source"]}
        }


def add_to_lexicomp_reference(drug_name, meddra_pt, frequency="Unknown"):
    clean_name = _clean_drug_name(drug_name)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT adverse_reactions_text FROM openfda_cache WHERE drug_name=?", (clean_name,))
    row = c.fetchone()
    existing_text = row[0] if row else ""
    updated_text = f"{existing_text} {meddra_pt}".strip()
    c.execute("""INSERT OR REPLACE INTO openfda_cache
                 (drug_name, adverse_reactions_text, warnings_text, fetched_at)
                 VALUES (?, ?, '', datetime('now'))""", (clean_name, updated_text))
    conn.commit()
    conn.close()
    _fda_label_cache.pop(clean_name, None)
    print(f"[OpenFDA] Manually added: {drug_name} -> {meddra_pt}")