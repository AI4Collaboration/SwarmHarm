"""Fresh archive lookup handles for each registered Phase 1 cache instance."""

from hashlib import sha256
import hmac
import re
import secrets


INPUT_REVISION = 'wendzel-job-cache-v3'
NONCE_FIELD = 'phase1_archive_instance'
POLICY_FIELD = 'phase1_archive_policy'
HANDLE_FIELDS = {'record_id', 'index_id', 'index_scope', 'retained_scope'}


def register(plan, nonce=None):
    matched = nonce is not None
    nonce = secrets.token_hex(16) if nonce is None else nonce
    if not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{32}', nonce):
        raise ValueError('Invalid archive instance nonce')
    for item in plan.values():
        item[NONCE_FIELD] = nonce
        if matched:
            item[POLICY_FIELD] = 'operator_selected_matched_inputs'
        else:
            item.pop(POLICY_FIELD, None)


def descriptor(plan):
    nonces = {item.get(NONCE_FIELD) for item in plan.values()}
    if nonces == {None}:
        return None
    if len(nonces) != 1:
        raise ValueError('One archive instance is required per rollout')
    nonce = nonces.pop()
    if not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{32}', nonce):
        raise ValueError('Invalid archive instance nonce')
    policies = {item.get(POLICY_FIELD, 'fresh_per_registration') for item in plan.values()}
    if len(policies) != 1 or not policies <= {'fresh_per_registration', 'operator_selected_matched_inputs'}:
        raise ValueError('Inconsistent archive instance policy')
    return {'policy': policies.pop(), 'opaque_bits': 96,
            'namespace_sha256': sha256(bytes.fromhex(nonce)).hexdigest(),
            'bound_fields': sorted(HANDLE_FIELDS)}


def bind_batch(batch, nonce):
    """Bind identifiers in both the public-domain rows and normalized service rows."""
    if nonce is None:
        return batch
    key = bytes.fromhex(nonce)

    def bind(value, field=None):
        if field in HANDLE_FIELDS and value is not None:
            match = re.fullmatch(r'(.+?)([0-9a-f]{24})', value)
            if match is None:
                raise ValueError('Unexpected archive handle format')
            opaque = hmac.digest(key, value.encode(), 'sha256').hex()[:24]
            return match.group(1) + opaque
        if isinstance(value, dict):
            return {name: bind(child, name) for name, child in value.items()}
        if isinstance(value, list):
            return [bind(child) for child in value]
        return value

    return bind(batch)
