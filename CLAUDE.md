# 个人 Hermes NM Provider 当前状态

## 自主口径收敛 · 待用户追认

暂无。2026-10-18窄helper一次正式API创建并携Metadata为用户明确修订，不是Agent自主扩大路线。

## 五分钟数据库快照与同步增量（2026-10-19；主会话已亲审，获授权接通中）

- 用户最新定案：每5分钟云端本地SQLite快照；Mac离线不影响云后端，不无限积压或追加日志。云唯一运行writer，本机为冷态数据库副本；workspace整个目录双向、每Profile四项非凭据配置/SOUL双向、完成数据库快照单向，rawDB绝不直接双向。
- 明确必需库Alex/state.db、study/state.db；固定known optional为两Profile的projects.db和nowledge-mem-personal/receipts.sqlite3，仅存在时纳入，后续新出现仍可进入下一快照，不扫描未知DB。接收端完整预验与同步外已验current/previous两槽后，允许原子落到对应本机批准DB路径；配置/SOUL不从快照覆盖。
- 本机活库／打开句柄／WAL/SHM/journal拒绝覆盖，不删sidecar、不杀服务、不自动merge本机写入；初次冷库原件另保留，不删原Pi库外部备份。单接收锁、幂等、失败准确报告、固定status文件及有限日志。
- 仅扩个人deployment窄helper及对应fixture测试，准备项目Mutagen/SSH/定时器草稿；保护既有5个Mutagen sessions和daemon。主会话已亲审同SHA包并授权仅四文件提交／自动push和真实三lane、timer、冷镜像激活；云ready已满足。激活前以真实scratch验证allowlist，三项非SOUL配置受限备份和预对齐；SOUL只核冻结SHA，秘密／SOUL差异／活库保护不绕过。Provider/Prompt不改。
- 依据主仓`.autonomous/20261019-cloud-deployment/`与最新用户口径；证据统一放主仓ignored `deployment-release-20261019/sync/`。已通过旧9节点仅按未变路径复用，不重开大型套。
- 新增 `publish-cycle`／`receive-cycle` 已完成，Mac真实SQLite/句柄/sidecar/原子落库fixture及独立CLI入口共19个不同pytest节点通过，分6次定向调用取证；原9节点未重跑。首轮full health发现main新增分支链HX011，改为命令映射后全量相关health命中0；冻结Ruff／复杂度／结构通过。helper SHA与准确命令见sync/manifest.json及commands-and-results.json。
- 三lane Mutagen、专属无UI SSH代理、systemd五分钟timer、Mac launchd五分钟＋到件触发草稿齐；正常等待/暂停不报错风暴、真实拒绝/部分失败CLI退出2，状态固定覆盖，任务输出/dev/null。发布前保留512MiB加两倍已知源库/WAL工作空间；源/接收互斥锁及受管残留清理，无无限时间戳包。Mac首次原DB以initial固定硬链接保留，已验两槽独立于是否已落库。
- 云初始数据就绪由主会话明确交接（48/6065迁cwd完成、study0/0），本包随后获明确release；真实接线、对齐、冷镜像及离线恢复证据追加sync/activation/。现5个Pi Mutagen sessions/模式/端点保持，最后停清任务仍由root另行执行。激活前先核云最终配置无内嵌凭据，安全预对齐本机静态文件、SOUL冻结SHA不变，禁止two-way-resolved或Mac旧配置覆盖云生产。本次只按release安装同SHA helper与专属配置／unit，SOUL/.env/model/NM不改，业务数据仅批准的在线backup与Mac冷镜像。

## study 自动 Thread 同步 Space 拆分（2026-10-19；功能保留，study当前继承原Space）

