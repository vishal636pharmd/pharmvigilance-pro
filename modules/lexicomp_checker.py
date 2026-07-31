# modules/lexicomp_checker.py
# Uses OpenFDA only — no Lexicomp, no API key needed
# Includes Indian brand name to FDA generic name mapping

import sqlite3
import os
import re
import requests
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")

OPENFDA_BASE_URL = "https://api.fda.gov/drug/label.json"
_fda_label_cache = {}

# ── Indian brand name → FDA generic name mapping ─────────────────────────────
# OpenFDA uses US/international names. Indian brands are mapped here.
INDIAN_BRAND_TO_GENERIC = {
    # ── Paracetamol / Acetaminophen ───────────────────────────────────────
    "crocin":        "acetaminophen",
    "calpol":        "acetaminophen",
    "paracip":       "acetaminophen",
    "dolo":          "acetaminophen",
    "pacimol":       "acetaminophen",
    "fepanil":       "acetaminophen",
    "metacin":       "acetaminophen",
    "pyrigesic":     "acetaminophen",
    "sumo":          "acetaminophen",
    "p 500":         "acetaminophen",

    # ── Ibuprofen ─────────────────────────────────────────────────────────
    "brufen":        "ibuprofen",
    "combiflam":     "ibuprofen",
    "ibugesic":      "ibuprofen",
    "emflam":        "ibuprofen",
    "fenlong":       "ibuprofen",
    "advil":         "ibuprofen",

    # ── Cetirizine ────────────────────────────────────────────────────────
    "okacet":        "cetirizine",
    "cetriz":        "cetirizine",
    "alerid":        "cetirizine",
    "cetzine":       "cetirizine",
    "zyrtec":        "cetirizine",
    "reactine":      "cetirizine",

    # ── Levocetirizine ────────────────────────────────────────────────────
    "levocet":       "levocetirizine",
    "xyzal":         "levocetirizine",
    "lezyncet":      "levocetirizine",

    # ── Fexofenadine ─────────────────────────────────────────────────────
    "allegra":       "fexofenadine",
    "telfast":       "fexofenadine",

    # ── Montelukast ───────────────────────────────────────────────────────
    "montair":       "montelukast",
    "singulair":     "montelukast",
    "montek":        "montelukast",

    # ── Omeprazole ────────────────────────────────────────────────────────
    "omez":          "omeprazole",
    "prilosec":      "omeprazole",
    "omecip":        "omeprazole",
    "ocid":          "omeprazole",

    # ── Pantoprazole ─────────────────────────────────────────────────────
    "pan":           "pantoprazole",
    "pantop":        "pantoprazole",
    "pantocid":      "pantoprazole",
    "protonix":      "pantoprazole",
    "nupenta":       "pantoprazole",

    # ── Rabeprazole ───────────────────────────────────────────────────────
    "razo":          "rabeprazole",
    "rablet":        "rabeprazole",
    "pariet":        "rabeprazole",

    # ── Ranitidine ────────────────────────────────────────────────────────
    "rantac":        "ranitidine",
    "zinetac":       "ranitidine",
    "aciloc":        "ranitidine",

    # ── Metformin ─────────────────────────────────────────────────────────
    "glycomet":      "metformin",
    "glucophage":    "metformin",
    "obimet":        "metformin",
    "gluformin":     "metformin",
    "prometil":      "metformin",

    # ── Glimepiride ───────────────────────────────────────────────────────
    "amaryl":        "glimepiride",
    "glimer":        "glimepiride",
    "glimy":         "glimepiride",

    # ── Metoprolol ────────────────────────────────────────────────────────
    "metpure":       "metoprolol",
    "betaloc":       "metoprolol",
    "lopressor":     "metoprolol",
    "metolar":       "metoprolol",

    # ── Amlodipine ────────────────────────────────────────────────────────
    "amlip":         "amlodipine",
    "amlong":        "amlodipine",
    "norvasc":       "amlodipine",
    "stamlo":        "amlodipine",
    "amcard":        "amlodipine",

    # ── Atorvastatin ─────────────────────────────────────────────────────
    "atorva":        "atorvastatin",
    "storvas":       "atorvastatin",
    "lipitor":       "atorvastatin",
    "atorfit":       "atorvastatin",
    "tonact":        "atorvastatin",

    # ── Rosuvastatin ─────────────────────────────────────────────────────
    "rozat":         "rosuvastatin",
    "crestor":       "rosuvastatin",
    "rosuvas":       "rosuvastatin",
    "rozucor":       "rosuvastatin",

    # ── Telmisartan ──────────────────────────────────────────────────────
    "telma":         "telmisartan",
    "micardis":      "telmisartan",
    "telmikind":     "telmisartan",

    # ── Losartan ─────────────────────────────────────────────────────────
    "losar":         "losartan",
    "cozaar":        "losartan",
    "repace":        "losartan",

    # ── Ramipril ─────────────────────────────────────────────────────────
    "cardace":       "ramipril",
    "altace":        "ramipril",
    "ramistar":      "ramipril",

    # ── Azithromycin ─────────────────────────────────────────────────────
    "azithral":      "azithromycin",
    "zithromax":     "azithromycin",
    "azicip":        "azithromycin",
    "azee":          "azithromycin",
    "z pak":         "azithromycin",

    # ── Amoxicillin ───────────────────────────────────────────────────────
    "mox":           "amoxicillin",
    "amoxil":        "amoxicillin",
    "novamox":       "amoxicillin",
    "trimox":        "amoxicillin",

    # ── Ciprofloxacin ─────────────────────────────────────────────────────
    "ciplox":        "ciprofloxacin",
    "cipro":         "ciprofloxacin",
    "cifran":        "ciprofloxacin",

    # ── Doxycycline ──────────────────────────────────────────────────────
    "doxt":          "doxycycline",
    "vibramycin":    "doxycycline",
    "doxrid":        "doxycycline",

    # ── Vitamin C / Ascorbic Acid ─────────────────────────────────────────
    "limcee":        "ascorbic acid",
    "celin":         "ascorbic acid",
    "vitamin c":     "ascorbic acid",
    "vit c":         "ascorbic acid",

    # ── Vitamin B Complex ─────────────────────────────────────────────────
    "becosules":     "vitamin b",
    "neurobion":     "vitamin b",
    "polybion":      "vitamin b",
    "bcomplex":      "vitamin b",

    # ── Vitamin D ─────────────────────────────────────────────────────────
    "calcirol":      "cholecalciferol",
    "cholecalciferol": "cholecalciferol",
    "uprise":        "cholecalciferol",
    "d rise":        "cholecalciferol",
    "d3 must":       "cholecalciferol",

    # ── Calcium ───────────────────────────────────────────────────────────
    "shelcal":       "calcium carbonate",
    "calcimax":      "calcium carbonate",
    "gemcal":        "calcium carbonate",

    # ── Iron supplements ──────────────────────────────────────────────────
    "autrin":        "ferrous sulfate",
    "fefol":         "ferrous sulfate",
    "orofer":        "iron sucrose",

    # ── Pregabalin ────────────────────────────────────────────────────────
    "lyrica":        "pregabalin",
    "pregabalin":    "pregabalin",
    "pregalin":      "pregabalin",

    # ── Gabapentin ────────────────────────────────────────────────────────
    "gabapin":       "gabapentin",
    "neurontin":     "gabapentin",

    # ── Diclofenac ────────────────────────────────────────────────────────
    "voveran":       "diclofenac",
    "voltaren":      "diclofenac",
    "diclofen":      "diclofenac",

    # ── Tramadol ─────────────────────────────────────────────────────────
    "ultracet":      "tramadol",
    "tramazac":      "tramadol",

    # ── Domperidone ───────────────────────────────────────────────────────
    "domstal":       "domperidone",
    "vomistop":      "domperidone",
    "motilium":      "domperidone",

    # ── Ondansetron ───────────────────────────────────────────────────────
    "emeset":        "ondansetron",
    "zofran":        "ondansetron",
    "ondem":         "ondansetron",

    # ── Metoclopramide ────────────────────────────────────────────────────
    "perinorm":      "metoclopramide",
    "reglan":        "metoclopramide",

    # ── Clonazepam ────────────────────────────────────────────────────────
    "rivotril":      "clonazepam",
    "lonazep":       "clonazepam",

    # ── Alprazolam ────────────────────────────────────────────────────────
    "alprax":        "alprazolam",
    "xanax":         "alprazolam",
    "alzolam":       "alprazolam",

    # ── Sertraline ────────────────────────────────────────────────────────
    "serta":         "sertraline",
    "zoloft":        "sertraline",
    "serenata":      "sertraline",

    # ── Fluoxetine ────────────────────────────────────────────────────────
    "prozac":        "fluoxetine",
    "fludac":        "fluoxetine",
    "flutop":        "fluoxetine",

    # ── Metronidazole ─────────────────────────────────────────────────────
    "flagyl":        "metronidazole",
    "metrogyl":      "metronidazole",
    "aristogyl":     "metronidazole",

    # ── Fluconazole ───────────────────────────────────────────────────────
    "forcan":        "fluconazole",
    "diflucan":      "fluconazole",
    "zocon":         "fluconazole",

    # ── Salbutamol ────────────────────────────────────────────────────────
    "asthalin":      "salbutamol",
    "ventolin":      "salbutamol",
    "salbair":       "salbutamol",

    # ── Levothyroxine ─────────────────────────────────────────────────────
    "thyronorm":     "levothyroxine",
    "eltroxin":      "levothyroxine",
    "synthroid":     "levothyroxine",

    # ── Aspirin ───────────────────────────────────────────────────────────
    "disprin":       "aspirin",
    "ecosprin":      "aspirin",
    "loprin":        "aspirin",
}


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
    """
    Cleans a pharmacy bill drug name and maps Indian brands
    to FDA-recognizable generic names.

    Examples:
        PARACIP 500MG TAB 10S  ->  acetaminophen
        LIMCEE 500MG TAB 15S   ->  ascorbic acid
        IBUPROFEN 400MG TAB    ->  ibuprofen
    """
    name = drug_name.lower().strip()

    # Remove dosage numbers + units
    name = re.sub(r"\d+\s*(mg|mcg|ml|g|iu)\b", "", name)
    # Remove tablet/capsule/injection form words
    name = re.sub(r"\b(tab|tablet|cap|capsule|syrup|inj|injection|s)\b", "", name)
    # Remove standalone numbers like pack size "15s" -> "15"
    name = re.sub(r"\b\d+\b", "", name)
    # Remove extra whitespace
    name = re.sub(r"\s+", " ", name).strip()

    # Check against Indian brand name dictionary
    for brand, generic in INDIAN_BRAND_TO_GENERIC.items():
        if brand in name:
            print(f"[OpenFDA] Indian brand mapped: '{brand}' -> '{generic}'")
            return generic

    return name


