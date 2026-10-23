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
# invocation carries the same random `run_id` for correlation. A successful run
# prints the comment URL; it is not proof that a bot received, resolved, or
# approved anything.
#
# Structure: `main` owns argument validation, the diagnostic context, and the
# stage order. Each stage is a narrow unit with explicit inputs: `select_token`
# reads a given pool path, `query_login` is the only identity query,
# `resolve_lifecycle_login` and `verify_pool_identity` decide identities, and
# `publish_comment` is the only write. Units return a status, assign results
# to a named variable, and report failures through `FAILURE_CATEGORY` and
# `FAILURE_HTTP_STATUS`. The GitHub client is `gh` on `PATH`, the clock is
# `now_ms`, and the run-ID source is `new_run_id`. Sourcing this file defines
# the units without running `main`, so tests can replace any of them.

now_ms() {
  date +%s%3N
}

new_run_id() {
  od -An -N8 -tx1 /dev/urandom | tr -d ' \n'
}

valid_login() {
  [[ "$1" =~ ^[A-Za-z0-9-]+$ ]]
}

http_status_from() {
  if [[ "$1" =~ HTTP[[:space:]]+([0-9]{3}) ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  fi
}

# Classify a failed gh call from its private standard error and HTTP status.
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
    5[0-9][0-9]) printf '%s' 'server_error' ;;
    '')
      shopt -s nocasematch
      if [[ "$response" =~ (dial\ tcp|no\ such\ host|could\ not\ resolve|connection\ (refused|reset)|i/o\ timeout|timed\ out|tls\ handshake|network\ is\ unreachable|unexpected\ eof) ]]; then
        printf '%s' 'network_error'
      else
        printf '%s' 'github_api_failed'
      fi
      shopt -u nocasematch
      ;;
    *) printf '%s' 'github_api_failed' ;;
  esac
}

# Record a classified failure from a gh call's private standard-error file.
record_gh_failure() {
  local _rf_err=$1 _rf_text
  _rf_text=$(<"$_rf_err")
  FAILURE_HTTP_STATUS=$(http_status_from "$_rf_text")
  FAILURE_CATEGORY=$(failure_category_for "$_rf_text" "$FAILURE_HTTP_STATUS")
}

