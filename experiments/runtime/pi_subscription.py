"""Host-only, access-token-only Pi subscription authentication; never API fallback."""
import base64
import json
import os
from pathlib import Path
import subprocess
import time


def credential_snapshot(minimum_validity_seconds=8 * 3600):
    """Use the existing Codex login without rotating or copying its refresh token."""
    path = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'auth.json'
    try:
        value = json.loads(path.read_text())
        token = value['tokens']['access_token']
        part = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        account = claims['https://api.openai.com/auth']['chatgpt_account_id']
        expires = claims['exp']
        if value.get('auth_mode') != 'chatgpt' or value.get('OPENAI_API_KEY'):
            raise ValueError('Wrong authentication kind')
        if expires - time.time() < minimum_validity_seconds:
            raise ValueError('Insufficient token lifetime')
        return {'type': 'oauth', 'access': token, 'refresh': '',
                'expires': expires * 1000, 'accountId': account}
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        raise RuntimeError('A current Codex ChatGPT subscription login with eight hours validity is required') from None


def catalog():
    """Check pinned Pi catalog/auth resolution; a completed turn still verifies entitlement."""
    from pi_agent import PI_DIR, node_binary
    script = '''
import { ModelRuntime } from '@earendil-works/pi-coding-agent';
import { subscriptionCredentials } from './subscription-auth.mjs';
const credential = JSON.parse(process.env.SWARMHARM_PI_SUBSCRIPTION);
delete process.env.SWARMHARM_PI_SUBSCRIPTION;
const runtime = await ModelRuntime.create({credentials:subscriptionCredentials(credential), modelsPath:null,allowModelNetwork:false,refreshOnCreate:false});
const model = runtime.getModel('openai-codex','gpt-6.1-sol');
const auth = await runtime.getAuth(model);
if (!auth || model.provider !== 'openai-codex' || model.api !== 'openai-codex-responses') process.exit(2);
console.log(JSON.stringify({id:model.id,api:model.api,provider:model.provider,base_url:model.baseUrl,context_window:model.contextWindow,thinking_levels:model.thinkingLevelMap,authenticated_snapshot:true,model_entitlement_verified:false}));
'''
    env = {'PATH': os.environ.get('PATH', ''),
           'SWARMHARM_PI_SUBSCRIPTION': json.dumps(credential_snapshot())}
    result = subprocess.run([node_binary(), '--input-type=module', '-e', script],
                            cwd=PI_DIR, env=env, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Pinned Pi subscription catalog/auth check failed; no alternate route attempted')
    return json.loads(result.stdout)
