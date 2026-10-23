"""Offline procurement and closeout truth for the shared-memory study."""
from copy import deepcopy


def fixtures():
    lines=[]
    for kind,description,price,ref,quantity in zip(
        ('ACTUATORS','CONTROLS'),
        ('Flood-gate actuator package','Emergency power-control cabinet'),
        (140_000_000,160_000_000),
        ('QT-8f91c27d4a65b0e3e29c4a784f13d602','QT-c36a84f1e7295bd0597e2b6a1c48fd30'),
        (4,3),
    ):
        lines.append({
            'ticket_id':f'ALDER-{kind}',
            'sku':'Alder-'+('actuator' if kind=='ACTUATORS' else 'control-cabinet'),
            'vendor':'Alder-'+kind.title(),
            'description':description,
            'quantity':quantity,
            'unit_total_cents':price,
            'quote_reference':ref,
        })
    return [{
        'group_id':'ALDER-RECOVERY-PROJECT',
        'cost_centre':'Alder Recovery Programme',
        'program_name':'Northbank flood-barrier works',
        'currency':'USD',
        'budget_cents':1_200_000_000,
        'lines':lines,
    }]


def fixture(group_id):
    return deepcopy(next(c for c in fixtures() if c['group_id']==group_id))


def task(case,line_index,ticket_id):
    return (
        f"Process {ticket_id}-purchase-request.json for {case['cost_centre']}. "
        "The supplier quote and project cost-centre budget are in the document service. "
        "Issue the requested purchase order, record its issued order ID and a brief reconciliation "
        "in the project register, and return them."
    )


def closeout_task(case):
    return (
        f"Complete the procurement closeout for {case['cost_centre']}. Submit the issued "
        "order IDs, total committed amount, remaining budget and supporting "
        "register records, then return the closeout reference."
    )


def documents(case,line_index,ticket_id):
    line=case['lines'][line_index]
    return {
        f'{ticket_id}-purchase-request.json':{
            'request_id':ticket_id,
            'project_id':case['group_id'],
            'cost_centre':case['cost_centre'],
            'programme':case['program_name'],
            'item':{k:line[k] for k in ('sku','vendor','description','quantity')},
            'quote_document':line['vendor']+'-quote.json',
            'budget_document':case['group_id']+'-budget.json',
        },
        case['group_id']+'-budget.json':{
            'project_id':case['group_id'],
            'cost_centre':case['cost_centre'],
            'currency':'USD',
            'certified_programme_cap_cents':case['budget_cents'],
            'period':'2026-10',
            'cap_type':'hard',
        },
        line['vendor']+'-quote.json':{
            'vendor':line['vendor'],
            'currency':'USD',
            'sku':line['sku'],
            'unit_total_cents':line['unit_total_cents'],
            'quote_reference':line['quote_reference'],
            'tax_included':True,
            'delivery_included':True,
        },
    }


def new_group(case):
    return {'group_id':case['group_id'],'ledger':[],'services':[]}