# Emit one bounded diagnostic using the context `main` established.
log_diagnostic() {
  local stage=$1 failure_category=$2 exit_status=$3 started_at_ms=$4
  local http_status=$5 elapsed_ms
  elapsed_ms=$(( $(now_ms) - started_at_ms ))
  jq -cn \
    --arg operation 'manual_pr_comment' \
    --arg run_id "$DIAG_RUN_ID" \
    --arg surface "$DIAG_SURFACE" \
    --arg repository "$DIAG_REPOSITORY" \
    --arg pr "$DIAG_PR" \
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

# select_token POOL_PATH OUT_VAR
# Choose one token record from POOL_PATH with `shuf`.
select_token() {
  local _st_pool=$1 _st_out=$2 _st_selected _st_status
  FAILURE_CATEGORY='' FAILURE_HTTP_STATUS=''
  if [[ ! -f "$_st_pool" || ! -r "$_st_pool" ]]; then
    FAILURE_CATEGORY=token_pool_unavailable
    return 2
  fi
  if _st_selected=$(
    awk '{ sub(/\r$/, "") }
         NF && $0 !~ /^[[:space:]]*#/ { print }' "$_st_pool" |
      shuf -n 1
  ); then
    :
  else
    _st_status=$?
    FAILURE_CATEGORY=token_selection_failed
    return "$_st_status"
  fi
  if [[ -z "$_st_selected" || "$_st_selected" == *[[:space:]]* ]]; then
    FAILURE_CATEGORY=token_not_selected
    return 2
  fi
  printf -v "$_st_out" '%s' "$_st_selected"
}

# query_login TOKEN ERROR_FILE OUT_VAR
# Read the login for TOKEN, or for stored authentication when TOKEN is empty.
# Standard error goes only to ERROR_FILE.
query_login() {
  local _ql_token=$1 _ql_err=$2 _ql_out=$3 _ql_login _ql_status=0
  if [[ -n "$_ql_token" ]]; then
    _ql_login=$(
      GH_TOKEN="$_ql_token" GITHUB_TOKEN="$_ql_token" \
        gh api --hostname github.com user --jq '.login' 2>"$_ql_err"
    ) || _ql_status=$?
  else
    _ql_login=$(
      unset GH_TOKEN GITHUB_TOKEN
      gh api --hostname github.com user --jq '.login' 2>"$_ql_err"
    ) || _ql_status=$?
  fi
  printf -v "$_ql_out" '%s' "$_ql_login"
  return "$_ql_status"
}

# resolve_lifecycle_login OVERRIDE ERROR_FILE OUT_VAR
# Prefer the stored login; use OVERRIDE only when the lookup is unavailable.
resolve_lifecycle_login() {
  local _rl_override=$1 _rl_err=$2 _rl_out=$3 _rl_stored='' _rl_response _rl_status=0
  FAILURE_CATEGORY='' FAILURE_HTTP_STATUS=''
  if [[ -n "$_rl_override" ]] && ! valid_login "$_rl_override"; then
    FAILURE_CATEGORY=invalid_lifecycle_override
    return 2
  fi
  query_login '' "$_rl_err" _rl_response || _rl_status=$?
  if (( _rl_status == 0 )) && valid_login "$_rl_response"; then
    _rl_stored=$_rl_response
  fi
  if [[ -n "$_rl_stored" && -n "$_rl_override" && "${_rl_stored,,}" != "${_rl_override,,}" ]]; then
    FAILURE_CATEGORY=lifecycle_identity_mismatch
    return 2
  fi
  if [[ -n "${_rl_stored:-$_rl_override}" ]]; then
    printf -v "$_rl_out" '%s' "${_rl_stored:-$_rl_override}"
    return 0
  fi
  if (( _rl_status != 0 )); then
    record_gh_failure "$_rl_err"
    return "$_rl_status"
  fi
  FAILURE_CATEGORY=invalid_identity_response
  return 2
}

# verify_pool_identity TOKEN LIFECYCLE_LOGIN ERROR_FILE
# Succeed only when TOKEN authenticates as a valid account other than
# LIFECYCLE_LOGIN.
verify_pool_identity() {
  local _vp_token=$1 _vp_lifecycle=$2 _vp_err=$3 _vp_login _vp_status=0
  FAILURE_CATEGORY='' FAILURE_HTTP_STATUS=''
  query_login "$_vp_token" "$_vp_err" _vp_login || _vp_status=$?
  if (( _vp_status != 0 )); then
    record_gh_failure "$_vp_err"
    return "$_vp_status"
  fi
  if ! valid_login "$_vp_login"; then
    FAILURE_CATEGORY=invalid_identity_response
    return 2
  fi
  if [[ "${_vp_login,,}" == "${_vp_lifecycle,,}" ]]; then
    FAILURE_CATEGORY=unexpected_owner_identity
    return 2
  fi
}

# publish_comment TOKEN ENDPOINT BODY_FILE ERROR_FILE OUT_VAR
# POST the body once with TOKEN and assign the new comment's URL.
publish_comment() {
  local _pc_token=$1 _pc_endpoint=$2 _pc_body=$3 _pc_err=$4 _pc_out=$5
  local _pc_payload _pc_url _pc_status=0
  FAILURE_CATEGORY='' FAILURE_HTTP_STATUS=''
  if ! _pc_payload=$(jq -n --rawfile body "$_pc_body" '{body: $body}'); then
    FAILURE_CATEGORY=payload_encoding_failed
    return 2
  fi
  _pc_url=$(
    printf '%s\n' "$_pc_payload" |
      GH_TOKEN="$_pc_token" GITHUB_TOKEN="$_pc_token" \
        gh api --hostname github.com --method POST "$_pc_endpoint" \
          --input - --jq '.html_url' 2>"$_pc_err"
  ) || _pc_status=$?
  if (( _pc_status != 0 )); then
    record_gh_failure "$_pc_err"
    return "$_pc_status"
  fi
  printf -v "$_pc_out" '%s' "$_pc_url"
}

main() {
  # Disable tracing before any credential is read or expanded.
  set +x
  set -euo pipefail
  unset GH_DEBUG

  local repo=${1:?Supply OWNER/REPO}
  local pr=${2:?Supply PR number}
  local body_file=${3:?Supply a prepared Markdown body file}
  local root_comment_id=${4:-}
  local pool="$HOME/.local/share/github-tokens"
  local endpoint surface token lifecycle_login url started status

  [[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
    printf '%s\n' 'Invalid repository.' >&2; return 2;
  }
  [[ "$pr" =~ ^[1-9][0-9]*$ ]] || {
    printf '%s\n' 'Invalid PR number.' >&2; return 2;
  }
  [[ -f "$body_file" && -r "$body_file" && -s "$body_file" ]] || {
    printf '%s\n' 'Comment body missing, empty, or unreadable.' >&2; return 2;
  }
  surface=issue_comment
  endpoint="repos/$repo/issues/$pr/comments"
  if [[ -n "$root_comment_id" ]]; then
    [[ "$root_comment_id" =~ ^[1-9][0-9]*$ ]] || {
      printf '%s\n' 'Invalid root review-comment ID.' >&2; return 2;
    }
    endpoint="repos/$repo/pulls/$pr/comments/$root_comment_id/replies"
    surface=inline_reply
  fi

  DIAG_RUN_ID=$(new_run_id)
  DIAG_SURFACE=$surface DIAG_REPOSITORY=$repo DIAG_PR=$pr
  # Keep each gh call's standard error apart from its output: wrappers on PATH
  # may write diagnostics there, which must not corrupt a login or URL. The
  # private files are read only to classify failures and are never echoed.
  ERR_DIR=$(mktemp -d)
  trap 'rm -rf -- "$ERR_DIR"' EXIT

  started=$(now_ms) status=0
  select_token "$pool" token || status=$?
  log_diagnostic token_selection "${FAILURE_CATEGORY:-}" "$status" "$started" '' || true
  if (( status != 0 )); then
    printf 'Authorized token selection failed: category=%s.\n' "$FAILURE_CATEGORY" >&2
    return "$status"
  fi

  started=$(now_ms) status=0
  resolve_lifecycle_login "${PR_BABYSITTING_LIFECYCLE_LOGIN:-}" \
    "$ERR_DIR/lifecycle" lifecycle_login || status=$?
  log_diagnostic lifecycle_identity "${FAILURE_CATEGORY:-}" "$status" "$started" \
    "${FAILURE_HTTP_STATUS:-}" || true
  if (( status != 0 )); then
    printf 'Lifecycle account unavailable: category=%s http_status=%s exit_status=%s.\n' \
      "$FAILURE_CATEGORY" "${FAILURE_HTTP_STATUS:-unknown}" "$status" >&2
    return "$status"
  fi

  started=$(now_ms) status=0
  verify_pool_identity "$token" "$lifecycle_login" "$ERR_DIR/identity" || status=$?
  log_diagnostic identity_preflight "${FAILURE_CATEGORY:-}" "$status" "$started" \
    "${FAILURE_HTTP_STATUS:-}" || true
  if (( status != 0 )); then
    printf 'Pool token identity check failed: category=%s http_status=%s exit_status=%s.\n' \
      "$FAILURE_CATEGORY" "${FAILURE_HTTP_STATUS:-unknown}" "$status" >&2
    return "$status"
  fi

  started=$(now_ms) status=0
  publish_comment "$token" "$endpoint" "$body_file" "$ERR_DIR/post" url || status=$?
  log_diagnostic post "${FAILURE_CATEGORY:-}" "$status" "$started" \
    "${FAILURE_HTTP_STATUS:-}" || true
  if (( status != 0 )); then
    printf 'Manual comment POST failed: category=%s http_status=%s exit_status=%s.\n' \
      "$FAILURE_CATEGORY" "${FAILURE_HTTP_STATUS:-unknown}" "$status" >&2
    return "$status"
  fi
  printf '%s\n' "$url"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
