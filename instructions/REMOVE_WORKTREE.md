# How to Remove Git Worktrees in Cursor

## Current Worktrees

Based on `git worktree list`, you have:
1. **Main repository**: `/Users/eboraks/Projects/icognition` (on branch `chat_SSE`)
2. **Worktree `ddp`**: `/Users/eboraks/.cursor/worktrees/icognition/ddp` (detached HEAD, has changes)
3. **Worktree `hmq`**: `/Users/eboraks/.cursor/worktrees/icognition/hmq` (detached HEAD, has SSE migration changes)

## Remove Worktree with Uncommitted Changes

### Option 1: Force Remove (Discards All Changes) ⚠️

**To remove `ddp` worktree:**
```bash
cd /Users/eboraks/Projects/icognition
git worktree remove --force /Users/eboraks/.cursor/worktrees/icognition/ddp
```

**To remove `hmq` worktree:**
```bash
cd /Users/eboraks/Projects/icognition
git worktree remove --force /Users/eboraks/.cursor/worktrees/icognition/hmq
```

**⚠️ Warning:** This will **permanently delete** all uncommitted changes in that worktree!

### Option 2: Manual Removal

If `git worktree remove` fails, you can manually delete:

```bash
# 1. Make sure you're NOT in the worktree directory
cd /Users/eboraks/Projects/icognition

# 2. Remove the worktree directory
rm -rf /Users/eboraks/.cursor/worktrees/icognition/ddp
# or
rm -rf /Users/eboraks/.cursor/worktrees/icognition/hmq

# 3. Clean up Git's worktree registry
git worktree prune
```

### Option 3: Save Changes First (If You Want to Keep Them)

If you want to save the changes before removing:

```bash
# 1. Go to the worktree
cd /Users/eboraks/.cursor/worktrees/icognition/ddp

# 2. Create a patch or stash
git diff > /tmp/worktree-changes.patch
# or
git stash

# 3. Go back to main repo and remove worktree
cd /Users/eboraks/Projects/icognition
git worktree remove /Users/eboraks/.cursor/worktrees/icognition/ddp
```

## Verify Removal

After removing, verify:
```bash
git worktree list
```

You should only see the main repository.

## Notes

- **Cursor worktrees**: Cursor creates worktrees in `~/.cursor/worktrees/` for its own use
- **Safe to remove**: If you're not actively using a worktree in Cursor, it's safe to remove
- **Auto-cleanup**: Cursor may recreate worktrees when needed, so don't worry about removing them

## Which Worktree to Remove?

- **`ddp`**: Has changes to `chat.py` and `chat_store.ts` - likely an old worktree
- **`hmq`**: Has all the SSE migration changes we just completed - **KEEP THIS ONE** if you want to keep the SSE work

If you want to keep the SSE migration work but remove the old `ddp` worktree:
```bash
cd /Users/eboraks/Projects/icognition
git worktree remove --force /Users/eboraks/.cursor/worktrees/icognition/ddp
```

