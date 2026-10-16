# 个人 Hermes NM Provider 当前状态

## 自主口径收敛 · 待用户追认

暂无。本轮小脚本两步失败时保留已创建ID、仅修复Metadata是落实用户指定流程的必要工程细化，不是用户另行批准的通用重试系统。

## 第三轮本地托管实施（2026-10-17）

- 本轮已恢复本地完整实施；当前分支 `codex/round3-local-completion`，从冻结 main `97078118` 开始，已应用云端 P1 `676fec37`、P2 `e2c01dab`；主会话 review 后统一提交，当前未提交。
- P3 已实现，待主会话 review：completed 快照边界、明确 ACK 收据、路径变化停止、窄脚本与安装说明接线；公共产品只读。
- Actions 已由主会话关闭并读回；本仓已有 post-commit hook 与公共 `.githooks/post-commit` 一致，保留不改。禁止真实 NM 写入、真实 profile 修改和部署。
- 用户已明确正式模型／产品实测统一使用 `round3` 隔离 profile，由唯一实测 owner 启动。本子任务不另启真实产品 profile；单元／fixture 使用仓库 ignored `temp-r3-personal/` 内临时隔离库及本机 HTTP，绝不连接真实 NM。
- 环境：公共 PM `.venv` Python 3.14.7；联合 P1/P3 44 测试通过（P1 30、P3 14）；随后修复 reset 资格并通过 4 项定向测试（含 2 项新增，共覆盖 P1 31、P3 15），P2 基本模拟调用检查通过；Ruff 与 C901≤20 检查通过。命令与完整日志：`temp-r3-personal/evidence/r3-personal.log`、`p2-basic.log`。不是独立门禁、真实 NM 或模型验收。
- 定向修复：识别原生 `_reset_from`，合法 reset 使用独立 Conversation／Thread；安装器改用 Hermes 锁定的 ruamel.yaml，保留 YAML 1.1／重复键拒绝；脱敏用例使用 host 支持的 Bearer 标记，并验证在去除 tool 行前对整批脱敏；相关失败项已复测关闭。
- 公共 host 缺口已交 C9：finalizer 需将 completed/failed verdict 传到外部 memory 同步门禁；不由个人 Provider 修改公共核心。
- 历史 `test_personal.py`／`test_security.py` 的旧 helper、Bundle 缓存及未限定 History 边界断言已失效；本任务未改这些白名单外文件、未运行历史整目录测试。主会话 C10 需按现行规格收口，不能直接沿用旧全目录命令为最终入口。
- 唯一轮次索引及七项交回报告位于并列公共仓库 `.autonomous/20261016-round3-secretary-nm/`；个人返回报告为 `personal-report.md`。

<details>
<summary>2026-10-16 文档冻结时点历史</summary>

## 第三轮文档冻结与暂停（2026-10-16）

- 目标：单Provider稳定Bundle、输入前Recall、合格Turn归档及个人Memory来源保存，与公开Secretary第三轮分别实施；界面后置。
- 当前仅完成源码承接和文档对齐。启动代码基线为`f9733fcb31a0e6f468eabe6419cb76444fe16b30`，本地目录`/Users/edgar/code/hermes-nmem-provider`。产品代码未改、未安装、未部署、未访问或写入NM服务。
- 用户要求文档基线后暂停：不进入writing-plans、代码实施或运行验收。根README、AGENTS、本文及插件规格和入口一同纳入文档基线。
- 唯一轮次索引：`../hermes-secretary/.autonomous/20261016-round3-secretary-nm/snapshot-index.md`；双仓库精确基线见同目录baseline.txt；用户明确本次不撰写交付或交接文档。
- 已确认：必须保存metadata.hermes_provenance；仅用小脚本调用官方CLI创建、取返回ID、补Metadata，复用运行主机配置。Main提供正文与来源；不复刻官方CLI，不保留旧helper的完整直接API写入体系。
- 验收例外：用户明确省去小脚本严格验证，不安排其真实NM测试写入；只做实施基本检查，联通问题留待以后云端部署。这不是其他Provider或公开核心免验。
- 环境：本轮本地隔离验收，以后部署云端。自动Thread归档的真实NM写入尚未授权；需要时另行收敛，不能擅写已有个人记录或改治理配置。
- 调查事实：本机nmem 0.10.101的add/update help无任意metadata入口；add/update支持labels，source-msg不是任意Hermes元数据入口。已有client能复用环境变量／config，但与官方CLI有效覆盖规则是否完全一致仍须实施时核对；未读取或打印真实凭据。
- 旧代码：personal_cli.py仍直接HTTP创建／修改Memory，需在恢复后改为新窄路径。PHASE3下半部旧session_search方案已失效，上半部§1–7是本轮个人依据。
- 已有证据：docs/TEST_REPORT.md记录41466f1版本的Linux/Windows模拟服务测试；不代表当前版本、真实Hermes或真实NM通过。本次未运行产品测试，两项独立门禁均未执行。
- 文档检查：已通过diff格式、文档入口、现行JSON及旧PHASE3原文保留检查。GitHub Actions原为enabled=true，本次不修改仓库设置；文档提交用[skip ci]，不把未运行写作通过。主仓库Actions关闭事实不推定到本仓库。
- 恢复：用户明确继续后，依据冻结版本编制计划，核对真实Hermes接口与运行环境，分配实现及后续Verification／Validation；部署另行授权。

</details>
