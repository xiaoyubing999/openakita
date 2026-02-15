# OpenAkita 发版流程

本文档记录 OpenAkita 的标准发版操作流程。**所有贡献者（包括 AI 辅助工具）发版时必须遵循此流程。**

---

## 前置准备

1. 确保所有代码已合并到 `main` 分支
2. 确认 CI 绿灯（包括完整 Tauri 构建检查 — `tauri_full_build_check` job）
3. 运行版本号同步：
   ```bash
   python scripts/version.py set <new_version>
   ```
   此命令会自动同步以下文件中的版本号：
   - `VERSION`
   - `pyproject.toml`
   - `apps/setup-center/package.json`
   - `apps/setup-center/src-tauri/tauri.conf.json`
   - `apps/setup-center/src-tauri/Cargo.toml` + `Cargo.lock`
4. 提交版本号变更并推送到 `main`

---

## 发版步骤

### Step 1: 预验证（可选但推荐）

- 在 GitHub Actions 页面手动触发 **"Release Dry Run"** workflow
- 等待三个平台（Windows / Linux / macOS）全部构建成功
- 如有失败，修复后重新触发
- Dry Run 产物会上传为 GitHub Artifacts（3 天后自动清理），不会发布到 Release

### Step 2: 打 tag 触发正式发布

```bash
git tag v<version>
git push origin v<version>
```

### Step 3: 等待 CI 完成

- Release 会先以 **Draft** 状态创建（用户不可见）
- Python 包构建 + PyPI 发布与 Desktop 构建并行执行
- 全平台 Desktop 构建成功后，Release 自动从 Draft 发布为正式版

---

## 如果 CI 构建失败

**绝不要为了修 CI 而递增版本号**（如 v1.21.9 → v1.21.10）。

### 方法 1: 强制更新 tag（推荐）

```bash
# 1. 本地修复代码
git add . && git commit -m "fix: 修复构建问题"
git push origin main

# 2. 强制更新 tag 指向新 commit
git tag -f v<version>
git push origin v<version> --force
```

tag push 会重新触发 Release workflow。因为 Release 仍是 Draft 状态，产物会被 `--clobber` 覆盖。

### 方法 2: 手动重跑 workflow

在 GitHub Actions 页面找到失败的 Release workflow → **"Re-run all jobs"**

适用于：构建失败是环境问题（如 runner 临时不可用），代码本身无需修改。

### 方法 3: workflow_dispatch 手动触发

在 GitHub Actions 页面手动触发 Release workflow，输入：
- `tag`: 要发布的 tag（如 `v1.22.0`）
- `ref`: 要构建的 commit SHA 或分支名（可选）

---

## 注意事项

- **Draft Release 对用户不可见**，放心重跑，不会造成用户看到残缺的版本
- **PyPI 发布是幂等的**（`twine upload --skip-existing`），重跑不会冲突
- `--clobber` 标志确保重跑时 GitHub Release 资产会被覆盖
- 发布成功后，CI 会自动更新 `latest.json` 用于应用内自动更新
- 如需清理历史废弃 Release，在 GitHub Releases 页面手动删除 Draft 状态的条目

---

## Workflow 文件说明

| Workflow | 文件 | 用途 |
|---|---|---|
| CI | `.github/workflows/ci.yml` | push/PR 触发，lint + test + 完整 Tauri 构建检查 |
| Release Dry Run | `.github/workflows/release-dryrun.yml` | 手动触发，全平台构建预验证，不发布 |
| Release | `.github/workflows/release.yml` | tag push 触发，Draft → Build → Publish |
