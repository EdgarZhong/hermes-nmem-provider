# 个人 Hermes NM Provider 当前状态

## 自主口径收敛 · 待用户追认

暂无。

## 当前阶段

2026-10-20用户确认第一版正常可用，部署基本结束，本仓进入维护阶段。本轮已收口并由主会话亲审既有`~/scripts/`拼写与Memory显式Space改动、精简文档；无新增功能或真实NM写入，后续按维护任务另行推进。

- 实现与安装入口：[README](README.md)、[插件README](nowledge-mem-hermes/README.md)、[PHASE3现行§1–8](nowledge-mem-hermes/docs/PHASE3.md)。History由公开Secretary核心负责；本插件保持单一Provider，不注册NM模型工具、MCP或额外Skill。
- 独立创建入口`python3 ~/scripts/nmem-memory.py create`，preview／apply必须显式非空`--space`，Default传`--space default`；原件只读／可执行，扩展用`~/scripts/custom/`。不继承ambient目标，partial／unknown不盲重试；普通修改仍走官方CLI。
- study的Thread仍继承原考研Space，不配置`thread_sync_space`覆盖。`archive_enabled`不提供服务端只读权限；手动CLI的Space／批准仍由Prompt与流程约束。Background Intelligence保持关闭。
- 不承诺所有网络丢ACK／Cron组合的长期exactly-once或跨客户端原子创建排他；旧attach被服务忽略的失败样本保持，不冒称已修复。

## 本次验证与交付边界

整理起点`892c6bf20399d43ecc51f829a08ff9b19be2f120`，分支`codex/round3-local-completion`。既有10个dirty文件均已审查保留，无新增功能；独立工具SHA256仍`c3447cfd1535b32d324ecf50e89c86a808950680ac5f01188c1c41983e8a7e0e`。

官方runner定向3项通过（缺失／空／空白Space零I/O拒绝、直接函数零解析／POST拒绝、Provider正式Prompt路径）；5个相关Python文件按Core Ruff及C901≤20检查通过，diff检查通过。PHASE3历史附录原样。完整命令在ignored`temp-r3-personal/evidence/cleanup-20261020/verification.json`，不重复跑大型套件，不访问真实NM、服务器、凭据、用户数据或界面。

部署／工具保护／快照／Mutagen／回滚统一维护于[主仓运维记录](../hermes-secretary/docs/operations-log.md)，当前跨仓任务以[主仓CLAUDE](../hermes-secretary/CLAUDE.md)为准，不建平行看板。固定v5通过与早期NOT PASS各按其版本保留在[产品意图交付](../hermes-secretary/.autonomous/20261018-product-intent-review/final-delivery.md)及第三轮报告；提交、安装、加载、真实结果分别判断。
