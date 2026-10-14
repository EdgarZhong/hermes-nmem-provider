# Personal Hermes 第三阶段：NM Provider 接入

状态：实施基线；2026-10-14。本文记录用户已确认的边界，不代表已经通过真实部署验收。

上游基线：nowledge-co/community 的 nowledge-mem-hermes 0.5.24；fork 起点 commit `4eafe6b620970bc3304e0192a81739a45fe99e4a`。

## 1. 目标与所有权

NM 是个人长期记忆、个人上下文、Space/Profile 策略的统一管理中心。Hermes Secretary 主 Conversation 是当前工作状态的所有者，Notebook/Noting 承担跨 Compaction 连续性。Agent 私有项目记忆不纳入个人全局记忆。

在 NM 同时补齐以下两项能力之前，用户不启用 Background Intelligence：

- Thread 入库后，由 NM Server 按单条 Thread 或来源配置是否自动蒸馏；这不是对外的 Distribution Policy，也不是导入规则。
- 自动治理具有具体 Thread/Message 级 Provenance，并能在定期审查中回读原始证据。

过渡方案是不自动蒸馏。由 Secretary 主会话提出、核验、审批后维护 Memory，复用现有审批与 Provenance，不创建另一套自动治理系统。

## 2. 一个插件、三个职责

只维护一个标准 Memory Provider；不另建 Thread Sync 插件，不连接 NM MCP，也不注册 nmem_* 函数工具。

| 接口 | 行为 |
| --- | --- |
| initialize | 读取 profile-scoped 配置，建立客户端及运行范围；不在后台任务初始化时读取个人 Bundle |
| system_prompt_block | 主会话稳定 Context Bundle + CLI/Recall 行为指导；排除 Working Memory |
| prefetch | 本轮输入的轻量 NM 搜索，返回候选索引 + 简短 Reminder |
| sync_turn | 成功完成 Turn 后归档获准会话的真实对话增量；归档不等于蒸馏 |
| on_session_switch | 维护身份及同步状态；不得将旧会话待同步数据绑定到新会话 |
| on_session_end / shutdown | 尽力补交获准范围的未同步记录，保留失败可恢复性 |
| queue_prefetch | 空实现；不在每轮结束后重新检索或预热 |
| get_tool_schemas | 返回空列表 |
| on_memory_write / on_delegation | 不镜像 MD 写入、不从任务汇报自动提炼记忆 |

关闭原生 MEMORY.md 与 USER.md：`memory.memory_enabled=false`、`memory.user_profile_enabled=false`。外部 provider 保持启用。不禁用整个 memory toolset，因为某些 Hermes 版本同时以其控制外部 Prompt 注入。

## 3. 运行范围

| 运行类型 | Bundle | Prefetch | Thread 同步 |
| --- | --- | --- | --- |
| 与用户交互的主 Conversation，包括用户显式新建/分支 | 是 | 是 | 是 |
| 独立定时任务自己的主 Session | 否 | 否 | 是 |
| Noting Task | 否 | 否 | 否 |
| 主会话或定时任务的 subagent/delegate | 否 | 否 | 否 |
| review、flush、dreaming、其他后台辅助 Session | 否 | 否 | 否 |

优先使用宿主提供的 platform/agent_context，以及可用的 session 元数据做轻量过滤。不新增严格 Conversation 身份鉴权系统；不根据文本内容猜测身份。可用的持久化来源与 delegate 标志优先于模糊的 primary 标签。未知或不可证明的后台来源不得自动获得同步权限。

Noting 不独立运行 Provider；继承主会话的冻结上下文与主动重新注入 Bundle 是两件不同的事。本阶段不修改既有 Parent-prefix/cache-parity 契约。

## 4. Context Bundle 与 Recall

Bundle 调用 NM `/context/bundle`，固定 `include_working_memory=false`；不得在失败时退回 Working Memory。保持 NM 已配置的 Space 与 host identity。会话内冻结；新会话或明确刷新边界才重新读取。失败不得静默伪造个人背景。

Recall 在 Hermes 原生 prefetch 时机执行，不新增 LLM preflight 或强制工具调用。使用 `nmem --json m search` 普通检索，不调用 ask/deep/dreaming/distill，不把正文自动塞入稳定 System Prompt。

索引仅包含 NM 返回的完整 ID、标题及已有的创建/更新时间；限条数和总体预算。不得截断 ID，不得把命中数量说成模型已经读过的记忆数量。不将正文或 Provenance 随索引注入。

全局规则：先判断当前上下文是否充分；涉及个人历史且缺少信息时，读取有用候选；候选不足时主动搜索；已有充分上下文时直接回答。短 Reminder 随索引返回，空命中或检索失败也应提示仍可按需 CLI 搜索。宿主跳过 trivial prompt 的原生行为不在本阶段强行更改。

