#!/usr/bin/env bash

# Post a pull request comment, an issue comment, or a reply in an inline review
# thread through the pr-babysitting manual-comment route. Run it on the host
# that holds the comment-token pool.
#
# The posting itself belongs to the pr-babysitting skill's helper,
# `skills/pr-babysitting/scripts/post-manual-comment.sh`, so this script
# follows the skill's manual-comment identity contract exactly: the helper
# selects one token with `shuf` from `~/.local/share/github-tokens`, scopes it
# to the one operation, refuses a token that authenticates as the lifecycle
# account, never prints credentials, and prints the new comment's URL.
#
# This wrapper adds a mode-based command line and the skill's CodeRabbit
# routing rules, checked before anything is posted:
#   - review requests (`@coderabbitai review`, `@coderabbitai full review`)
#     belong to comenq-coderabbit and are refused;
#   - a top-level PR comment must open with `@coderabbitai `, because
#     CodeRabbit ignores a question that does not mention it. Set
#     BOT_COMMENT_NO_MENTION=1 for a PR comment not addressed to CodeRabbit.
#     Issue comments and thread replies are not checked.
#
# Environment:
#   BOT_COMMENT_HELPER              path to post-manual-comment.sh; by default
#                                   the copy beside this script in a checkout,
#                                   then the installed skill under
#                                   ~/.claude/skills or ~/.codex/skills
#   BOT_COMMENT_NO_MENTION          see above
#   PR_BABYSITTING_LIFECYCLE_LOGIN  read by the helper when the stored `gh`
#                                   login cannot be looked up

set -euo pipefail

# Purpose:
#   Print command usage and terminate with an argument error.
# Parameters:
#   None.
# Returns:
#   Does not return; exits with status 2.
# Side effects:
#   Writes usage text to stderr.
usage() {
  cat >&2 <<'EOF'
Usage (the body is read from a file, so no shell quoting is involved):
  bot-comment.sh pr    <owner/repo> <pr-number> <body-file>
  bot-comment.sh reply <owner/repo> <pr-number> <review-comment-id> <body-file>
  bot-comment.sh issue <owner/repo> <issue-number> <body-file>

Prints the URL of the new comment.
EOF
  exit 2
}

# Purpose:
#   Report an error and terminate.
# Parameters:
#   $1 - exit status; $2 - message.
# Returns:
#   Does not return.
# Side effects:
#   Writes the message to stderr.
die() {
  printf '%s\n' "$2" >&2
  exit "$1"
}

# Purpose:
#   Locate the pr-babysitting posting helper.
# Parameters:
#   None.
# Returns:
#   Prints the helper's path; status 1 when no readable copy exists.
# Side effects:
#   None.
find_helper() {
  local script_dir candidate
  if [[ -n ${BOT_COMMENT_HELPER:-} ]]; then
    printf '%s\n' "$BOT_COMMENT_HELPER"
    return 0
  fi
  script_dir=$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)
  for candidate in \
    "$script_dir/../skills/pr-babysitting/scripts/post-manual-comment.sh" \
    "$HOME/.claude/skills/pr-babysitting/scripts/post-manual-comment.sh" \
    "$HOME/.codex/skills/pr-babysitting/scripts/post-manual-comment.sh"; do
    if [[ -f $candidate && -r $candidate ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

[[ $# -ge 1 ]] || usage
mode=$1
shift
case "$mode" in
  pr | issue)
    [[ $# -eq 3 ]] || usage
    repo=$1 number=$2 comment_id="" body_file=$3
    ;;
  reply)
    [[ $# -eq 4 ]] || usage
    repo=$1 number=$2 comment_id=$3 body_file=$4
    ;;
  *) usage ;;
esac

[[ $repo =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die 2 "bad repository: $repo"
[[ $number =~ ^[1-9][0-9]*$ ]] || die 2 "bad number: $number"
[[ -z $comment_id || $comment_id =~ ^[1-9][0-9]*$ ]] || die 2 "bad comment id: $comment_id"
[[ -f $body_file && -r $body_file && -s $body_file ]] ||
  die 2 "empty, missing or unreadable body file: $body_file"

if grep -Eiq '@coderabbitai[[:space:]]+(full[[:space:]]+)?review' "$body_file"; then
  die 3 "refused: review requests go through comenq-coderabbit, not a comment"
fi

if [[ $mode == pr && ${BOT_COMMENT_NO_MENTION:-} != 1 ]] &&
  ! head -c 64 "$body_file" | grep -Eq '^[[:space:]]*@coderabbitai[[:space:]]'; then
  die 4 "refused: a PR-level comment must start with '@coderabbitai ' (set BOT_COMMENT_NO_MENTION=1 if it is not for CodeRabbit)"
fi

helper=$(find_helper) || die 5 "pr-babysitting posting helper not found; set BOT_COMMENT_HELPER"

# PR conversation comments and issue comments share the issues endpoint, so
# both map to the helper's top-level form; a reply adds the thread's root ID.
if [[ -n $comment_id ]]; then
  exec bash "$helper" "$repo" "$number" "$body_file" "$comment_id"
fi
exec bash "$helper" "$repo" "$number" "$body_file"
