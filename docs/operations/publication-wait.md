# Daily publication review wait (#595)

The daily publication workflow stages a bounded data PR, never merges it.
While a same-repository publications/* PR is open, the workflow reports a green
waiting notice and skips checkout, VPN, collection, diff, publication and artifact
upload. No tunnel was opened, so cleanup is skipped too. API/JSON errors still
fail closed and are real failures, unlike ordinary review waiting.

This intentionally pauses publication detection until that PR is reviewed and
merged. Publications that appear during the wait are delayed; a row that appears
and disappears entirely during a long wait may never be observed. Keep review
waits short and escalate stalled review through the normal review process. Do
not infer that a green waiting run checked the municipality or found no notices.
It did neither. Continuing collection without mutating a reviewed PR needs a
separate reviewed design, not a hidden successor or retry.

The publisher also re-checks pending PRs immediately before its Git Data API
writes. It never changes an existing PR head or creates a competing PR while one
is pending. The workflow concurrency group serializes scheduled/manual runs;
external writers outside that group can still race, so this is not an atomic
repository-wide lock. A no-change render returns without commit/ref/PR writes.