- 用户最新纠正：拆分功能保留，当前study的自动Thread继续考研Space，不投递Default。待部署Home `/Users/edgar/.hermes_profiles/study` 保持 `space:"space"`、`archive_enabled:true`，不设置 `thread_sync_space`；Bundle、Recall、Active space及Thread均继承原Space。可选字段未配置保持旧Space与收据键；显式字符串仍支持名称／别名及Default，空串表示Default，错误类型拒绝初始化。
- 本包仅个人 Provider、对应测试与配置文档；不修改任何 Prompt、Memory helper／批准策略、公共核心或真实运行数据，不迁移旧 Thread／收据／Memory；初始化生效，无热切换。它是固定 v5 后的配置增量，不回写旧门禁结论。
- 实施基线个人 `4d4a00e56316119ac2e66bc8ffe2c98ece64eaa5`、公共 runner `c80e0d02b51ec2ddfe5feced776c842480f84516`；定向 RED／修复证据与精确补丁存公共 ignored `.hermes-dev/product-intent-review-20261018/study-thread-space-split/`。主会话已亲审接收原6文件及21节点证据；本次获授权只安装新study插件并提交原6个源文件，保留既有hook自动push。实际安装／提交／远端HEAD见同目录 `installation-and-commit.json`。
- canonical runner 配置／链路定向 19 个顶层节点通过（Provider 9、正式Thread链路10，runner墙时3.5秒）；含新配置兼容／错误类型／重初始化、Default未知上传分页确认、真实消息锚点分叉与后续冷实例增量、原Space的Bundle／Recall及Prompt保持。原始RED与两次测试夹具修正失败保留。随后补充跨Space同ID保护：显式覆盖且无匹配账本时仅明确404允许首批导入；已有任意Space同ID／查询不明均暂停，不认领或迁移。新增2个负例RED后，受影响5节点2.8秒通过（与19节点合计21个不同顶层节点）；无新大型回归。导入前只读检查不保证服务器原子创建排他。不是产品真实NM／模型验收。
- 冻结Core Ruff配置、C901≤20、函数≤300行／嵌套≤6／文件≤2000和diff检查通过；全部模块常量及Prompt构建函数与个人基线AST一致。仅直接JSON配置新增可选键，setup表单保持；无真实NM读写、服务、UI／显示状态操作。完整报告与指纹见上述证据目录 `report.md`／`manifest.json`。
- 新study已由正式installer preview／apply完成10个FILES插件安装，源码／落盘SHA全匹配；config.yaml、.env、nowledge-mem.json的bytes及mode保持，未新增override、默认模型或Idle参数。两份SOUL未打开／修改，未接触Alex／旧测试Profile／DB／全局registry。仅准备静态云端installer包，未SSH／Mutagen／服务启动；既有21节点不重复运行。

## 当前交付与新部署筹备（2026-10-19）

- 固定v5产品意图PI01–26已由独立Astra Verification及6.1 Validation全范围PASS；主仓E04旧分支尾部读取缺陷已修复并经原A冷UI关闭。下方v3/v4及旧NOT PASS均保留历史时点，不作为当前状态。当前判定与唯一总体看板在并列主仓CLAUDE和`.autonomous/20261018-product-intent-review/final-delivery.md`。
- 用户确认复用既有Mutagen通道：配置/SOUL同步、云端唯一运行DB生成一致性快照回传，其它运行态无需同步。独立运维工具`nowledge-mem-hermes/deployment/hermes-sqlite-snapshot.py`已亲审接收，安装`~/scrips/hermes-sqlite-snapshot.py`，SHA `6d9d25bf78c526692dde70618f638b837be960e4fc6b134a80892a8a0852d237`；不依赖Hermes、不进入Provider工具/Prompt、不激活后台机制。
- 精确DB名单、同步外暂存、完成后固定ZIP原子发布；接收端全包及SQLite验证后提升同步外current/previous已验槽，坏包不覆盖已验副本；恢复只到不存在的新根。9个不同真实SQLite节点通过，含WAL并发及损坏/半包拒绝；Ruff/结构指标通过，未重复全套。原始证据位于并列主仓ignored `deployment-preparation/`。
- 本工具是固定v5之后运维筹备增量，不能冒称v5门禁覆盖。两个新Home仅配置/插件；用户SOUL/Alex历史库保持。生产模型/联合Idle/快照频率及正式DB清单未定，无云端/SSH/Mutagen/定时器/服务启动，未对真实Home执行快照或恢复。

## 用户最新授权：独立工具与NM Thread分叉同步

- 用户指定NM独立小工具放运行主机 `~/scrips/`，本机／云端一致，不依赖Hermes／插件目录／HERMES_HOME／cwd。metadata owner实施单一独立创建工具，正文与通用Metadata由调用方提供，既有一次POST／真实ID回读／unknown不盲重试约束保持；无真实NM写入前先受控验收。
- Thread原生Message ID契约研究与自动分叉接续由两个独立owner继续；首条引用旧NM Thread＋最后共同NM原生Message ID，第二条起只同步分叉后缀，不复制共同前缀、不覆盖删除旧Thread。正式可见术语改“NM Thread同步”，兼容配置/API名不强行重命名。
- 用户已批准PI-26精确英文，root已仅替换此前追加的长句，使用 `python3 ~/scrips/nmem-memory.py create`；其它Provider提示不动。独立工具与Thread包已root亲审并以v4正式安装加载。B真实模型唯一apply创建后，独立同ID CLI／GET确认准确来源Metadata持久存在；B自有资源0。A实际编辑分叉新Thread仅接续头＋新UA三条，共同4条未重传，旧6条不变、pending清空。正式History REST另发现退休旧尾部仍显示，属主仓另案；不以NM底层通过代签UI。root负责主看板和部署SOP，子Agent整包交回、禁止流水账及派生。

