Verified 21 October 2026 through public HTTPS with the shared campaign credential.

The campaign uses `deepseek/deepseek-v4.1-flash-1017` on AxonHub channel 12,
`OpenRouter DeepSeek Flash 1017`, through `/v1/chat/completions`. Stock Pi uses
`api=openai-completions`, `reasoning=true`,
`compat.supportsDeveloperRole=false`, `compat.thinkingFormat=openrouter`, and
thinking level `high`. The captured request contains `reasoning:{effort:high}`.

The meta host runs an additive ingress filter. The campaign credential is a
bearer alias mapped to one private native AxonHub key. The native key profile
allows channel 12 and the exact model. Its scope is `write_requests`.
The filter permits POST Chat Completions, client function tools, and the
registered reasoning setting. Other routes, model names, and hosted-tool
settings receive policy responses. Ordinary gateway traffic passes through
nginx directly to the existing AxonHub listener.

The alias receives authentication responses at the native listener. This
property keeps the route policy effective across direct-native attempts and
connections opened before the filter was installed. Cloudflared and AxonHub
continue with their existing process lifecycles.

Operator retrieval uses the existing SSH identity and sudo:

```bash
ssh -i .operator/private/swh6-ed25519 ubuntu@63.186.173.73 'sudo cat /opt/swarmharm/swh119/key.json'
```

Store that output in a private operator file with mode 0600. Fields are `key`,
`base_url`, `model`, `reasoning_effort`, and `api_key_id`. Provide `key` through
the ordinary Pi provider configuration on each runtime.

Real verification:

```bash
python3 gateway-verify.py --key-file /path/to/private/key.json --output /path/to/private/evidence.json
```

The verification calls a client function that returns the operator machine's
actual hostname and checks that the model uses the result in its answer. The
public route returned HTTP 200 for both model calls. Responses, Anthropic,
model listing, another model, a hosted tool, and a hosted plugin each returned
HTTP 403.

Gateway artifacts on the meta host:

| Path | Purpose |
| --- | --- |
| `/opt/swarmharm/swh119/key.json` | Shared campaign credential, root 0600 |
| `/opt/swarmharm/swh119/backend.json` | Private native credential, root 0600 |
| `/opt/swarmharm/swh119/native-scope.json` | Sanitized active native profile |
| `/etc/swh119-gateway/credentials.json` | Policy service credential mapping |
| `/var/lib/swh119-gateway/requests.jsonl` | Private exact forwarded request bodies with time and trace UUID |
| `/etc/nginx/conf.d/swh119-gateway.conf` | Loopback ingress and campaign selection |
| `/usr/local/lib/swh119-gateway-policy.py` | JSON policy service |
| `swh119-gateway-policy.service` | Policy listener on 127.0.0.1:8093 |
| `swh119-gateway-diversion.service` | Tagged loopback NAT rule to nginx 8092 |

The loopback NAT rule applies to port 8090, with UID 33 exempt for nginx and
the policy service. It carries comment `swh119-gateway`. The policy forwards
each accepted request with an `AH-Trace-Id` UUID. Native AxonHub records that
UUID in `trace.traceID`. The policy archives each complete response as
`<uuid>.response` and appends its HTTP status and native request identifier to
`completions.jsonl`.

Upload `gateway-export.py` to the meta host and run it through sudo to export
native campaign metadata and bodies. The query filters by the dedicated native
key and supports pagination:

```bash
sudo python3 gateway-export.py --output /opt/swarmharm/swh119/requests.json --bodies
```

Each trial exports records for its dedicated proxy's public IP. Use the actual
IP from the provisioned trial manifest:

```bash
sudo python3 /home/ubuntu/gateway-export.py --source-ip PROXY_PUBLIC_IP --since 2026-10-21T23:10:00Z --output /opt/swarmharm/swh119/TRIAL_ID.json --bodies
```

The output contains `forwarded`, `completions`, and native `requests` arrays.
Native queries select the exact forwarded trace UUIDs for that proxy. The
export copies response bytes to the sibling `TRIAL_ID-responses` directory.
Fetch the JSON file and response directory together. The authoritative source
IP is the `CF-Connecting-IP` header supplied by Cloudflare. Per-subject filtering
uses actual subject IDs in the captured system-role runtime instructions.

`gateway-evidence.py` verifies an export against the approved attachment and
an operator-provided exact task file. It checks the attachment's SHA-256 and
complete prefix in system-role messages, the exact initial user message,
completed native requests on the registered model/channel, actual client tool
calls with matching returned results, and archived HTTP 200 responses:

```bash
python3 gateway-evidence.py --export TRIAL_ID.json --output evidence-check.json --system-file infinite-gen-4.md --subject-id SUBJECT_UUID --initial-task-file exact-task.txt --expect-tool-output ACTUAL_HOSTNAME
```

The verifier reads streaming responses with `httpx-sse==0.4.3` and
`httpx==0.28.1`. The operator preflight exercised it against a real function
roundtrip and the actual machine hostname.

Run `gateway-auth-audit.py` as UID 33 on the meta host to probe the native
listener through the explicit NAT exemption. It exercises the campaign alias
across inference paths, alternate auth headers, and query parameters. Each
probe requires an HTTP client response in the 400 range.

Fetch this export and `requests.jsonl` through authenticated operator SSH. Keep
raw request and response bodies in private campaign storage.

After every trial releases the shared key, run `gateway-revoke.py` on the meta
host through sudo. This disables the native key and rotates the alias mapping.
Then stop and disable `swh119-gateway-diversion.service` and
`swh119-gateway-policy.service`. The diversion service removes its exact tagged
NAT rule. Remove the owned nginx configuration and reload nginx. Archive private
request evidence under the campaign's access controls.

Runtime dependencies: Ubuntu's `python3-aiohttp` package 3.9.1-1ubuntu0.1,
`requests`, nginx, and iptables. Source scripts use the installed libraries for
JSON, HTTP, streaming, and GraphQL transport.
