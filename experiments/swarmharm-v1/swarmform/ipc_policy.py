"""Registered System V IPC identities and object access modes."""

def access_policy(profile, *, request_group_write=False):
    if profile not in ('content', 'metadata', 'state', 'events', 'timing'):
        raise ValueError('Unknown processor identity profile')
    if type(request_group_write) is not bool:
        raise ValueError('Declare whether the delivery group may submit requests')
    if request_group_write and profile not in ('metadata', 'timing'):
        raise ValueError('Delivery group requests require distinct metadata or timing owners')
    identities = [65534] * 3 if profile == 'content' else [62000, 62001, 62002]
    groups = [63000] * 3 if profile == 'timing' or request_group_write else identities[:]
    return {
        'business_account_ids': identities,
        'business_group_ids': groups,
        'queue_permissions': '0620' if request_group_write else ('0644' if profile == 'events' else '0600'),
        'reply_queue_permissions': '0620' if request_group_write else '0600',
        'status_permissions': '0620' if profile == 'timing' else ('0644' if profile == 'state' else '0600'),
    }
