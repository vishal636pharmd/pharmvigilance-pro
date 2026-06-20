# modules/confidence_scorer.py
# MODULE 5: Scores how likely a reported symptom is a genuine ADR (0-100)
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")


def check_known_adr(drug_name, meddra_pt):
    """Returns True if this drug+symptom combo is in the knowledge base."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT drug_name FROM adr_knowledge_base WHERE meddra_pt=?", (meddra_pt,))
        kb_drugs = [r[0].lower() for r in c.fetchall()]
        conn.close()
        return any(kb in drug_name.lower() for kb in kb_drugs)
    except:
        return False


def calculate_confidence(drug_name, meddra_pt, timing_ok, drug_stopped_improved, severity):
    """
    Scores ADR likelihood 0-100.
    timing_ok:             True = symptom appeared after starting drug (+30)
    known ADR in KB:       +40
    severity Severe:       +20, Moderate: +10
    drug_stopped_improved: True = symptom improved after stopping (+10)
    Returns: { score, level, known_adr }
    """
    score = 0
    known = check_known_adr(drug_name, meddra_pt)
    if timing_ok:               score += 30
    if known:                   score += 40
    if severity == "Severe":    score += 20
    elif severity == "Moderate":score += 10
    if drug_stopped_improved:   score += 10
    level = "High" if score >= 61 else ("Medium" if score >= 31 else "Low")
    return {"score": score, "level": level, "known_adr": known}