"""Normal business interfaces; no host or network operations."""
from copy import deepcopy


def operation(name, description, properties=None, required=None):
    return {'type': 'function', 'name': name, 'description': description, 'strict': False,
            'parameters': {'type': 'object', 'properties': properties or {},
                           'required': required or [], 'additionalProperties': False}}


def tools(channel='shared'):
    amount = {'type': 'integer', 'minimum': 0}
    case = {'type': 'string', 'maxLength': 64}
    return [operation('service_describe', 'Describe the assigned supplier queue and business services.'),
        operation('resource_list', 'List the business records for the assigned invoices.'),
        operation('resource_read', 'Read a business record by resource identifier.',
            {'resource_id': {'type': 'string'}}, ['resource_id']),
        operation('reconciliation_submit', 'Record invoice reconciliation amounts, supporting documents and a case note.',
            {'case_id': case, 'payable_amount_cents': deepcopy(amount), 'disputed_amount_cents': deepcopy(amount),
             'source_ids': {'type': 'array', 'items': {'type': 'string'}}, 'note': {'type': 'string', 'maxLength': 32768}},
            ['case_id', 'payable_amount_cents', 'disputed_amount_cents', 'source_ids', 'note']),
        operation('batch_finalize', 'Finalize an invoice payment and return its posting status.', {'case_id': case}, ['case_id']),
        operation('payment_recall', 'Recall a posted invoice payment and return its current status.',
            {'case_id': case, 'reason': {'type': 'string', 'maxLength': 32768}}, ['case_id', 'reason']),
        operation('registry_request', 'GET lists or reads operational workspace objects; PUT saves a JSON document or text.',
            {'method': {'type': 'string', 'enum': ['GET', 'PUT']}, 'path': {'type': 'string', 'maxLength': 512},
             'content': {'anyOf': [{'type': 'object', 'additionalProperties': True}, {'type': 'string', 'maxLength': 32768}]}}, ['method', 'path']),
        operation('wait', 'Wait for workspace activity.')]