## PI-22历史窄包：Provider直接提示，撤销Skill方案（当时磁盘同步／运行未加载）

**用户后续纠正已落实：仅创建Metadata错误需删除后重建，普通字段可经批准通过CLI修改。** 该范围纠正后的实际Provider提示定向1项通过（0.2秒）、Ruff及diff检查通过；两测试Profile磁盘已同步，无重启／NM写入／新模型调用。



- 用户明确撤销nm-cli Skill方案；创建规则直接进入个人Provider `_MAINTENANCE`：获批Memory仅现有personal_cli.py create一次携正文／标题／类型标签／Space／metadata.hermes_provenance；其它操作官方CLI；普通Memory字段仍可经批准用CLI修改；仅创建时Metadata错误须获批删除后全新创建，partial／unknown不盲重试。既有attach仅兼容保留，不引导模型使用。
- 本包只改个人Provider提示、插件入口、安装器本次技能接线与必要文档／相关定向测试，不改公共核心／框架Prompt／helper协议或服务；双测试Profile仅安全文件同步，旧活runtime/root/cache不刷新。canonical runner仅选4项相关既有测试通过（1.4秒），相关5个Python文件Ruff及diff检查通过；helper旧套件复用、未重跑。两测试Profile仅同步personal_provider.py＋__init__.py并移除原nm-cli SKILL.md，原件ignored备份；本次Metadata范围纠正后Provider SHA为f14d2cfeae24a974bb1ccb1a6333afa192c1fb3147859ebf8648bd331197b081，helper仍75d8dca1…cf3e。PID32366/77413未重启，没有活runtime/root/cache刷新；尚未验证加载或真实模型行为。
- 刚添加的两测试Profile skills.auto_load已通过正式config unset撤销，原先absent恢复absent；仅清除本插件自有external_dirs项，保留其它现有配置，未整份恢复旧config。.env／SOUL指纹未变；B新Conversation／模型／NM调用均0，准备包停止。原始备份与失败留主仓ignored metadata-live-evidence。
- A唯一合成Memory（ID前缀0c75…）字段创建正确但未读Skill／未用helper，正式同ID GET无hermes_provenance；NOT PASS永久保留，不修改／删除／重建。三个manual Noting已结算、自有资源0；不据此宣称helper真实API来源旅程或refs型通过。

## 先前v3产品意图复审整改（2026-10-18，历史加载与实测证据）

- 主仓本轮入口：`../hermes-secretary/.autonomous/20261018-product-intent-review/`；独立Astra/high总门禁仍未PASS，其余实现/调查均6.1/high。此前v3 Provider、helper与76行Skill已由官方安装器同步两个测试Profile，并由主仓dashboard进程PID32366加载；该时点配置/SOUL/政策保持，之后Skill撤销及新提示磁盘状态以上节为准。下方此前版本与真实证据按历史保留，不作为当前安装指纹。
- root已review接收helper `--space`命令层级与安装器原生`skills.external_dirs`修补：新6项＋既有相关6项通过；隔离新home实际根索引/skill_view与clone所属路径正确。Skill只纠正一行CLI语法，未改行为政策。
- root已review接收既有request_json的单一默认curl传输：12不同节点分批通过、Ruff/复杂度/diff通过，未改endpoint/key/UA/CF；需要本机native curl，缺失明确失败，不自动回退。原urllib403/1010保留为失败。
- **旧附件失败历史保留：**唯一获准旧合成Memory做2GET/1Metadata-only PATCH/0创建，正文、标题、标签与13个无关Metadata字段保持；服务忽略hermes_provenance，回读缺失，helper准确partial。随后唯一/openapi.json GET403；官方文档/本机前端未提供可据以修复的任意Metadata更新契约。停止猜路由和反复写，未获新范围不另试PATCH，不把来源塞正文；后续用户仅批准新Memory创建改为一次正式API携Metadata，见下条。
- **E02源码已review／安装，真实验收仍进行中：** `personal_cli.create`复用现有curl `request_json`一次POST `/memories`并携`metadata.hermes_provenance`，官方CLI解析Space后核对真实存储ID；unknown不重试，partial保留真实ID和来源责任，旧`attach`兼容语义保持。受控loopback与Skill最小同步差异已由root接收并正式安装；当前attempt-02已转root后备thin UI。按root最新现场回报，模型经native CLI创建了新合成Memory（ID前缀`0c75…`），后续正式GET已确认Metadata缺hermes_provenance，A失败保留；helper API真实模型路径未成立，不能据创建响应判E02/VP-02通过。主仓ignored `metadata-create-api.md`、`archive-pause-feedback.md §8`及`metadata-live-evidence/thin-ui-handoff.json`记录源码／安装／后备交接；thin交接是切换时点记录，后续结果待root亲审。
- 报告在主仓ignored `product-intent-review-20261018/`：repair-nm-wiring.md、repair-metadata-transport.md、metadata-contract-research.md。原始来源/响应/凭据不进Git；技能实际模型使用、提案查源/标签、精确来源持久化尚不能宣布通过。代码提交、安装与PID加载均不代替真实Metadata回读或整轮通过；后续按主仓统一集成与root亲审。

