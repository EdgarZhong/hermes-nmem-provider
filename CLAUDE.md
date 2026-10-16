# 个人 Hermes NM Provider 当前状态

## 自主口径收敛 · 待用户追认

暂无。本轮小脚本两步失败时保留已创建ID、仅修复Metadata是落实用户指定流程的必要工程细化，不是用户另行批准的通用重试系统。

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
