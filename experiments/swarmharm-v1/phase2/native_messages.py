"""Message-content projection for explicitly registered native record formats.

Observer captures always retain original bytes. This projection changes neither
the native file nor the model context. Claude user entries include tool results;
assistant entries include tool requests. Attachments and goal metadata are not
conversation messages, matching the Pi condition's metadata exclusion.
"""


def conversation_row(row):
    if not isinstance(row, dict):
        raise ValueError('Native record entry is not an object')
    if row.get('type') in ('user', 'assistant'):
        if not isinstance(row.get('uuid'), str) or not isinstance(row.get('message'), dict):
            raise ValueError('Invalid Claude conversation entry')
        return {'type': 'message', 'id': row['uuid'], 'message': row['message']}
    return row
