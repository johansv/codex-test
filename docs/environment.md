# Environment Configuration

List required environment variables and rotation procedures.

- `REQFLOW_REQUIRE_APPROVAL` (default `true`): require mark-done commands to provide `--approval-source` or set `--override-wait-for-approval`.
- `assets/config/approval-policy.toml`: default wait-for-approval toggle when the env var is unset.
