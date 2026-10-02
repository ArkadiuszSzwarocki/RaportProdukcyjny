# Automatic AGRO label recovery

Automatic pallet registration requests two label copies. The wrapper does not trigger printing.

## Schema update

Run the normal application schema migration, or run `scripts/migrations/ensure_auto_label_recovery.py` against the intended database before starting the updated background workers. The migration adds `auto_label_state` to pallet tables and a nullable unique `job_key` to `print_jobs`. It does not change table storage engines or request labels for existing pallets.

## Recovery

The automatic registration stores `pending` label intent in the same pallet row as its weight and identifier. The recovery worker uses the registration lock and creates a print job with key `auto-label:AGRO:<pallet id>`. It commits that job before changing the pallet intent to `queued`.

If preparation or queue insertion fails, intent remains pending. If the process stops after job commit, the next worker reuses the job with that key. Recovery does not register another pallet or change produced weight. Completed intent remains queued even after old print jobs are removed.

## Uncertain sends

A send that may already have reached the printer must not be repeated automatically. Interrupted printing jobs older than five minutes and pending jobs untouched for 48 hours become errors requiring review. Bulk retry excludes uncertain results. Individual retry requires confirmation after checking the physical labels and accepts only error jobs. A confirmed retry updates the job activity time so older jobs can be processed.

The print bridge's acknowledgement means the send was accepted; it does not confirm a physical label. Background workers remain disabled in the isolated local test environment. Test registration and recovery through mocks before testing with a real printer.