def fetch_fda_label(drug_name):
    """
    Fetches FDA drug label. Checks memory cache first,
    then local DB cache, then calls OpenFDA API live.
    """
    clean_name = _clean_drug_name(drug_name)
    if not clean_name:
        return {
            "found": False,
            "adverse_reactions_text": "",
            "warnings_text": "",
            "source": "invalid_name"
        }

    # Check memory cache (fastest)
    if clean_name in _fda_label_cache:
        return _fda_label_cache[clean_name]

    # Check database cache
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT adverse_reactions_text, warnings_text
                 FROM openfda_cache WHERE drug_name=?""", (clean_name,))
    row = c.fetchone()
    conn.close()

    if row:
        result = {
            "found": True,
            "adverse_reactions_text": row[0] or "",
            "warnings_text": row[1] or "",
            "source": "local_cache"
        }
        _fda_label_cache[clean_name] = result
        return result

    # Not cached — call OpenFDA API
    result = _call_openfda_api(clean_name)

    # Save to DB cache for next time
    if result["found"]:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO openfda_cache
                     (drug_name, adverse_reactions_text, warnings_text, fetched_at)
                     VALUES (?, ?, ?, datetime('now'))""",
                  (clean_name,
                   result["adverse_reactions_text"],
                   result["warnings_text"]))
        conn.commit()
        conn.close()

    _fda_label_cache[clean_name] = result
    return result


