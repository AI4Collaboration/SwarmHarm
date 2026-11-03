"""Access-only subscription snapshots: host credentials never enter fixtures."""
import base64
import json
import time
from unittest import TestCase
from unittest.mock import patch
import pi_subscription

class PiSubscriptionChecks(TestCase):
    def fixture(self, lifetime=9*3600, auth_mode='chatgpt', api_key=None):
        claims={'https://api.openai.com/auth':{'chatgpt_account_id':'fixture-account'},'exp':time.time()+lifetime}
        body=base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
        token='fixture.'+body+'.fixture'
        return json.dumps({'auth_mode':auth_mode,'OPENAI_API_KEY':api_key,
            'tokens':{'access_token':token,'refresh_token':'fixture-refresh-must-not-be-copied'}}),token

    def test_snapshot_excludes_refresh_token_and_rejects_other_auth(self):
        raw,token=self.fixture()
        with patch.object(pi_subscription.Path,'read_text',return_value=raw):
            snapshot=pi_subscription.credential_snapshot()
        self.assertEqual(snapshot['access'],token)
        self.assertEqual(snapshot['refresh'],'')
        self.assertNotIn('fixture-refresh',json.dumps(snapshot))
        for kwargs in ({'lifetime':10},{'auth_mode':'apikey'},{'api_key':'fixture-key'}):
            raw,_=self.fixture(**kwargs)
            with patch.object(pi_subscription.Path,'read_text',return_value=raw):
                with self.assertRaises(RuntimeError):pi_subscription.credential_snapshot()
