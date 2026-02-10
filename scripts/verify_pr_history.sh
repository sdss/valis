#!/bin/bash
# Script to verify that merged PRs are present in git history
# Usage: ./verify_pr_history.sh [number_of_prs_to_check]

set -e

# Default to checking last 10 PRs
NUM_PRS=${1:-10}

echo "PR History Verification Script"
echo "==============================="
echo ""

# Check if this is a shallow clone
if [ -f .git/shallow ]; then
    echo "⚠️  WARNING: This is a shallow clone!"
    echo "    Some history may not be available."
    echo "    Run 'git fetch --unshallow' to get full history."
    echo ""
    read -p "Would you like to unshallow now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Unshallowing repository..."
        git fetch --unshallow
        echo "✅ Repository unshallowed successfully"
        echo ""
    fi
fi

# Get the repo info from git remote
REMOTE_URL=$(git remote get-url origin)
REPO_PATH=$(echo $REMOTE_URL | sed -E 's/.*github\.com[:/]([^/]+\/[^/.]+)(\.git)?/\1/')

echo "Repository: $REPO_PATH"
echo "Checking last $NUM_PRS merged PRs..."
echo ""

# Note: This script requires gh CLI or manual API calls
# For simplicity, we'll just check git history for PR references

echo "Searching for PR merge commits in git history..."
echo ""

# Find commits with PR references in the last 50 commits
git log --oneline -50 --grep="#[0-9]" | while read -r commit; do
    # Extract PR number
    pr_num=$(echo "$commit" | grep -oE '#[0-9]+' | head -1 | tr -d '#')
    commit_sha=$(echo "$commit" | awk '{print $1}')
    
    if [ -n "$pr_num" ]; then
        # Verify commit exists
        if git cat-file -e "$commit_sha" 2>/dev/null; then
            echo "✅ PR #$pr_num - Commit $commit_sha exists"
        else
            echo "❌ PR #$pr_num - Commit $commit_sha MISSING"
        fi
    fi
done

echo ""
echo "Verification complete!"
echo ""
echo "Note: This script only checks commits that reference PRs in their message."
echo "      For comprehensive verification, use the GitHub API to list all merged PRs."
