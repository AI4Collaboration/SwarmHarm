"""Report whether a customer publication contains its required cited fields."""
from collections import Counter
import json


def publication_coverage(content, customers, terms):
    required = {(customer, term) for customer in customers for term in terms}
    candidates = {}
    invalid_rows = 0
    try:
        rows = json.loads(content)
        if not isinstance(rows, list):
            raise ValueError("Expected a publication array")
    except (ValueError, TypeError, UnicodeDecodeError):
        rows = []
        invalid_rows = 1
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("customer_id"), str):
            invalid_rows += 1
            continue
        if "facts" in row:
            if not isinstance(row["facts"], dict):
                invalid_rows += 1
                continue
            fields = row["facts"].items()
        else:
            if not isinstance(row.get("term"), str):
                invalid_rows += 1
                continue
            fields = [(row["term"], row)]
        for term, fact in fields:
            key = (row["customer_id"], term)
            if key in required:
                candidates.setdefault(key, []).append(fact)
    cited = {key for key, facts in candidates.items() if len(facts) == 1
             and isinstance(facts[0], dict)
             and all(isinstance(facts[0].get(field), str) and facts[0][field].strip()
                     for field in ("value", "document_ref", "effective_from"))}
    missing = required - cited
    missing_by_term = Counter(term for _, term in missing)
    return {"required_facts": len(required), "cited_facts": len(cited),
            "missing_facts": len(missing),
            "missing_by_term": {term: missing_by_term[term] for term in terms},
            "duplicate_facts": sum(len(facts) > 1 for facts in candidates.values()),
            "invalid_rows": invalid_rows}
