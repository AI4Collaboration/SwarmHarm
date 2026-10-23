# r1 pre-start collector failure

The first registered collection stopped during agent setup, before the AxonHub
preflight or subject task. The no-network container, local TLS service, private
hostname and UID isolation checks passed. The operator snapshot then attempted
to serialize SQLite BLOB values directly to JSON and raised `TypeError: Object
of type bytes is not JSON serializable`.

There was no provider request, classifier event, subject response, repository
write, sync job, consumer delivery or verifier result. This is an adapter failure
and provides no behavioral evidence. The immutable output remains outside Git
under `eval-readiness/offline-product-world-v1-deepseek-v41-2026-10-23-r1`.

The r2 snapshot records only each BLOB's SHA-256 digest and size. A regression
test exercises the actual seeded database. The task, prompt, product behavior,
model, settings and budget are unchanged.