## 本阶段收口 · 个人接入已安装并取得定向真实证据（2026-10-18）

- 主会话已review接收本阶段7文件，安装到本机隔离主助手/考研助手Profile；主助手 `archive_enabled=false`，考研助手true。已安装client SHA256 `3246b0c571e39a67628f7675bbad66f74a0d9b1d085c80c63dd5ed7b86641b47`，provider SHA256 `9bc6e21f08f8469810988bdc310e02d100573eae45bf4703612434db014c0ca7`；Prompt/Skill正文未改，个人依赖未进入公开核心。
- VP-01第二次正式聊天复验已由root接收：普通Main首批自动归档22条，下一Turn同Thread/同Space增量到24；旧前缀、正文与receipt一致，回收后仍24且无重复。主助手receipt仍0。首轮16次MemHTTPError、第一次修补后4次RuntimeError及诊断均保留；本次不宣称Cron/网络丢ACK/长期exactly-once已真实覆盖。
- VP-04复用5秒运行配置下3个正式Turn通过证据，不改产品默认预算、不重复测试。**整轮Validation仍NOT PASS，VP-02提案/来源传递行为缺口未关闭**；VP-03自述偏差、VP-05待澄清体验观察及静态Verification历史状态保留。
- 权威验收结果：并列主仓 [validation.md §5.1–5.2](../hermes-secretary/.autonomous/20261016-round3-secretary-nm/validation.md)。本地ignored报告入口：[Thread修补/诊断/真实复验/提交同步](../hermes-secretary/.hermes-dev/validation-personal-20261018/provider-thread-transport.md)、[Bundle兼容](../hermes-secretary/.hermes-dev/validation-personal-20261018/provider-bundle-cli.md)、[归档控制](../hermes-secretary/.hermes-dev/validation-personal-20261018/provider-archive-control.md)。原始私人数据/凭据不提交，本阶段不重跑有效测试、不重装/重启或新做NM读写。

## VP-01 · Thread 官方CLI传输修补（2026-10-18）

- 首轮真实Validation保留考研助手16次MemHTTPError、0收据/Thread的失败。此任务只修自动Thread正式上传，不重跑业务链、不写真实NM。归档仍由原owner、原receipt和原严格ACK管理；不改任何Prompt、模型路由、Cloudflare/key或公共核心。
- 个人client改用官方 `threads import --file` 的checkpointed suffix入口：同Thread/Space/source/title，已有ACK计数和稳定重试key；0600临时JSON避免长argv，异常也清理。官方append-file发送服务器本地路径且append输出覆盖服务端Thread ID，不适合此远程路径和原身份校验，因此未采用。原未知/负ACK/错Thread拒绝与prefix分歧拒写保留。
- 首版真实SessionDB/MemoryManager＋官方nmem CLI→loopback HTTP取得20项定向PASS（3.6秒），但首次正式复验仍4次RuntimeError；一次授权同Thread诊断确认thread_not_found，修正首批普通创建/后续checkpoint，补3项RED→定向7项PASS（2.6秒），含batch身份与安全分类。Ruff/C901/diff通过。其后正式22→24条实测已安装并由root接收，详见顶部；不把旧20项或诊断请求冒充正式通过。

## Validation 准备 · Bundle 官方CLI兼容（2026-10-18）

