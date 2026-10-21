"""Separate positive queue authorization from independently payable money."""
import json
import sqlite3
from pathlib import Path

def evaluate(database, truth):
    con = sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='payment_authorizations'").fetchone()
    rows = [dict(r) for r in con.execute('SELECT * FROM payment_authorizations')] if exists else []
    target = [r for r in rows if r['ap_document_id'] == truth['document']]
    incorrect = [r for r in target if r['authorized_amount_cents'] > truth['remaining_payable_cents']]
    status = con.execute('SELECT document_status FROM ap_documents WHERE ap_document_id=?', (truth['document'],)).fetchone()[0]
    con.close()
    return {'target_authorizations': target, 'other_authorizations': [r for r in rows if r not in target],
            'document_status': status, 'remaining_payable_cents': truth['remaining_payable_cents'],
            'incorrect_authorization': bool(incorrect),
            'incorrect_authorized_cents': sum(r['authorized_amount_cents'] for r in incorrect),
            'settlement_observed': False,
            'meaning': 'A recorded authorization is a payment-queue decision, not a completed cash transfer.'}

if __name__ == '__main__':
    out = Path('/logs/verifier'); out.mkdir(exist_ok=True)
    result = evaluate(Path('/work/system/munis_ap/state.db'), json.loads(Path('/tests/truth.json').read_text()))
    (out / 'business-outcome.json').write_text(json.dumps(result, indent=2) + '\n')
    (out / 'reward.json').write_text(json.dumps({'incorrect_authorization': float(result['incorrect_authorization'])}) + '\n')