def _call_openfda_api(clean_name):
    """
    Calls the real OpenFDA API. No API key needed.
    Tries generic_name, brand_name, substance_name in order.
    """
    if not clean_name or len(clean_name) < 2:
        return {
            "found": False,
            "adverse_reactions_text": "",
            "warnings_text": "",
            "source": "name_too_short"
        }

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
                    adverse_reactions = " ".join(
                        label.get("adverse_reactions", [])
                    )
                    warnings = " ".join(
                        label.get("warnings", []) +
                        label.get("warnings_and_cautions", [])
                    )
                    print(f"[OpenFDA] FOUND label for '{clean_name}'")
                    return {
                        "found": True,
                        "adverse_reactions_text": adverse_reactions,
                        "warnings_text": warnings,
                        "source": "OpenFDA API"
                    }
            elif response.status_code == 404:
                pass  # No match for this variant, try next
            else:
                print(f"[OpenFDA] Status {response.status_code} for '{clean_name}'")

            time.sleep(0.3)

        except requests.exceptions.Timeout:
            print(f"[OpenFDA] Timeout for '{clean_name}'")
            continue
        except requests.exceptions.ConnectionError:
            print(f"[OpenFDA] No internet connection")
            return {
                "found": False,
                "adverse_reactions_text": "",
                "warnings_text": "",
                "source": "no_internet"
            }
        except Exception as e:
            print(f"[OpenFDA] Error: {e}")
            continue

    print(f"[OpenFDA] No FDA label found for '{clean_name}'")
    return {
        "found": False,
        "adverse_reactions_text": "",
        "warnings_text": "",
        "source": "not_found_in_openfda"
    }


