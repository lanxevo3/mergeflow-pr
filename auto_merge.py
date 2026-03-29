#!/usr/bin/env python3
"""
MergeFlow — GitHub PR Auto-Merge Engine
Pure Python stdlib + gh CLI. No external API calls except GitHub and Stripe.
"""
import json
import subprocess
import sys
import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

GH_CLI = "gh"

@dataclass
class PullRequest:
    number: int
    title: str
    url: str
    author: str
    draft: bool
    mergeable: bool
    review_decision: str  # APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED | None
    ci_status: str  # SUCCESS | FAILURE | PENDING | None
    approvals: int
    base_branch: str

def gh(args: list[str], repo: Optional[str] = None) -> subprocess.CompletedProcess:
    cmd = [GH_CLI] + args
    if repo:
        cmd[2:2] = ["--repo", repo]
    return subprocess.run(cmd, capture_output=True, text=True)

def get_open_prs(repo: str, min_approvals: int = 1) -> list[PullRequest]:
    result = gh([
        "pr", "list",
        "--state", "open",
        "--json", "number,title,url,author,isDraft,mergeable,reviewDecision,baseRefName",
        "--limit", "50"
    ], repo)

    if result.returncode != 0:
        raise RuntimeError(f"gh pr list failed: {result.stderr}")

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON from gh: {result.stdout[:200]}")

    mergeable_prs = []
    for raw in prs:
        if raw.get("isDraft") or not raw.get("mergeable"):
            continue

        pr = PullRequest(
            number=raw["number"],
            title=raw["title"],
            url=raw["url"],
            author=raw["author"].get("login", "unknown") if raw.get("author") else "unknown",
            draft=raw.get("isDraft", False),
            mergeable=raw.get("mergeable", False),
            review_decision=raw.get("reviewDecision") or "",
            ci_status="UNKNOWN",
            approvals=0,
            base_branch=raw.get("baseRefName", "main"),
        )
        mergeable_prs.append(pr)

    return mergeable_prs

def get_ci_status(repo: str, pr_number: int) -> tuple[str, int]:
    """Returns (ci_status, approval_count)."""
    result = gh([
        "pr", "view", str(pr_number),
        "--json", "statusCheckRollup,reviews",
        "--jq", "{ci: .statusCheckRollup, reviews: .reviews}"
    ], repo)

    if result.returncode != 0:
        return "UNKNOWN", 0

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "UNKNOWN", 0

    rollup = data.get("ci") or {}
    ci_conclusion = rollup.get("conclusion") or rollup.get("status", "UNKNOWN")

    # Count approvals (not author_association)
    approvals = sum(
        1 for r in data.get("reviews", [])
        if r.get("state") == "APPROVED"
    )

    return ci_conclusion, approvals

def should_merge(pr: PullRequest, min_approvals: int) -> tuple[bool, str]:
    """Returns (should_merge, reason)."""
    if pr.draft:
        return False, "draft PR"

    if not pr.mergeable:
        return False, "not mergeable"

    ci = pr.ci_status.upper()
    if ci not in ("SUCCESS", "COMPLETED", "PASSED"):
        return False, f"CI {ci} not passing"

    if pr.review_decision == "CHANGES_REQUESTED":
        return False, "changes requested"

    if pr.review_decision == "REVIEW_REQUIRED":
        return False, "review required"

    if pr.approvals < min_approvals:
        return False, f"only {pr.approvals}/{min_approvals} approvals"

    if pr.review_decision == "APPROVED":
        return True, "approved and CI passing"

    return False, f"review_decision={pr.review_decision}"

def merge_pr(repo: str, pr_number: int, author: str, squash: bool = True) -> tuple[bool, str]:
    method_flag = "--squash" if squash else "--admin --merge"
    result = gh(
        ["pr", "merge", str(pr_number), method_flag, "--auto", "--delete-branch"],
        repo
    )
    if result.returncode == 0:
        return True, f"Merged PR #{pr_number} (by @{author})"
    return False, f"Merge failed: {result.stderr.strip()}"

def run_scan(repo: str, min_approvals: int = 1, dry_run: bool = True,
             squash: bool = True) -> list[tuple[PullRequest, bool, str]]:
    """
    Returns list of (pr, merged, reason).
    """
    prs = get_open_prs(repo,