搜索 timeout 只降级本轮候选；不用上一轮结果冒充当前结果。Provider 不注册额外工具，Agent 自主操作 NM 的首选通道仍为 CLI。

## 5. Thread 同步

同步由同一个 Provider 的 sync_turn 驱动；主会话与独立定时任务主 Session 均可归档，后台子会话不可归档。

Secretary 可提供可信 Conversation Ref 时，以它标识逻辑 Conversation；否则保留原生物理 Session 身份，不臆造跨 Session 合并。定时任务以自己的主 Session 身份归档。显式分支与 reset/new 不并入原 Conversation。

优先复用官方客户端、Thread import/append 和增量同步路径。原始 Hermes History 是证据权威；NM Thread 是归档副本，不能把 Compaction Summary、Recall 注入、Noting 输出冒充用户原话。不得将子任务 transcript 当作主会话 transcript。

重试不得改变目标 Thread；只有服务端明确成功才推进同步确认位置。没有经过测试的 exactly-once、跨 rewind 删除传播、完整多模态无损归档不得宣称已经实现。备份 Hermes 原始 state.db 与身份表仍然必要。

## 6. Memory Provenance 与写入

权威来源始终为 Hermes `(conversation_ref, message_uid)`，不是 NM Thread/Message ID。

NM Memory 支持自定义 metadata。使用 namespaced 对象 `metadata.hermes_provenance`，包含 `version: 1` 及 `sources: [{conversation_ref, message_uid}]`。一条 Memory 可有多个来源。content 只放知识正文；不把随机 ID 拼进正文影响召回，也不冒用 NM 原生 source_thread_id/source_message_indices。

CLI helper 只补齐原生 nmem 尚未暴露的 metadata 读写能力，不注册成 Agent 函数工具。辅助命令必须默认不写入、显式 apply 才写；创建/更新后回读验证；更新保留无关 metadata。其 apply 开关不是用户授权的安全证明，更不替代 Secretary 已有审批门禁。持有任意 shell 和 NM 写凭据的模型不能靠隐藏工具获得硬隔离。

来源 ID 必须来自 History 工具，不能由模型猜测。能够访问 Secretary History API 时执行精确证据验证；不可用时明确报告，不将字符串格式校验说成证据核验。

## 7. 已确认的 session_search 改造契约

这是第三阶段的 Secretary Core 工作，不属于此 Provider 插件的 Monkey Patch。本仓库保存契约，不能把未修改的另一个仓库说成已经完成。

- 以 Conversation 为一级实体分组；提供完整 conversation_ref、真实标题、创建时间和最后有效活动时间，不提供 UI link、物理 Session ID 或数据库行 ID。
- 每组 Ref 只出现一次；消息返回 message_uid、带时区 timestamp、role、content。
- 沿用角色过滤、时间约束和授权范围；Noting 仍只允许读取 Parent Conversation，不获得跨会话搜索权。
- Search 以关键词/词组实际命中处为中心截取原文，合并重叠窗口，多个不连续窗口用省略标记分隔，标记 truncated；不机械保留头尾，不用 LLM 改写。
- 总预算先缩减单条 content，再减少同组重复命中，最后减少 Conversation 组；身份元数据不截断。
- Search 不提供强制全文开关。Read 必须按完整 Message Identity 精确回读原文，可选邻居；正文不能悄悄截断。触及硬上限时明确报错或提供有边界的分段方案。
- 复用 Hermes FTS5，但最终通过 Secretary History Foreground 核验路径、Fork、Rewind 与 Compaction 原始证据，不凭物理 lineage 代替 Conversation。

## 8. 交付和验收

本次交付：fork 插件源代码、规格、配置/安装方式、CLI skill/helper、聚焦测试与执行记录。仅在此 fork 提交，不向上游或包注册中心发布，不改用户正在运行的 Hermes/NM 配置或真实记忆。

必须覆盖主会话/cron/各类子任务矩阵、短中文查询、索引预算、无工具注册、WM 禁用、错误降级、同步重试与切换、metadata 往返、CLI 默认不写和安装保留无关配置。

单元测试与模拟 HTTP 测试不等于真实 Hermes + NM 端到端验收。测试记录必须分别报告已执行项、未执行项和环境限制。

## 9. 接口依据

- Hermes Provider：`agent/memory_provider.py`、`agent/memory_manager.py`、`agent/turn_context.py`、`run_agent.py`。
- 官方插件：`https://github.com/nowledge-co/community/tree/main/nowledge-mem-hermes`。
- Bundle：`https://mem.nowledge.co/docs/api/context/bundle/get`。
- Memory metadata：`https://mem.nowledge.co/docs/api/memories/post`。
