# Commit Skill

Create a git commit for the current staged and unstaged changes.

## Steps

1. Run `git status` to see all changed and untracked files.
2. Run `git diff` and `git diff --staged` to review changes.
3. Run `git log --oneline -5` to see recent commit style.
4. Stage the relevant files (prefer specific filenames over `git add -A`). Never stage `.env`, `credentials.json`, or other secrets.
5. Write a conventional commit message:
   - Start with a verb: Add, Fix, Update, Remove, Refactor
   - Keep first line under 72 characters
   - Add body details if the change is non-trivial
6. Commit with the Co-Authored-By trailer:

```
git commit -m "$(cat <<'EOF'
<subject line>

<optional body>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

7. Run `git status` to confirm the commit succeeded.
