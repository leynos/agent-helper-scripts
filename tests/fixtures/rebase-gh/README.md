# Real GitHub CLI captures for rebase discovery

These stdout/stderr files came from **gh 2.100.0**, running the exact argv in
`manifest.json` on 10 September 2026. The manifest records the timestamp,
command exit codes and originating Actions run. The capture used read-only
repository and pull-request permissions. It contains no token, authorization
header, private user data or synthetic commit IDs.

`merged-parent` queries the merged PR `leynos/agent-helper-scripts#50` and projects
the fields used by the planner. `missing-parent` records the real HTTP 404 for
PR 2147483647, including the CLI's non-zero status and stderr. Keep the raw files
unchanged; whitespace and trailing newlines are part of each capture.

The behavioural tests deep-copy the parsed success fixture and substitute
`head_sha` and `landed` with object IDs from their isolated real Git histories.
Negative tests explicitly override additional fields. Those transformed responses
are synthetic scenarios based on this real schema, not additional live captures.
`cmd-mox` supplies them through an executable `gh` shim and verifies the exact
argument vector. Git itself remains real. A repository-local `url.*.insteadOf`
rule redirects the explicit GitHub fetch URL to a local bare remote, and
`GIT_ALLOW_PROTOCOL=file` prevents accidental live Git traffic.

To refresh, run the argv arrays in the manifest with a real, authenticated `gh`
and capture stdout, stderr and exit status separately. Record the new CLI version,
UTC timestamp and source PR. Do not put credentials in the fixture or log. Review
the real output before replacing any file. Tests are offline and never refresh
fixtures automatically. A one-off capture workflow produced these fixtures;
that temporary workflow is not part of the finished change.
