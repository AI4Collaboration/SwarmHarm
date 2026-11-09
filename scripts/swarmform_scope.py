"""Select the current delivery scope without changing retained inputs or scores."""
from itertools import product


def selected_cells(ledger, *, all_retained=False):
    matrix = ledger['matrix']
    available = list(product(matrix['deployments'], matrix['encoding_opportunities'], matrix['domains']))
    if all_retained:
        return available
    scope = ledger['delivery_scope']
    primary, generalization = scope['primary_domain'], scope['generalization_domain']
    encodings = scope['generalization_encodings']
    if (primary not in matrix['domains'] or generalization not in matrix['domains']
            or primary == generalization or not isinstance(encodings, list) or not encodings
            or len(set(encodings)) != len(encodings)
            or not set(encodings) <= set(matrix['encoding_opportunities'])):
        raise ValueError('Invalid primary or generalization scope')
    return [cell for cell in available if cell[2] == primary
            or (cell[2] == generalization and cell[1] in encodings)]


def role(ledger, cell):
    deployment, encoding, domain = cell.split('/')
    scope = ledger['delivery_scope']
    if domain == scope['primary_domain']:
        return 'primary'
    if domain == scope['generalization_domain'] and encoding in scope['generalization_encodings']:
        return 'generalization'
    return 'supplemental'
