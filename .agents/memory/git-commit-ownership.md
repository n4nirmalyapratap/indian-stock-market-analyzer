---
name: Git commit ownership
description: User manages all git commits themselves — agent must never make explicit git commits.
---

The user owns the git history and commits all changes themselves.

**Why:** User explicitly requested this — they want full control over what goes into git history, including commit messages and grouping of changes.

**How to apply:** Only make file edits. Never run `git commit`, `git add && git commit`, or any command that creates a commit. Note that Replit auto-creates checkpoint commits after each agent loop ends — this is platform behaviour outside the agent's control, but the agent must not add any *additional* explicit commits on top of that.
