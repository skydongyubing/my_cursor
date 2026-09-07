---
name: "gitee-release"
description: "发布威宇佳烧录工具新版本到 Gitee（改版本号→打包→建 Release→传附件→更新 latest.json→全链路验证→提交推送）。当用户要求发布新版本、发版、推送升级、release 时调用。"
---

# Gitee 一键发版技能（威宇佳烧录 / WYJ PROGRAM）

本 workspace 的发版流程已固化在 `release.py`，通过 Gitee API 自动完成全部步骤，并在最后做真实链路验证。

## 触发场景

用户说「发布 1.x」「发版」「推送升级」「release」等。

## 标准流程

1. **确认版本号**：形如 `1.7`（x.y）。版本号只能升不能降；`APP_VERSION` 在 `src/updater.py`，由脚本自动修改。
2. **获取 Gitee 私人令牌**：令牌只能用户本人在网页生成（https://gitee.com/profile/personal_access_tokens ，只勾 `projects` 权限）。模型无法代办；用户提供后使用，用完**必须提醒用户作废**。
3. **执行发布**（工作目录 `d:\my_cursor`）：

   ```powershell
   .venv\Scripts\python.exe release.py <版本号> --notes "<更新说明>" --token <令牌>
   ```

   脚本六步：改 `APP_VERSION` → PyInstaller 打包 → 算 sha256 → 建/复用 Release `v<版本号>` 并上传固定名附件 `威宇佳烧录.exe`（同名旧附件自动删除）→ 更新仓库 `latest.json` → 拉线上 manifest + 完整下载附件比对 sha256。**必须看到 `[6/6] 验证通过` 才算成功**，否则按报错排查，不得宣告完成。
4. **提交推送代码**（release.py 会改 `src/updater.py`；main.spec 固定名不再改动）：

   - PowerShell **不支持 heredoc**，提交信息写入临时文件后 `git commit -F <文件>`
   - 提交信息文件若含中文，先确保 UTF-8 编码（本环境 Write 工具偶发写成 GBK，提交前用 python 检查/转回）
   - `git add` 需要提交的文件（release.py 改动、src/updater.py 等）→ commit → `git push`
   - push 到 GitHub 偶发 `Connection was reset`（网络波动），重试即可；用户开代理后通常即通。**禁止 force push**
5. **收尾提醒**：提醒用户到 Gitee 删除本次令牌。

## 关键约定（不要破坏）

- 产物/附件/下载 URL 一律使用**固定文件名** `威宇佳烧录.exe`（`src/main.spec` 的 `name="威宇佳烧录"`、`release.py` 的 `EXE_NAME`）。版本区分靠标题栏 `WYJ PROGRAM vX.Y`，不进文件名
- `latest.json` 字段：`version` / `url`（releases/download/vX.Y/威宇佳烧录.exe）/ `sha256`（小写）/ `notes`
- 升级覆盖机制：下载到临时目录 → 移为 exe 同目录 `.new` → updater.bat 等进程退出后 `move /y` 原地覆盖并重启
- 下载链路含中文文件名 + 302 重定向，必须走 `src/updater.py` 的 `_quoted_url` + `_QuotingRedirectHandler`，裸 urllib 会 `UnicodeEncodeError`
- 打包命令：`.venv\Scripts\pyinstaller --noconfirm --clean --workpath src\build --distpath src\dist src\main.spec`
- 仅演练不碰 Gitee：`release.py <版本号> --dry-run`；演练后用 `git checkout -- src/updater.py` 还原版本号（spec 不再被改）

## 常见问题

- **脚本/源文件/本 SKILL.md 被写成 GBK 编码**：本环境用 Write/Edit 创建或修改含中文文件后偶发（SKILL.md 自身也中过招），运行报 `SyntaxError: Non-UTF-8` 或读取报 `UnicodeDecodeError`。用 python 读 bytes 尝试 utf-8 解码、失败则按 gbk 解码后转回 utf-8
- **PowerShell 内联 python（`python -c "..."`）含正则/引号时易报错**：PowerShell 会把 `r'(.+?)'` 之类当作子表达式解析（`The term '.+?' is not recognized`）。复杂脚本一律写成临时 .py 文件再运行，不要塞进 `-c`
- **Gitee 仓库/Release 操作 404**：确认仓库已初始化（master 分支存在）、令牌有效且有 `projects` 权限
- **发布后旧版未提示升级**：检查 `latest.json` 的 version 是否严格大于旧版 APP_VERSION、raw 链接是否 200（Gitee raw 有短时缓存）

## 验证记录

- **2026-09-07 技能演练（dry-run，不碰 Gitee）**：
  - SKILL.md 结构校验通过（frontmatter/name 有效，description 100 字符 ≤200）
  - `release.py 1.7 --dry-run` 六步走完前三步：版本号修改、PyInstaller 打包、固定名产物 `src/dist/威宇佳烧录.exe` 产出正常
  - 演练后 `git checkout -- src/updater.py` 还原，APP_VERSION 回到线上版本
  - 演练中命中并验证了两处文档记载的坑：SKILL.md 被写成 GBK（按常见问题方法修复）、PowerShell 内联 python 正则引号报错（改用临时脚本）
- **真实发布历史**：v1.4（首版在线升级）、v1.5、v1.6（固定文件名方案）均经 `[6/6] 验证通过`——manifest 拉取 + 附件完整下载 + sha256 比对一致

