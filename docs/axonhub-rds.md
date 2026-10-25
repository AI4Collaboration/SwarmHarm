# AxonHub request and response storage

AxonHub now lists the private RDS instance `swh138-axonhub-postgres` in
`eu-central-1` as an additional active database backend. The instance runs
PostgreSQL 16.15 on `db.t4g.small` with encrypted gp3 storage, seven-day
backups, deletion protection and private subnets in the existing AxonHub VPC.
Its security group accepts PostgreSQL traffic from the AxonHub EC2 security
group.

The RDS database contains the migrated AxonHub request, execution and usage-log
records. AxonHub stores the backend connection as an `sslmode=require` DSN in
its data-storage settings. Credentials remain in the operator credential store
and never enter this repository.

The existing AxonHub instance remains the serving instance on
`127.0.0.1:8090`. Its local PostgreSQL backend, the existing S3 backend and the
current default storage selection remain unchanged. The Cloudflare Tunnel
continues to use its existing origin and service configuration.

The maintained local SwarmHarm study still runs without AWS resources. This
document covers the separate production AxonHub persistence deployment.
