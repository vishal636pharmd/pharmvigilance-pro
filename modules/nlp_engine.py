# modules/nlp_engine.py
# MODULE 4: Converts patient's natural language symptom → MedDRA Preferred Term
import re

SYNONYM_MAP = {
    "swollen feet": "Peripheral oedema", "swollen legs": "Peripheral oedema",
    "swollen ankles": "Peripheral oedema", "feet are swollen": "Peripheral oedema",
    "legs are swollen": "Peripheral oedema", "ankle swelling": "Peripheral oedema",
    "loose stools": "Diarrhoea", "loose motion": "Diarrhoea",
    "loose motions": "Diarrhoea", "watery stools": "Diarrhoea",
    "diarrhea": "Diarrhoea", "diarrhoea": "Diarrhoea",
    "stomach pain": "Abdominal pain", "tummy pain": "Abdominal pain",
    "stomach ache": "Abdominal pain", "abdominal pain": "Abdominal pain",
    "red spots": "Rash", "skin rash": "Rash", "rashes": "Rash",
    "red patches": "Rash", "rash": "Rash",
    "itchy skin": "Pruritus", "itching": "Pruritus", "skin itching": "Pruritus",
    "fast heartbeat": "Tachycardia", "racing heart": "Tachycardia",
    "heart beating fast": "Tachycardia", "palpitations": "Palpitations",
    "headache": "Headache", "head pain": "Headache", "head ache": "Headache",
    "dizziness": "Dizziness", "feeling dizzy": "Dizziness", "lightheaded": "Dizziness",
    "nausea": "Nausea", "feeling sick": "Nausea", "feeling nauseous": "Nausea",
    "vomiting": "Vomiting", "throwing up": "Vomiting", "vomit": "Vomiting",
    "fever": "Pyrexia", "high temperature": "Pyrexia", "high fever": "Pyrexia",
    "difficulty breathing": "Dyspnoea", "shortness of breath": "Dyspnoea",
    "trouble breathing": "Dyspnoea", "breathless": "Dyspnoea",
    "dry cough": "Cough", "coughing": "Cough", "cough": "Cough",
    "muscle pain": "Myalgia", "body pain": "Myalgia", "muscle ache": "Myalgia",
    "joint pain": "Arthralgia", "joints hurt": "Arthralgia",
    "tongue swelling": "Tongue oedema", "swollen tongue": "Tongue oedema",
    "lip swelling": "Lip oedema", "swollen lips": "Lip oedema",
    "tiredness": "Fatigue", "feeling tired": "Fatigue", "feeling weak": "Fatigue",
    "weakness": "Fatigue", "fatigue": "Fatigue",
    "can't sleep": "Insomnia", "trouble sleeping": "Insomnia", "insomnia": "Insomnia",
    "drowsiness": "Somnolence", "feeling drowsy": "Somnolence", "sleepy": "Somnolence",
    "dry mouth": "Dry mouth", "mouth dry": "Dry mouth",
}


def standardize_symptom(raw_text):
    """
    Converts patient raw symptom text to MedDRA Preferred Term.
    Returns dict: { meddra_pt, method, confidence }
    """
    text_lower = raw_text.lower().strip()

    # Step 1: Rule-based phrase match
    for phrase, meddra_term in SYNONYM_MAP.items():
        if phrase in text_lower:
            return {"meddra_pt": meddra_term, "method": "rule_based", "confidence": 1.0}

    # Step 2: Single word match
    words = re.sub(r"[^a-z\s]", "", text_lower).split()
    for word in words:
        if word in SYNONYM_MAP:
            return {"meddra_pt": SYNONYM_MAP[word], "method": "word_match", "confidence": 0.8}

    # Step 3: Try spaCy if installed
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text_lower)
        for token in doc:
            if token.lemma_.lower() in SYNONYM_MAP:
                return {"meddra_pt": SYNONYM_MAP[token.lemma_.lower()],
                        "method": "spacy_lemma", "confidence": 0.75}
    except Exception:
        pass

    # Step 4: No match — return cleaned raw text
    return {"meddra_pt": raw_text.strip().capitalize(), "method": "no_match", "confidence": 0.0}


def process_all_unprocessed():
    """Processes all unprocessed symptom reports. Called from /nlp-process route."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from modules.patient_db import get_unprocessed_reports, update_meddra_term
    from modules.meddra_mapper import get_meddra_hierarchy

    reports = get_unprocessed_reports()
    processed = []
    for report in reports:
        result = standardize_symptom(report["raw_symptom"])
        hierarchy = get_meddra_hierarchy(result["meddra_pt"])
        update_meddra_term(report["report_id"], result["meddra_pt"], hierarchy["soc"])
        processed.append({
            "report_id": report["report_id"],
            "raw": report["raw_symptom"],
            "meddra_pt": result["meddra_pt"],
            "soc": hierarchy["soc"],
            "method": result["method"]
        })
        print(f"[NLP] '{report['raw_symptom']}' -> '{result['meddra_pt']}' ({result['method']})")
    return processed