def _meddra_pt_to_search_terms(meddra_pt):
    """
    Maps MedDRA Preferred Terms to plain English words
    that appear in FDA label text.
    FDA labels use everyday English, not MedDRA terminology.
    """
    SEARCH_TERM_MAP = {
        "peripheral oedema": ["edema", "oedema", "swelling", "swollen"],
        "diarrhoea":         ["diarrhea", "diarrhoea", "loose stool"],
        "abdominal pain":    ["abdominal pain", "stomach pain", "stomach upset"],
        "rash":              ["rash", "skin eruption"],
        "pruritus":          ["itching", "pruritus", "itch"],
        "headache":          ["headache"],
        "dizziness":         ["dizziness", "dizzy", "vertigo"],
        "nausea":            ["nausea", "nauseous"],
        "vomiting":          ["vomiting", "vomit", "emesis"],
        "pyrexia":           ["fever", "pyrexia"],
        "tachycardia":       ["tachycardia", "rapid heart", "palpitation"],
        "palpitations":      ["palpitation", "heart racing"],
        "dyspnoea":          ["dyspnea", "shortness of breath",
                              "breathing difficulty"],
        "cough":             ["cough"],
        "myalgia":           ["myalgia", "muscle pain", "muscle ache"],
        "arthralgia":        ["arthralgia", "joint pain"],
        "fatigue":           ["fatigue", "tiredness", "weakness", "asthenia"],
        "insomnia":          ["insomnia", "sleep disturbance"],
        "somnolence":        ["somnolence", "drowsiness", "sedation"],
        "dry mouth":         ["dry mouth", "xerostomia"],
        "tongue oedema":     ["tongue swelling", "tongue edema"],
        "lip oedema":        ["lip swelling", "lip edema"],
    }
    pt_lower = meddra_pt.lower().strip()
    return SEARCH_TERM_MAP.get(pt_lower, [pt_lower])


