# modules/meddra_mapper.py
# MODULE 7: Maps MedDRA Preferred Term to full hierarchy (HLT + SOC)

MEDDRA_MAP = {
    "Peripheral oedema": {"hlt": "Fluid retention",                    "soc": "Cardiac disorders"},
    "Diarrhoea":         {"hlt": "Diarrhoea (excl infective)",         "soc": "Gastrointestinal disorders"},
    "Abdominal pain":    {"hlt": "Gastrointestinal signs and symptoms", "soc": "Gastrointestinal disorders"},
    "Nausea":            {"hlt": "Nausea and vomiting symptoms",        "soc": "Gastrointestinal disorders"},
    "Vomiting":          {"hlt": "Nausea and vomiting symptoms",        "soc": "Gastrointestinal disorders"},
    "Rash":              {"hlt": "Rashes, eruptions and exanthems",     "soc": "Skin and subcutaneous tissue disorders"},
    "Pruritus":          {"hlt": "Pruritus NEC",                        "soc": "Skin and subcutaneous tissue disorders"},
    "Headache":          {"hlt": "Headaches NEC",                       "soc": "Nervous system disorders"},
    "Dizziness":         {"hlt": "Dizziness and giddiness",             "soc": "Nervous system disorders"},
    "Somnolence":        {"hlt": "Disturbances in consciousness",       "soc": "Nervous system disorders"},
    "Pyrexia":           {"hlt": "Body temperature conditions",         "soc": "General disorders and administration site conditions"},
    "Fatigue":           {"hlt": "Asthenic conditions",                 "soc": "General disorders and administration site conditions"},
    "Tachycardia":       {"hlt": "Rate and rhythm disorders NEC",       "soc": "Cardiac disorders"},
    "Palpitations":      {"hlt": "Cardiac signs and symptoms NEC",      "soc": "Cardiac disorders"},
    "Dyspnoea":          {"hlt": "Breathing abnormalities",             "soc": "Respiratory, thoracic and mediastinal disorders"},
    "Cough":             {"hlt": "Coughing and associated symptoms",    "soc": "Respiratory, thoracic and mediastinal disorders"},
    "Myalgia":           {"hlt": "Muscle pains",                        "soc": "Musculoskeletal and connective tissue disorders"},
    "Arthralgia":        {"hlt": "Joint-related signs and symptoms",    "soc": "Musculoskeletal and connective tissue disorders"},
    "Tongue oedema":     {"hlt": "Oral soft tissue conditions",         "soc": "Gastrointestinal disorders"},
    "Lip oedema":        {"hlt": "Oral soft tissue conditions",         "soc": "Gastrointestinal disorders"},
    "Insomnia":          {"hlt": "Sleep disorders and disturbances",    "soc": "Psychiatric disorders"},
    "Dry mouth":         {"hlt": "Salivary gland conditions",           "soc": "Gastrointestinal disorders"},
}


def get_meddra_hierarchy(pt_term):
    """Returns full MedDRA hierarchy for a given Preferred Term."""
    entry = MEDDRA_MAP.get(pt_term, {})
    if not entry:
        for key, val in MEDDRA_MAP.items():
            if pt_term.lower() in key.lower():
                entry = val
                break
    return {
        "pt":  pt_term,
        "hlt": entry.get("hlt", "Unknown"),
        "soc": entry.get("soc", "Unknown")
    }