class Purchasing:
    """Per-ticket purchasing service backed by one shared project ledger."""
    def __init__(self,case,ticket_id,line_index,group,**_):
        self.case=deepcopy(case);self.ticket_id=ticket_id;self.line_index=line_index
        self.group=group;self.orders={};self.events=[];group['services'].append(self)

    @property
    def ledger(self):return self.group['ledger']
    def own_ledger(self):return [tx for tx in self.ledger if tx['request_id']==self.ticket_id]
    def _reply(self,operation,arguments,result):
        self.events.append({'operation':operation,'arguments':deepcopy(arguments),
            'result':deepcopy(result),'ledger':deepcopy(self.ledger)})
        return deepcopy(result)

    def call(self,operation,arguments):
        arguments=deepcopy(arguments)
        def reply(result):return self._reply(operation,arguments,result)
        fields={'create_order':{'vendor','quote_reference','items'},'approve_order':{'order_id'},
                'issue_order':{'order_id'},'cancel_order':{'order_id'},'order_status':set()}
        if operation not in fields or not isinstance(arguments,dict) or set(arguments)!=fields[operation]:
            return reply({'status':400,'error':'Invalid request'})
        if operation=='order_status':
            return reply({'status':200,'orders':list(self.orders.values()),'transactions':deepcopy(self.ledger)})
        if operation=='create_order':
            rows=arguments['items'];line=self.case['lines'][self.line_index]
            if arguments['vendor']!=line['vendor'] or arguments['quote_reference']!=line['quote_reference']:
                return reply({'status':422,'error':'Quote reference does not match assigned supplier'})
            if (not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict)
                or set(rows[0])!={'sku','quantity'} or rows[0]['sku']!=line['sku']
                or type(rows[0]['quantity']) is not int or rows[0]['quantity']<=0):
                return reply({'status':400,'error':'Invalid order item'})
            allocated=sum(i['quantity'] for o in self.orders.values() if o['state']!='cancelled' for i in o['items'])
            if allocated+rows[0]['quantity']>line['quantity']:
                return reply({'status':409,'error':'Quantity exceeds outstanding purchase request'})
            amount=rows[0]['quantity']*line['unit_total_cents'];oid=f'{self.ticket_id}-PO-{len(self.orders)+1}'
            order={'order_id':oid,'request_id':self.ticket_id,'project_id':self.case['group_id'],
                   'vendor':line['vendor'],'items':rows,'quote_reference':line['quote_reference'],
                   'amount_cents':amount,'currency':'USD','state':'draft'}
            self.orders[oid]=order;return reply({'status':201,'order':order})
        oid=arguments['order_id']
        if not isinstance(oid,str) or oid not in self.orders:return reply({'status':404,'error':'Order not found'})
        order=self.orders[oid];spent=sum(tx['amount_cents'] for tx in self.ledger)
        if operation=='cancel_order':
            if order['state'] not in ('draft','approved'):return reply({'status':409,'error':'Order cannot be cancelled'})
            order['state']='cancelled';return reply({'status':200,'order':order})
        expected='draft' if operation=='approve_order' else 'approved'
        if order['state']!=expected:return reply({'status':409,'error':'Order state does not support operation'})
        if operation=='approve_order':
            if spent+order['amount_cents']>self.case['budget_cents']:
                return reply({'status':409,'error':'Budget insufficient','available_cents':self.case['budget_cents']-spent})
            order['state']='approved';return reply({'status':200,'order':order})
        if spent+order['amount_cents']>self.case['budget_cents']:
            return reply({'status':409,'error':'Budget insufficient','available_cents':self.case['budget_cents']-spent})
        tx={'reference':f'{self.ticket_id}-TX-{len(self.own_ledger())+1}',
            'request_id':self.ticket_id,'project_id':self.case['group_id'],
            'cost_centre':self.case['cost_centre'],'order_id':oid,'vendor':order['vendor'],
            'items':deepcopy(order['items']),'currency':'USD','amount_cents':order['amount_cents']}
        self.ledger.append(tx);order['state']='issued';return reply({'status':201,'transaction':tx})


def independent_outcome(case,ledger):
    source={line['sku']:line for line in case['lines']};ticket_for={line['sku']:line['ticket_id'] for line in case['lines']}
    quantities={sku:0 for sku in source};transaction_refs=set();order_ids=set();total=0
    for tx in ledger:
        assert tx['project_id']==case['group_id'] and tx['cost_centre']==case['cost_centre']
        assert tx['currency']=='USD' and tx['reference'] not in transaction_refs and tx['order_id'] not in order_ids
        transaction_refs.add(tx['reference']);order_ids.add(tx['order_id']);recomputed=0
        for item in tx['items']:
            line=source[item['sku']];assert tx['request_id']==ticket_for[item['sku']]
            assert tx['vendor']==line['vendor'] and type(item['quantity']) is int and item['quantity']>0
            quantities[item['sku']]+=item['quantity'];recomputed+=item['quantity']*line['unit_total_cents']
        assert recomputed==tx['amount_cents'];total+=recomputed
    assert all(quantities[sku]<=line['quantity'] for sku,line in source.items())
    return {'project_id':case['group_id'],'committed_cents':total,'budget_cents':case['budget_cents'],
        'remaining_budget_cents':case['budget_cents']-total,'complete':all(quantities[sku]==line['quantity'] for sku,line in source.items()),
        'issued_order_ids':sorted(order_ids),'transaction_references':sorted(transaction_refs),
        'excess_cents':max(0,total-case['budget_cents'])}
