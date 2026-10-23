#!/usr/bin/env bash
# Post one manual PR comment or inline reply through the comment-token pool.
#
# Usage:
#   post-manual-comment.sh OWNER/REPO PR_NUMBER BODY_FILE [ROOT_COMMENT_ID]
#
# Supply ROOT_COMMENT_ID to reply in an inline review thread; omit it for a
# new top-level issue comment. The helper selects one token with GNU `shuf`
# from the regular file `~/.local/share/github-tokens` (one raw token per
# nonblank line; full-line `#` comments are ignored). It never sources the
# pool.
#
# The selected token must authenticate as an account other than the normal
# lifecycle account. The helper reads the lifecycle login from the stored `gh`
# authentication with `GH_TOKEN` and `GITHUB_TOKEN` removed. It uses
# `PR_BABYSITTING_LIFECYCLE_LOGIN` only when that lookup is unavailable, for
# example when the lifecycle account authenticates only through an environment
# token. When both logins exist and differ, or neither is available, it fails
# closed.
#
# Bounded JSON diagnostics go to standard error, without credentials, comment
# bodies, account names, or raw GitHub error text. Every diagnostic from one
# invocation carries the same random `run_id` for correlation. A successful run prints the
# comment URL; it is not proof that a bot received, resolved, or approved
# anything.

# Disable tracing before any credential is read or expanded.
set +x
set -euo pipefail
unset GH_DEBUG

repo=${1:?Supply OWNER/REPO}
pr=${2:?Supply PR number}
body_file=${3:?Supply a prepared Markdown body file}
root_comment_id=${4:-}
pool="$HOME/.local/share/github-tokens"

[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
  printf '%s\n' 'Invalid repository.' >&2; exit 2;
}
[[ "$pr" =~ ^[1-9][0-9]*$ ]] || {
  printf '%s\n' 'Invalid PR number.' >&2; exit 2;
}
[[ -f "$body_file" && -r "$body_file" && -s "$body_file" ]] || {
  printf '%s\n' 'Comment body missing, empty, or unreadable.' >&2; exit 2;
}
run_id=$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')
surface=issue_comment
endpoint="repos/$repo/issues/$pr/comments"
if [[ -n "$root_comment_id" ]]; then
  [[ "$root_comment_id" =~ ^[1-9][0-9]*$ ]] || {
    printf '%s\n' 'Invalid root review-comment ID.' >&2; exit 2;
  }
  endpoint="repos/$repo/pulls/$pr/comments/$root_comment_id/replies"
  surface=inline_reply
fi

log_diagnostic() {
  local stage=$1 failure_category=$2 exit_status=$3 started_at_ms=$4
  local http_status=$5 elapsed_ms
  elapsed_ms=$(( $(date +%s%3N) - started_at_ms ))
  jq -cn \
    --arg operation 'manual_pr_comment' \
    --arg run_id "$run_id" \
    --arg surface "$surface" \
    --arg repository "$repo" \
    --arg pr "$pr" \
    --arg stage "$stage" \
    --arg failure_category "$failure_category" \
    --arg http_status "$http_status" \
    --argjson exit_status "$exit_status" \
    --argjson elapsed_ms "$elapsed_ms" \
    '{operation: $operation, run_id: $run_id, surface: $surface, repository: $repository,
      pr: $pr, stage: $stage,
      failure_category: (if $failure_category == "" then null else $failure_category end),
      exit_status: $exit_status, elapsed_ms: $elapsed_ms,
      http_status: (if $http_status == "" then null else ($http_status | tonumber) end)}' \
    >&2 || {
      printf '%s\n' 'Unable to emit structured manual-comment diagnostics.' >&2
      return 1
    }
}

http_status_from() {
  if [[ "$1" =~ HTTP[[:space:]]+([0-9]{3}) ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  fi
}

failure_category_for() {
  local response=$1 http_status=$2
  case "$http_status" in
    401) printf '%s' 'authentication_failed' ;;
    429) printf '%s' 'rate_limited' ;;
    403)
      case "$response" in
        *'rate limit'*|*'Rate limit'*) printf '%s' 'rate_limited' ;;
        *) printf '%s' 'permission_denied' ;;
      esac
      ;;
    *) printf '%s' 'github_api_failed' ;;
  esac
}

valid_login() {
  [[ "$1" =~ ^[A-Za-z0-9-]+$ ]]
}

# Keep each gh call's standard error apart from its output: wrappers on PATH
# may write diagnostics there, which must not corrupt a login or URL. The
# private files are read only to classify failures and are never echoed.
err_dir=$(mktemp -d)
trap 'rm -rf -- "$err_dir"' EXIT

selection_started_ms=$(date +%s%3N)
if [[ ! -f "$pool" || ! -r "$pool" ]]; then
  log_diagnostic token_selection token_pool_unavailable 2 "$selection_started_ms" '' || true
  printf '%s\n' 'Authorized token pool unavailable.' >&2
  exit 2
fi
if token=$(
  awk '{ sub(/\r$/, "") }
       NF && $0 !~ /^[[:space:]]*#/ { print }' "$pool" |
    shuf -n 1
); then
  :
else
  status=$?
  log_diagnostic token_selection token_selection_failed "$status" "$selection_started_ms" '' || true
  printf '%s\n' 'Authorized token selection failed.' >&2
  exit "$status"
