import json

def compile_reference(records):
    # Operator-only executable witness. Expected outputs come from the independently
    # constructed frame/probe pairs, not from this implementation.
    source = "import json\nfrom decimal import Decimal\nT = json.loads(" + repr(json.dumps({str(k):v for k,v in records.items()})) + ")\n"
    source += """
def decode(frame_hex):
    frame = bytes.fromhex(frame_hex)
    if len(frame) != 9:
        raise ValueError('A measurement frame has nine bytes')
    identifier = int.from_bytes(frame[:2], 'big')
    spec = T[str(identifier)]
    value = int.from_bytes(frame[4:8], spec['byte_order'], signed=spec['signed'])
    return {'type_id': identifier, 'sequence': int.from_bytes(frame[2:4], 'big'),
        'reading': format(Decimal(value)*Decimal(spec['scale'])+Decimal(spec['offset']), '.2f'),
        'unit': spec['unit'], 'status': spec['states'][str(frame[8])]}
"""
    return source

def loaded_reference(records):
    namespace = {}
    exec(compile_reference(records), namespace)
    return namespace['decode']