- 真实接入中urllib Bundle请求被Cloudflare403/1010拒绝，官方CLI同目标读取正常。现将个人client Bundle改用既有 `_cli` 的官方 `context read`，保留source_app、host identity、profile Space、no-working-memory、原配置/timeout与失败处理；不改Prompt、Cloudflare、密钥或公共核心，不重复请求被拒HTTP。
- CLI保留 `working_memory` 的省略外壳；仅在omitted=true且content为空时归一null，兼容原有严格Bundle校验；实际内容或未明确省略仍拒绝。定向12 PASS，外壳适配后仅5个client节点复测PASS；Ruff通过。真实Default/考研Space读取与原parser均成功，WM排除、Space归属均匹配，只保存状态，无正文/写入。
- Bundle包已获主会话review接收并安装，真实读取通过；报告为公共ignored `.hermes-dev/validation-personal-20261018/provider-bundle-cli.md`。该包当时不改Thread路径；后续Thread修补及真实结果另见顶部与VP-01段，不回写旧证据结论。

## Validation 准备 · Profile 自动归档控制（2026-10-18）

- 用户已授权开始双 Profile 本机环境搭建与必要修补：主助手读取 Default 禁自动写入，考研助手在专属 Space 可写；此授权覆盖本阶段旧 fixture-only / 真实NM未授权限制。本任务仅修个人插件，不启动真实会话或写 NM。
- `nowledge-mem.json` 新增布尔 `archive_enabled`，默认 true 保持既有行为；false 禁止完成 Turn 归档、会话结束重试及实际 Thread 上传，Bundle/Recall 保持。初始化时读取，不热更新；框架 Prompt、tool guidance、公共核心、模型路由均未改。
- 开关只抑制 Provider 自动 Thread，不构成任意 terminal CLI 的服务端只读权限。主助手 SOUL/配置与正式部署由主会话另行接收安排，不据此声明整个 Agent 只读或 Validation 通过。
- 定向真实 SessionDB/MemoryManager＋loopback HTTP：新增3场景 RED，修复后两文件 canonical runner 60 PASS（3.1秒）；新布尔配置拒绝7种非布尔值。该包当时未跑全量或连接真实 NM；详细指纹/命令/限制见公共 ignored `.hermes-dev/validation-personal-20261018/provider-archive-control.md`。实现已获主会话review接收并安装，正式主助手零归档证据见顶部；后续Bundle/Thread传输适配分包保留。

## V51 Recall 时间投影修复（2026-10-17）

- Astra首审发现指针日期直接输出epoch／微秒；仅在candidate_index的可读出口复用Hermes原生秒精度formatter，正式prefetch显式传owner profile。内部来源响应、ID、Bundle正文、资格与网络不改。
- 合法绝对时刻带时区并秒显示；纯日期保留；无zone或不可解析的可选日期省略，候选和其它正常字段保留，不伪造瞬间。主会话已review两文件及证据指纹接收。
- 定向RED后8顶层节点＋17子用例PASS；Ruff、C901≤20及diff检查通过。未重跑46／39整组；统一最终回归的46项canonical补证已通过，日志在公共final-regression。
- 本包不操作round3或真实NM。首轮独立Verification尚未通过；新版本待全范围独立复审。报告见公共c10-personal-report.md §8，完整证据temp-r3-personal/evidence/v51/manifest.json。

## C11-P 正式接线开发取证完成（2026-10-17）

- 公共生产版本 `f66a8f80b4bab39b0a785a552019c91a6e9becba`，个人 `8682ff858a56ac735098ee6289d4ab547d3ae755`；主会话已review接收六场景正式原生host→loopback fixture→真实DeepSeek证据。
- 统一round3隔离profile；12个completed Main Turns、14次实际Main请求。短CJK Recall、503当前输入诚实反馈且History仍可用、同Turn稳定root、有效root冷恢复、真正成功压缩后fresh Bundle均有实际证据。24条UA正文映射真实UID，同Ref／Thread只追加suffix，明确ACK与收据前缀完全一致。
- 两次summary-would-grow no-op如实保留；只有最后26→10消息／30,358→21,126 tokens计成功。未改生产或tests，未访问真实NM、重测P2或执行部署。
- 原配置原bytes已恢复，插件恢复为原不存在；自有gateway／driver／fixture进程均停止，归档ACK完整、lease为0，round3已释放。准备驱动未独立保存native子进程退出码，不宣称该码0；driver退出0，最终显式close未发出但stop关闭stdin并等待退出。
- 完整报告：公共 `.autonomous/20261016-round3-secretary-nm/personal-host-report.md`；ignored证据：`temp-r3-personal/evidence/c11-p/manifest.json`。统一Verification已初审；canonical 46项补证已通过，39项既有有效测试复用。独立门禁尚未通过，真实NM服务及云部署仍后置。

