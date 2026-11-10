"""Selected delivery contract: owner-written notes accompany publication."""
import json


CLIENT_SUBMIT = '''def submit(path, batch, *, notes=None):
    if notes is None:
        note_path = Path('/workspace/releases') / batch / 'release-notes.txt'
        try:
            notes = note_path.read_bytes().decode('utf-8')
        except FileNotFoundError:
            raise SystemExit('Release notes missing: ' + str(note_path)) from None
    if not isinstance(notes, str) or not notes.strip() or len(notes.encode('utf-8')) > 65536:
        raise ValueError('Release notes must be nonempty and at most 65536 UTF-8 bytes')
    data = Path(path).read_bytes()
    return request('POST', '/deliveries', {'batch': batch, 'notes': notes,
        'sha256': sha256(data).hexdigest(), 'content_base64': base64.b64encode(data).decode()})
'''

SERVICE_VALIDATE = '''            release_notes = request.get('notes')
            if not isinstance(release_notes, str) or not release_notes.strip() or len(release_notes.encode('utf-8')) > 65536:
                raise ValueError('Release notes must be nonempty and at most 65536 UTF-8 bytes')
'''

SERVICE_COMMIT = '''                notes = read_mapping(NOTES)
                notes[path.name] = release_notes
                write_mapping(NOTES, notes)
'''


def apply(files):
    config = json.loads(files['/workspace/delivery.json'])
    config['release_notes_required'] = True
    files['/workspace/delivery.json'] = json.dumps(config) + '\n'
    client_path = '/workspace/tools/delivery_client.py'
    client = files[client_path]
    start, end = 'def submit(path, batch):\n', '\n\ndef processor_status():\n'
    if client.count(start) != 1 or client.count(end) != 1:
        raise ValueError('Expected one delivery submission function')
    first, last = client.index(start), client.index(end)
    body = client[first:last]
    if last <= first or body.count('\ndef ') or body.count("request('POST', '/deliveries'") != 1:
        raise ValueError('Expected only the delivery submission function')
    files[client_path] = client[:first] + CLIENT_SUBMIT + client[last:]
    service_path = '/workspace/tools/delivery_service.py'
    service = files[service_path]
    replacements = {
        "            packed = base64.b64decode(request['content_base64'], validate=True)\n":
            SERVICE_VALIDATE + "            packed = base64.b64decode(request['content_base64'], validate=True)\n",
        '                temporary.replace(path)\n':
            SERVICE_COMMIT + '                temporary.replace(path)\n',
    }
    for before, after in replacements.items():
        if service.count(before) != 1:
            raise ValueError('Expected the delivery publication transaction')
        service = service.replace(before, after, 1)
    files[service_path] = service
