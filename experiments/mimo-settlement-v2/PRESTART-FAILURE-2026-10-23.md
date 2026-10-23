# Pre-start collector failure

Registration r1 stopped before `started.json`, Docker setup or any model call.
The runner called a credential-validation helper that is not exposed by the
transport wrapper. The registered `configure` call already performs host-only
credential setup; r2 removes the unsupported call. No behavioral evidence or
trajectory exists for r1.
