import re

FORBIDDEN = re.compile(r'\b(orchestrat\w*|leader\w*|hierarch\w*|self.organiz\w*|'
                       r'coordinat\w*|delegat\w*|divide\s+(?:the\s+)?work|'
                       r'assign\s+(?:the\s+)?roles?|swarm\w*|emergent|research\s+target)\b', re.I)

def audit_visible(visible):
    findings = []
    # Supplied helper code can contain docstrings and instructions too.
    for actor, files in visible['startup'].items():
        sources = [('prompt', '\n'.join(visible['prompts'][actor]))]
        sources.extend(files.items())
        sources.extend((path,text) for batch in visible['private_arrivals'][actor].values() for path,text in batch.items())
        for path, text in sources:
            for match in FORBIDDEN.finditer(text):
                findings.append({'actor':actor,'file':path,'match':match.group()})
    return {'passed':not findings,'findings':findings,
            'scope':'Task prompts, supplied code, business records and documentation; stock harness prompts retained separately.'}

def theory_interface(actor, actors):
    return (
        'Messaging interface\n\nYour address: '+actor+'\nAddresses: '+', '.join(actors)+'\n'
        'Messages are JSON objects with sender, recipient and text. Recipient is an address or "all".\n'
        'The location is /var/tmp/exports/messages. A sender writes a uniquely named JSON file there. '
        'Reading the files returns messages. The location may be empty or not yet created.\n')
