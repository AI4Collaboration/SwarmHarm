"""Explicit direct route and pushed snapshot remain bounded and independently sealed."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import run
from runtime_evidence_checks import load,Stream

MODEL='openai/gpt-6.1-sol-20260929'
CANONICAL='openai/gpt-6.1-sol'

class ProviderProfileChecks(unittest.TestCase):
    def test_default_profile_keeps_axonhub_and_main(self):
        self.assertEqual(run.API_PROVIDER,'axonhub')
        self.assertEqual(run.COLLECTION_REF,'refs/heads/main')
        self.assertEqual(run.provider_request_fields({}),{})
    def test_direct_catalog_is_checked_without_sending_key_to_axonhub(self):
        with patch.object(run,'API_PROVIDER','openrouter'),patch.object(run,'MODELS',{'sol':MODEL}),patch.object(run,'UPSTREAM_MODELS',{'sol':CANONICAL}),patch.object(run,'catalog',return_value={'model_found':True}) as catalog:
            routes=run.verify_routes(Path('/fixture/private-key'))
        self.assertEqual(catalog.call_count,2)
        self.assertTrue(all(c.args[0].startswith('https://openrouter.ai/') for c in catalog.call_args_list))
        self.assertIn(MODEL,catalog.call_args_list[0].args[0])
        self.assertEqual(routes['api_provider'],'openrouter')
        self.assertFalse(routes['provider_preferences']['allow_fallbacks'])
    def test_missing_direct_route_aborts_before_inference(self):
        with patch.object(run,'API_PROVIDER','openrouter'),patch.object(run,'catalog',return_value={'model_found':False}):
            with self.assertRaisesRegex(RuntimeError,'no inference sent'):run.verify_routes(Path('/fixture/key'))
    def test_collection_reference_requires_a_complete_branch(self):
        self.assertEqual(run.validated_collection_ref('refs/heads/fix/current-runtime-evidence'),'refs/heads/fix/current-runtime-evidence')
        for bad in ('main','HEAD','refs/tags/test','refs/heads/x//y','refs/heads/x y','refs/heads/x;echo'):
            with self.subTest(ref=bad),self.assertRaises(ValueError):run.validated_collection_ref(bad)
    def test_request_routing_comes_from_sealed_registration(self):
        reg={'api_provider':'openrouter','provider_preferences':{'only':['openai'],'allow_fallbacks':False}}
        fields=run.provider_request_fields(reg);fields['provider']['only'].append('other')
        self.assertEqual(reg['provider_preferences']['only'],['openai'])
        self.assertEqual(run.provider_request_fields({'api_provider':'axonhub'}),{})
    def test_model_identity_aliases_are_explicit_and_bounded(self):
        request={'model':MODEL}
        with self.assertRaises(ValueError):run.validate_response_model(request,{'model':CANONICAL})
        run.validate_response_model(request,{'model':CANONICAL},[MODEL,CANONICAL])
        with self.assertRaises(ValueError):run.validate_response_model(request,{'model':'unregistered-model'},[MODEL,CANONICAL])
    def test_direct_transport_preserves_identity_and_requests_routing_metadata(self):
        t=load('transport');t.configure(MODEL,'https://openrouter.ai/api/v1',response_model_aliases=[MODEL,CANONICAL])
        native={'id':'fixture-response','status':'completed','model':CANONICAL,'output':[]}
        with tempfile.TemporaryDirectory() as tmp,patch.object(t,'key',return_value='fixture-secret'),patch.object(t.guardrails,'open_url',return_value=Stream([{'type':'response.completed','response':native}])) as opening:
            self.assertEqual(t.call({'model':MODEL},Path(tmp),'0001'),native)
            headers={k.lower():v for k,v in opening.call_args.args[0].header_items()}
            self.assertEqual(headers['x-openrouter-metadata'],'enabled')
            self.assertEqual(json.loads((Path(tmp)/'0001.response.json').read_text()),native)
    def test_alias_configuration_rejects_unbounded_values(self):
        t=load('transport')
        for aliases in ('any',[],[None]):
            with self.assertRaises(ValueError):t.configure(MODEL,response_model_aliases=aliases)

if __name__=='__main__':unittest.main()
