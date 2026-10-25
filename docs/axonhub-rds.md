# AxonHub request and response storage

The production AxonHub host uses the private RDS instance `swh138-axonhub-postgres`
in `eu-central-1`. The instance runs PostgreSQL 16.15 on `db.t4g.small` with
20 GiB encrypted gp3 storage, seven-day backups, automatic minor upgrades and
deletion protection. Its DB subnet group contains two private subnets in the
existing AxonHub VPC. The RDS security group accepts PostgreSQL traffic only
from the AxonHub EC2 security group.

The existing PostgreSQL data was copied while AxonHub continued serving. The
RDS database contains the request, execution, usage-log, trace, channel-probe,
API-key and configuration records from the source database. A final binary
COPY synchronized rows written during the initial dump, and the affected
sequences were advanced to their current maxima.

The live route uses a sidecar container named `swarmharm-axonhub-rds-1` with
the same AxonHub image and an RDS `sslmode=require` DSN. It listens on
`127.0.0.1:8091`. A persistent systemd unit inserts an OUTPUT redirect from
`127.0.0.1:8090` to port `8091`; the existing Cloudflare Tunnel continues to
use its configured origin address while traffic reaches the RDS-backed sidecar.
The original AxonHub container and local database remain available as a
rollback copy.

Verification checks cover RDS availability, TLS database connectivity, equal
row counts for request and response records, AxonHub health, initialization,
administrator sign-in and the enabled route unit. Credentials remain in the
operator credential store and never enter this repository.

The maintained local SwarmHarm study still runs without AWS resources. This
document covers the separate production AxonHub persistence deployment.
