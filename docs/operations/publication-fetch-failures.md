# Publication fetch failures (#661)

The active-publication watcher makes one request. HTTP 500 means the remote
server returned an error, not that the tunnel failed or that the error is
known to be transient. The command exits 1 with a short status-only diagnostic.
Transport failures also exit 1. Neither path retries or writes the output.
The workflow therefore never diffs or stages a failed response as a baseline.

Challenge/denial/redirect handling stays a hard stop with exit 2 and no retry.
Do not rerun a collector as a diagnostic workaround. Review the recorded run
and preserve the last successful data; live recovery remains unverified until
an already-authorized run succeeds. Tunnel cleanup runs on failure as before.