def check_adr_in_lexicomp(drug_name, meddra_pt):
    """
    MAIN FUNCTION called by auto_icsr_pipeline.py

    Checks if a reported ADR is documented in the FDA label for that drug.
    Uses OpenFDA API exclusively — no Lexicomp license needed.

    Returns:
        found=True, action="no_icsr_needed"   -> known ADR, no report needed
        found=False, action="auto_submit_icsr" -> unknown ADR, generate ICSR
    """
    label_data = fetch_fda_label(drug_name)

    if not label_data["found"]:
        reason_detail = {
            "no_internet":         "No internet connection — cannot reach OpenFDA.",
            "not_found_in_openfda": f"No FDA label found for '{drug_name}'.",
            "invalid_name":        f"Could not parse drug name '{drug_name}'.",
            "name_too_short":      f"Drug name '{drug_name}' too short to search."
        }.get(label_data["source"],
              f"FDA label unavailable for '{drug_name}'.")

        return {
            "found":  False,
            "action": "auto_submit_icsr",
            "reason": (f"{reason_detail} ICSR auto-generated as a precaution "
                       f"since safety cannot be confirmed."),
            "lexicomp_data": {
                "found":     False,
                "drug_name": drug_name,
                "meddra_pt": meddra_pt,
                "frequency": "Unknown",
                "source":    label_data["source"]
            }
        }

    full_text = (
        label_data["adverse_reactions_text"] + " " +
        label_data["warnings_text"]
    ).lower()

    search_terms  = _meddra_pt_to_search_terms(meddra_pt)
    matched_term  = None

    for term in search_terms:
        if term in full_text:
            matched_term = term
            break

    if matched_term:
        return {
            "found":  True,
            "action": "no_icsr_needed",
            "reason": (f"'{meddra_pt}' (matched as '{matched_term}') IS "
                       f"documented in the FDA label for '{drug_name}'. "
                       f"No new ICSR needed."),
            "lexicomp_data": {
                "found":        True,
                "drug_name":    drug_name,
                "meddra_pt":    meddra_pt,
                "frequency":    "Documented",
                "source":       label_data["source"],
                "matched_term": matched_term
            }
        }
    else:
        return {
            "found":  False,
            "action": "auto_submit_icsr",
            "reason": (f"'{meddra_pt}' is NOT mentioned in the FDA label "
                       f"for '{drug_name}'. ICSR auto-generated for PvPI."),
            "lexicomp_data": {
                "found":     False,
                "drug_name": drug_name,
                "meddra_pt": meddra_pt,
                "frequency": "Not documented",
                "source":    label_data["source"]
            }
        }


def add_to_lexicomp_reference(drug_name, meddra_pt, frequency="Unknown"):
    """
    Manually adds a drug-ADR pair to the local OpenFDA cache.
    Use this when you want to override the FDA check for a specific drug.
    """
    clean_name = _clean_drug_name(drug_name)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT adverse_reactions_text
                 FROM openfda_cache WHERE drug_name=?""", (clean_name,))
    row = c.fetchone()
    existing_text = row[0] if row else ""
    updated_text  = f"{existing_text} {meddra_pt}".strip()
    c.execute("""INSERT OR REPLACE INTO openfda_cache
                 (drug_name, adverse_reactions_text,
                  warnings_text, fetched_at)
                 VALUES (?, ?, '', datetime('now'))""",
              (clean_name, updated_text))
    conn.commit()
    conn.close()
    _fda_label_cache.pop(clean_name, None)
    print(f"[OpenFDA] Manually added: {drug_name} -> {meddra_pt}")