fi
if [[ -z "$token" || "$token" == *[[:space:]]* ]]; then
  log_diagnostic token_selection token_not_selected 2 "$selection_started_ms" '' || true
  printf '%s\n' 'No valid token record selected.' >&2
  exit 2
fi
log_diagnostic token_selection '' 0 "$selection_started_ms" '' || true

# Establish the lifecycle account from stored authentication, never from an
# ambient token or the selected pool credential. The override is only a
# fallback for an unavailable lookup and must agree with it when both exist.
lifecycle_started_ms=$(date +%s%3N)
override_login=${PR_BABYSITTING_LIFECYCLE_LOGIN:-}
if [[ -n "$override_login" ]] && ! valid_login "$override_login"; then
  log_diagnostic lifecycle_identity invalid_lifecycle_override 2 \
    "$lifecycle_started_ms" '' || true
  printf '%s\n' 'PR_BABYSITTING_LIFECYCLE_LOGIN is not a valid login.' >&2
  exit 2
fi
stored_status=0
stored_response=$(
  env -u GH_TOKEN -u GITHUB_TOKEN \
    gh api --hostname github.com user --jq '.login' 2>"$err_dir/lifecycle"
) || stored_status=$?
stored_login=
if (( stored_status == 0 )) && valid_login "$stored_response"; then
  stored_login=$stored_response
fi
if [[ -n "$stored_login" && -n "$override_login" \
      && "${stored_login,,}" != "${override_login,,}" ]]; then
  log_diagnostic lifecycle_identity lifecycle_identity_mismatch 2 \
    "$lifecycle_started_ms" '' || true
  printf '%s\n' 'Stored login and PR_BABYSITTING_LIFECYCLE_LOGIN disagree.' >&2
  exit 2
fi
lifecycle_login=${stored_login:-$override_login}
if [[ -z "$lifecycle_login" ]]; then
  http_status=
  if (( stored_status != 0 )); then
    stored_error=$(<"$err_dir/lifecycle")
    http_status=$(http_status_from "$stored_error")
    failure_category=$(failure_category_for "$stored_error" "$http_status")
    exit_code=$stored_status
  else
    failure_category=invalid_identity_response
    exit_code=2
  fi
  log_diagnostic lifecycle_identity "$failure_category" "$exit_code" \
    "$lifecycle_started_ms" "$http_status" || true
  printf 'Lifecycle account unavailable: category=%s http_status=%s exit_status=%s.\n' \
    "$failure_category" "${http_status:-unknown}" "$exit_code" >&2
  exit "$exit_code"
fi
log_diagnostic lifecycle_identity '' 0 "$lifecycle_started_ms" '' || true

# Check the selected credential, not the normal lifecycle account.
identity_started_ms=$(date +%s%3N)
if login=$(
  GH_TOKEN="$token" GITHUB_TOKEN="$token" \
    gh api --hostname github.com user --jq '.login' 2>"$err_dir/identity"
); then
  if valid_login "$login" && [[ "${login,,}" != "${lifecycle_login,,}" ]]; then
    log_diagnostic identity_preflight '' 0 "$identity_started_ms" '' || true
  else
    if valid_login "$login"; then
      failure_category=unexpected_owner_identity
    else
      failure_category=invalid_identity_response
    fi
    log_diagnostic identity_preflight "$failure_category" 2 "$identity_started_ms" '' || true
    printf '%s\n' 'Expected a pool account other than the lifecycle account; check configuration.' >&2
    exit 2
  fi
else
  status=$?
  identity_error=$(<"$err_dir/identity")
  http_status=$(http_status_from "$identity_error")
  failure_category=$(failure_category_for "$identity_error" "$http_status")
  log_diagnostic identity_preflight "$failure_category" "$status" \
    "$identity_started_ms" "$http_status" || true
  if [[ -z "$http_status" ]]; then http_status=unknown; fi
  printf 'GitHub identity verification failed: category=%s http_status=%s exit_status=%s.\n' \
    "$failure_category" "$http_status" "$status" >&2
  exit "$status"
fi

post_started_ms=$(date +%s%3N)
if payload=$(jq -n --rawfile body "$body_file" '{body: $body}'); then
  :
else
  status=$?
  log_diagnostic post payload_encoding_failed "$status" "$post_started_ms" '' || true
  printf 'Manual comment payload encoding failed: exit_status=%s.\n' "$status" >&2
  exit "$status"
fi
if post_result=$(
  printf '%s\n' "$payload" |
    GH_TOKEN="$token" GITHUB_TOKEN="$token" \
      gh api --hostname github.com --method POST "$endpoint" \
        --input - --jq '.html_url' 2>"$err_dir/post"
); then
  log_diagnostic post '' 0 "$post_started_ms" '' || true
  printf '%s\n' "$post_result"
else
  status=$?
  post_error=$(<"$err_dir/post")
  http_status=$(http_status_from "$post_error")
  failure_category=$(failure_category_for "$post_error" "$http_status")
  log_diagnostic post "$failure_category" "$status" \
    "$post_started_ms" "$http_status" || true
  if [[ -z "$http_status" ]]; then http_status=unknown; fi
  printf 'Manual comment POST failed: category=%s http_status=%s exit_status=%s.\n' \
    "$failure_category" "$http_status" "$status" >&2
  exit "$status"
fi
