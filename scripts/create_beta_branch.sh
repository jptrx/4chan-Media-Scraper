#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/create_beta_branch.sh [branch-name] [remote-name]
# Defaults: branch-name="beta" remote-name="origin"

branch_name="${1:-beta}"
remote_name="${2:-origin}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: this script must be run inside a git repository." >&2
  exit 1
fi

# Create or update the local branch to point at the current HEAD.
if git show-ref --verify --quiet "refs/heads/${branch_name}"; then
  echo "Updating existing local branch '${branch_name}' to current HEAD..."
else
  echo "Creating local branch '${branch_name}' at current HEAD..."
fi
git branch -f "${branch_name}"

# Attempt to push if the remote exists; otherwise, provide next steps.
if git remote get-url "${remote_name}" >/dev/null 2>&1; then
  echo "Pushing '${branch_name}' to remote '${remote_name}'..."
  echo "(If authentication is required, the push may prompt or fail.)"
  git push -u "${remote_name}" "${branch_name}"
else
  echo "No remote named '${remote_name}' is configured."
  echo "The local branch '${branch_name}' has been created; add a remote and rerun to push."
fi
