# modules/naranjo_calculator.py
# MODULE 6: Naranjo Adverse Drug Reaction Probability Scale

NARANJO_QUESTIONS = [
    ("Q1",  "Previous conclusive reports of this reaction?",             +1,  0, 0),
    ("Q2",  "ADR appeared after the suspected drug was given?",          +2, -1, 0),
    ("Q3",  "Improved after drug was stopped or antidote given?",        +1,  0, 0),
    ("Q4",  "Reaction reappeared when drug was re-administered?",        +2, -1, 0),
    ("Q5",  "Alternative causes that could have caused the reaction?",   -1, +2, 0),
    ("Q6",  "Did the same symptom happen after you took a dummy pill with no medicine?", -1, +1, 0),
    ("Q7",  "Drug detected in toxic concentration in blood/urine?",      +1,  0, 0),
    ("Q8",  "Reaction more severe when dose increased?",                 +1,  0, 0),
    ("Q9",  "Similar reaction to same/related drug before?",             +1,  0, 0),
    ("Q10", "Adverse event confirmed by objective evidence?",            +1,  0, 0),
]


def calculate_naranjo(answers):
    """
    answers: dict like { "Q1": "yes", "Q2": "no", "Q3": "unknown", ... }
    Returns: { "score": int, "category": str }
    Categories: Definite(>=9), Probable(5-8), Possible(1-4), Doubtful(<=0)
    """
    total = 0
    for q_id, _, yes_s, no_s, unk_s in NARANJO_QUESTIONS:
        ans = answers.get(q_id, "unknown").lower()
        if ans == "yes":     total += yes_s
        elif ans == "no":    total += no_s
        else:                total += unk_s

    if total >= 9:   category = "Definite"
    elif total >= 5: category = "Probable"
    elif total >= 1: category = "Possible"
    else:            category = "Doubtful"

    return {"score": total, "category": category}
