# 个人 Provider 协作规则

- 永远用中文答复；项目AGENTS.md、CLAUDE.md使用中文。运行命令和修改前说明意图，每个新会话先读本文件和CLAUDE.md。
- README只记稳定事实与入口，AGENTS只记规则，CLAUDE维护动态任务；专项规格使用现有docs。用户确认的口径立即同步，非必要不创建文档，不查看归档原文。
- 个人工作仅修改nowledge-mem-hermes及必要根文档；不改其他集成、发布注册或用户运行配置。不将个人NM依赖加入公开Secretary核心。
- 目标设计查nowledge-mem-hermes/docs/PHASE3.md现行§1–8；其历史附录与上游指南仅作参考，不能新增、覆盖已冻结要求或门禁。History由独立Secretary核心实现，本插件不monkey-patch。
- 保留单一Provider和已有helper边界。凭据不进入Git、日志或文档；复用运行主机NM配置，不复制开发机配置。未获明确授权不写真实NM数据、不改治理政策。
- 用户明确：NM创建等独立小工具放运行主机 `~/scripts/`，本机／云端一致；不依赖Hermes、插件目录、`HERMES_HOME`、仓库cwd或Hermes模块。工具只接收普通内容与通用Metadata JSON，由调用方提供来源，不自行读取Hermes状态。仅创建走窄工具，其余操作官方CLI；不借此搬迁无关脚本／修改全局配置。
- Memory独立创建入口的preview与apply均要求显式非空`--space`，Default明确写`--space default`；缺失、空串、纯空白直接拒绝，不从环境或Profile推断。
- 已准备并测试的工具原件只读／可执行；未经用户明确授权，不修改、删除、替换、解锁或提权绕过。扩展先读源码，在`~/scripts/custom/`另建副本并标明未验收；获授权维护原件时验证后重新保护。
- 开发闭环：读现行依据→检查工作区并保护已有修改→更新CLAUDE并说明意图→最小修改→按影响做必要检查→亲自review→同步文档和阶段提交。纯文档只检查差异、引用及一致性，不启动产品测试。具体轮次的用户验收例外以轮次索引为准。
- 提交仅包含任务授权内容。沿用户提交后自动同步规则，保留已有hook，安装主仓库.githooks/post-commit到本仓库实际hooks路径；不强推、不自动合并。代码同步不代表部署或验收通过。
- 自主轮次按autonomous-run套件；当前轮次索引与冻结版本位于并列hermes-secretary仓库.autonomous目录，入口由CLAUDE记录。不得借上游发布约定扩张任务。

## 上游规则历史参考

以下内容保留供理解原仓库，不是本个人fork的新增发布、验收或行为要求；冲突时以上规则和用户冻结规格优先。

<details>
<summary>上游Community参考</summary>

# Nowledge Community — Agent Guidelines

## Registry

[`integrations.json`](integrations.json) is the **single source of truth** for all Nowledge Mem integrations. It tracks capabilities, versions, install commands, transport, tool naming, and thread save methods.

**When adding or modifying any integration, update `integrations.json` first.** Other surfaces (website `integrations.ts`, desktop app integrations view, README tables, marketplace JSONs) derive from or validate against this file.

## Integration Release Contract

For npm, PyPI, or ClawHub release preparation, publication, failed-run recovery,
and acceptance, read [plugin-release](.agents/skills/plugin-release/SKILL.md)
before changing versions or dispatching a publisher. It is a maintainer skill,
not an end-user install skill, and does not grant release authority.

`integrations.json` is the canonical registry for every Nowledge Mem
integration. A plugin version bump is incomplete until all version-bearing
surfaces agree.

Changes to shipped runtime, skills, commands, rules, or hook guidance require a
plugin version bump before delivery, even when the change is Markdown-only.
An implementation PR without a bump is not a completed plugin release: land
the reviewed version update and finish each actual distribution channel.
Alma changes also require a matching PR to `yetone/alma-plugins`; see the
external marketplace section of `docs/PLUGIN_PUBLISHING.md`.

When changing an integration's version:

1. Update the package manifest, such as `plugin.yaml`, `plugin.json`,
   `package.json`, or the host-specific equivalent.
2. Update the matching integration's `version` in `integrations.json` in the
   same pull request.
3. Update changelogs, documentation, lockfiles, and tests that intentionally
   pin the released version.
4. Run the integration's focused test suite and the relevant registry or
   plugin contract tests.

Before approving or merging an integration release, search the repository for
the previous version and account for every remaining occurrence. Historical
changelog entries may remain unchanged; active manifests, registry entries,
install metadata, and release assertions must not disagree.

## Universal Install Contract — SKILL.md

`https://mem.nowledge.co/SKILL.md` is the **one URL** an AI agent can fetch before installing Nowledge Mem for a supported host. Source lives at <https://github.com/nowledge-co/nowledge-labs-website/blob/main/nowledge-mem/public/SKILL.md>. The design doc is <https://github.com/nowledge-co/mem/blob/main/docs/design/ONBOARDING_REVISIT_0_9_0.md>.

When adding or changing an integration's install command, update both:
1. The integration's row in [`integrations.json`](integrations.json) (`install.command`, `install.detectionHint`, `install.agentGuide`).
2. The matching row in the SKILL.md's "Step 2 — Install for that host" table, if the install command changes.

Per-tool `install.agentGuide` prompts in `integrations.json` should still point to `https://mem.nowledge.co/SKILL.md` first. Per-tool website pages are behavior and troubleshooting references after the connect loop starts, not the primary install contract.

The desktop app fetches this file at runtime from `https://raw.githubusercontent.com/nowledge-co/community/main/integrations.json` for plugin update awareness. Changes to the schema (adding/removing/renaming fields) affect:
- **Rust** (`lib.rs`): `fetch_plugin_registry`, `detect_installed_plugins`, `write_plugin_update_state`
- **TypeScript** (`plugin-update-manager.ts`): `RegistryIntegration` interface
- **Python** (`health.py`): `_read_plugin_update_state` reader

## Behavioral Guidance

[`shared/behavioral-guidance.md`](shared/behavioral-guidance.md) defines when plugins should search, save, read Working Memory, and distill. All plugins should align with this shared guidance.

Ambient space rule:
- Profile- or provider-owned space config should be the primary lane control when the host supports it.
- CLI-first integrations should honor `NMEM_SPACE` for one session-wide lane only when the host does not expose a better config surface. Legacy `NMEM_SPACE_ID` remains compatibility-only.
- General harness agents should support fixed, derived, or explicitly mapped lanes only when the host exposes that context truthfully.
- MCP/HTTP integrations should pass `space_id` directly when their runtime can do so.
- Do not add a second plugin-local “vault” abstraction.

## Plugin Development

See [`docs/PLUGIN_DEVELOPMENT_GUIDE.md`](docs/PLUGIN_DEVELOPMENT_GUIDE.md) for authoring rules, directory layout, and testing expectations.

## Submodules

`nowledge-mem-gemini-cli` is a first-class connector submodule with its own
release cycle. Keep its `package.json` / `gemini-extension.json` version,
`integrations.json`, tags, and parent submodule pointer aligned.

Trajectory extractors are recovery/fallback tools, not primary connectors.
Do not promote them into the normal connector update flow. Current
Antigravity users should use the native Google Antigravity plugin and
`nmem t sync --from antigravity`; the standalone trajectory extractor is only
linked as an external fallback for old cache-only sessions.

## Commit Workflow

When modifying this repo as a submodule of the parent `muscat` repo:
1. Commit inside `community/` first
2. Then stage the updated submodule reference in the parent repo

</details>