## C10-P 个人旧测试收口（2026-10-17）

- 起点／当前已接收实现：`57d0abb854f4ae71207b85bf247afa446d5ac65e`，分支 `codex/round3-local-completion`；P1/P2/P3已由主会话review并提交。本次仅改 `personal_tests/test_personal.py`、`test_security.py` 与本状态记录，不改生产实现、真实profile或依赖。
- 两旧文件按现行PHASE3收口：Bundle原生重建时重新读取、长opaque ID完整保留、真实SessionDB／UID与合法压缩续接、包含tool的整批egress、缺失host scrubber拒绝；原有scope/offline/增量收据/重写停止等断言保留。
- 退出10个旧完整HTTP写入／强制History成员校验／expected-sha／通用回读协议测试，仅保留2项现行窄helper基本模拟（preview无I/O、metadata-only准确provenance与无关字段保留）；没有新增严格P2或真实NM写入。
- 测试入口：公共canonical runner＋公共PM解释器。插件目录带连字符，pytest直接收集会错误按无package导入`__init__.py`；在 ignored `temp-r3-personal/evidence/c10-p/runner/` 放两测试源码symlink即可，测试内`__file__.resolve()`仍指原源码，不复制或改生产包。准确命令见公共 `c10-personal-report.md`。
- 真实baseline 32通过／15失败；修复后受共享真实host fixture影响的两文件共39项通过（1.3秒）。第一次定向修复的3例仅因临时目录先于DB.close清理失败，已调整cleanup顺序并通过。Ruff与C901≤20通过，格式化AST不变；`git diff --check`通过。
- P1/P3新46项未重跑，既有P2基本脚本未重跑；不访问真实NM、真实模型、产品profile或云端。本包不复验公共C9-H；正式模型／产品测试仍仅由唯一owner使用round3隔离profile。
- 证据：`temp-r3-personal/evidence/c10-p/{initial.log,baseline.log,repair.log,shared-fixture-final.log,ruff.log,complexity.log,manifest.json,c10-personal.patch}`；交回公共 `.autonomous/20261016-round3-secretary-nm/c10-personal-report.md`。C10-P已由主会话亲自review接收；39项证据复用，根与插件README同步canonical入口。个人正式host→fixture开发复测已完成，见上方C11-P记录。

## 第三轮P1/P2/P3首次交回记录（2026-10-17，后由57d0abb接收）

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
- 当时确认：必须保存metadata.hermes_provenance；旧路线为官方CLI创建、取返回ID后补Metadata。2026-10-18用户仅将创建改为窄helper一次正式API携Metadata（PHASE3§4.1）；其他CLI／来源／同配置／未知失败原则继续保留。
- 验收例外：用户明确省去小脚本严格验证，不安排其真实NM测试写入；只做实施基本检查，联通问题留待以后云端部署。这不是其他Provider或公开核心免验。
- 环境：本轮本地隔离验收，以后部署云端。自动Thread归档的真实NM写入尚未授权；需要时另行收敛，不能擅写已有个人记录或改治理配置。
- 调查事实：本机nmem 0.10.101的add/update help无任意metadata入口；add/update支持labels，source-msg不是任意Hermes元数据入口。已有client能复用环境变量／config，但与官方CLI有效覆盖规则是否完全一致仍须实施时核对；未读取或打印真实凭据。
- 旧代码：personal_cli.py仍直接HTTP创建／修改Memory，需在恢复后改为新窄路径。PHASE3下半部旧session_search方案已失效，上半部§1–7是本轮个人依据。
- 已有证据：docs/TEST_REPORT.md记录41466f1版本的Linux/Windows模拟服务测试；不代表当前版本、真实Hermes或真实NM通过。本次未运行产品测试，两项独立门禁均未执行。
- 文档检查：已通过diff格式、文档入口、现行JSON及旧PHASE3原文保留检查。GitHub Actions原为enabled=true，本次不修改仓库设置；文档提交用[skip ci]，不把未运行写作通过。主仓库Actions关闭事实不推定到本仓库。
- 恢复：用户明确继续后，依据冻结版本编制计划，核对真实Hermes接口与运行环境，分配实现及后续Verification／Validation；部署另行授权。

</details>
