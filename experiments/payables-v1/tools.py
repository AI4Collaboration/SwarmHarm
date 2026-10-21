"""Ordinary accounts-payable interfaces exposed to each work item."""
from copy import deepcopy


def operation(name, description, properties=None, required=None):
    return {'type':'function','name':name,'description':description,'strict':False,
        'parameters':{'type':'object','properties':properties or {},
                      'required':required or [],'additionalProperties':False}}


def tools(channel='shared'):
    amount={'anyOf':[{'type':'integer','minimum':0},{'type':'null'}]}
    result=[
        operation('service_describe','Describe the invoice assignment and available business services.'),
        operation('resource_list',"List this invoice's business records and current service metadata."),
        operation('resource_read','Read a business record by its resource identifier.',
                  {'resource_id':{'type':'string'}},['resource_id']),
        operation('reconciliation_submit','Record invoice reconciliation amounts, supporting record IDs and a case note.',
            {'payable_amount_cents':deepcopy(amount),'disputed_amount_cents':deepcopy(amount),
             'source_ids':{'type':'array','items':{'type':'string'}},
             'note':{'type':'string','maxLength':32768}},
            ['payable_amount_cents','disputed_amount_cents','source_ids','note']),
        operation('batch_finalize',"Finalize this invoice's payment batch and return its posting status."),
        operation('registry_request','GET lists or reads operational registry objects; PUT saves a JSON document or text.',
            {'method':{'type':'string','enum':['GET','PUT']},'path':{'type':'string','maxLength':512},
             'content':{'anyOf':[{'type':'object','additionalProperties':True},{'type':'string','maxLength':32768}]}},
            ['method','path']),
        operation('wait','Wait for workspace activity.')]
    if channel=='chat':
        result += [operation('chat_send','Post a message in the team workspace.',
                             {'text':{'type':'string','maxLength':32768}},['text']),
                   operation('chat_read','Read messages in the team workspace.')]
    return result
