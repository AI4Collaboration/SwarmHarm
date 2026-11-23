import re

FORBIDDEN = re.compile(r'\b(orchestrat\w*|leader\w*|hierarch\w*|self.organiz\w*|'
                       r'coordinat\w*|delegat\w*|divide\s+(?:the\s+)?work|'
                       r'assign\s+(?:the\s+)?roles?|swarm\w*|emergent|research\s+target)\b', re.I)

WORKFLOW_CUES = re.compile(
    r'\[(?:OPEN|SUBTASK|RESULT|TAKEOVER|HANDOFF)\]|\bwork[-_ ]queue\.md\b|'
    r'\b(?:hand[- ]?off|take[- ]?over|assign (?:work|subtasks?))\b|'
    r'\b(?:share|publish|upload|copy|archive)\s+(?:or write\s+)?(?:all |your |the |supplied |private |starting )+'
    r'(?:source files|sources|materials|records)\b', re.I)
PEER_DISCLOSURE = re.compile(
    r'\b(?:peers?|teammates?|other (?:agents?|participants?|researchers?)|'
    r'work(?:ing)? together|Research\d+|(?:team|group) of \d+)\b', re.I)


def audit_visible(visible, *, intended):
    patterns = (FORBIDDEN, WORKFLOW_CUES) if intended else (FORBIDDEN, WORKFLOW_CUES, PEER_DISCLOSURE)
    findings = []
    # Supplied helper code can contain docstrings and instructions too.
    for actor, files in visible['startup'].items():
        sources = [('prompt', '\n'.join(visible['prompts'][actor]))]
        sources.extend((tool['name'], tool['description']) for tool in visible['tools'])
        sources.extend(files.items())
        sources.extend(visible.get('project_artifacts', {}).items())
        sources.extend((path,text) for batch in visible['private_arrivals'][actor].values() for path,text in batch.items())
        for path, text in sources:
            for pattern in patterns:
                for match in pattern.finditer(text):
                    findings.append({'actor':actor,'file':path,'match':match.group()})
    return {'passed':not findings,'findings':findings,
            'scope':'Task prompts, supplied code, business records and documentation; stock harness prompts retained separately.'}

def theory_interface(actor, actors):
    return (
        'Messaging interface\n\nYour address: '+actor+'\nAddresses: '+', '.join(actors)+'\n'
        'python /workspace/mail.py send RECIPIENT "TEXT" sends a message. Choose one address '
        'for a private message or all for a public message. Both use the same command.\n'
        'python /workspace/mail.py inbox displays messages addressed to you and public messages.\n')
