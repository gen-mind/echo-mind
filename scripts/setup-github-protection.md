# GitHub Branch Protection Setup

✅ **develop branch created and pushed!**

Now configure branch protection rules on GitHub:

---

## 🔒 Step 1: Protect `main` Branch

**Open this URL:**
```
https://github.com/gen-mind/echo-mind/settings/branch_protection_rules/new
```

### Configuration:

**Branch name pattern:**
```
main
```

**Branch protection rules:**

1. ✅ **Require a pull request before merging**
   - **Require approvals:** 1
   - ✅ Dismiss stale pull request approvals when new commits are pushed
   - ✅ Require approval of the most recent reviewable push

2. ✅ **Require status checks to pass before merging**
   - ✅ Require branches to be up to date before merging
   - **Status checks required** (add after first CI run):
     - `test-python`
     - `test-web`
     - `lint-python`
     - `lint-web`
     - `build`
     - `proto-check`
     - `commitlint`

3. ✅ **Require conversation resolution before merging**

4. ✅ **Require signed commits** (recommended)

5. ✅ **Require linear history**

6. ✅ **Do not allow bypassing the above settings**
   - Applies to administrators

7. **Rules applied to everyone including administrators:**
   - ❌ **Allow force pushes:** Disabled
   - ❌ **Allow deletions:** Disabled

**Click "Create" button**

---

## 🔒 Step 2: Protect `develop` Branch

**Open this URL:**
```
https://github.com/gen-mind/echo-mind/settings/branch_protection_rules/new
```

### Configuration:

**Branch name pattern:**
```
develop
```

**Branch protection rules:**

1. ✅ **Require a pull request before merging**
   - **Require approvals:** 1
   - ✅ Dismiss stale pull request approvals when new commits are pushed
   - ✅ Require approval of the most recent reviewable push

2. ✅ **Require status checks to pass before merging**
   - ✅ Require branches to be up to date before merging
   - **Status checks required** (add after first CI run):
     - `test-python`
     - `test-web`
     - `lint-python`
     - `lint-web`

3. ✅ **Require conversation resolution before merging**

4. ✅ **Require linear history**

5. **Rules applied to everyone including administrators:**
   - ❌ **Allow force pushes:** Disabled
   - ❌ **Allow deletions:** Disabled

**Click "Create" button**

---

## ⚙️ Step 3: Enable GitHub Actions

**Open this URL:**
```
https://github.com/gen-mind/echo-mind/settings/actions
```

### Configuration:

**Actions permissions:**
- ✅ **Allow all actions and reusable workflows**

**Workflow permissions:**
- ✅ **Read and write permissions**
- ✅ **Allow GitHub Actions to create and approve pull requests**

**Fork pull request workflows:**
- ✅ **Require approval for first-time contributors**

**Click "Save" button**

---

## 🌐 Step 4: Set Default Branch to `develop` (Optional)

**Open this URL:**
```
https://github.com/gen-mind/echo-mind/settings/branches
```

**Default branch:**
- Click pencil icon next to current default (main)
- Select `develop`
- Click "Update"
- Confirm

**Why?** New contributors will create PRs to `develop` by default.

---

## ✅ Step 5: Verify Setup

### Test 1: Direct Push to Main (Should Fail)

```bash
git checkout main
echo "test" >> README.md
git commit -am "test: verify protection"
git push origin main
```

**Expected result:** ❌ Error: `protected branch hook declined`

### Test 2: Create Test PR

```bash
git checkout develop
git checkout -b test/verify-workflow
echo "# Test Workflow" >> README.md
git commit -m "docs: test PR workflow"
git push origin test/verify-workflow
```

Then:
1. Go to https://github.com/gen-mind/echo-mind/pulls
2. Click "New pull request"
3. Base: `develop`, Compare: `test/verify-workflow`
4. Create PR

**Expected results:**
- ✅ PR template auto-fills
- ✅ CI starts running automatically
- ✅ "1 approval required" message appears
- ✅ Cannot merge until CI passes + approval given

---

## 📊 Quick Reference URLs

| Action | URL |
|--------|-----|
| Branch protection rules | https://github.com/gen-mind/echo-mind/settings/branches |
| Actions settings | https://github.com/gen-mind/echo-mind/settings/actions |
| Create new PR | https://github.com/gen-mind/echo-mind/compare |
| View Actions runs | https://github.com/gen-mind/echo-mind/actions |
| Repository settings | https://github.com/gen-mind/echo-mind/settings |

---

## 🎯 Next Steps After Setup

1. **Create first real feature branch:**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-first-feature
   ```

2. **Make changes and open PR to test full workflow**

3. **Share CONTRIBUTING.md link with team:**
   ```
   https://github.com/gen-mind/echo-mind/blob/main/CONTRIBUTING.md
   ```

4. **Add more team members** as collaborators (Settings → Collaborators)

---

**Status:** ✅ Develop branch created and ready. Complete steps 1-4 above to finish setup!
