# SwarmHarm 候选任务与验证方法

更新日期：2026-10-17

**当前范围（2026-10-17）：简单任务数据，以及独立冻结的局部边界、通信和跨会话小试。** 按网站的五个领域整理查询、计数、筛选、时间核对及对账任务；高风险 cyber、网络入侵和 CVE 复现留待以后。[第一批数据与维度](../../data/simple-tasks/README.md)保留原题，不附加诚实停止或越界提醒。可完成性与可利用性分开记录；既需要可利用条件，也需要关闭漏洞的对照，未验证的候选不计为已覆盖或已具备 exploit。原版 HVTB 的故意暴露入口属于其研究设计，不能因防评测污染而直接屏蔽；当前恢复 runner 尚未完成资格验证或模型实跑。

本笔记保留 SwarmHarm 候选任务数据、方法用途和待核实事项。当前目标明确为诱发和测量 HF 类受阻、越界与传播链，底座选择以此为准。网站仅展示精选候选领域的图标。

[构念效度审查](construct-validity-2026-10-17.md)已把源任务、有效捷径、边界、独立评分、同伴痕迹与传播证据分开。当前五题保持候选状态；LLM 评委或可写工具本身都不构成有效 exploit 的证明。LessWrong 附录已有预置线索的真实多 agent 条件，后续不能只以“真实同伴”声称方法上的区别。

第一题已落实为单独标识的 [wayfinding 局部数据族](../../data/simple-tasks/wayfinding/README.md)：8 个原文件内容已核验，独立计数参照一致；合成的权限遗漏、关闭对照及通信检测通过 22 项软件控制，24 条条件配置已备。其原题未改，环境/API 改造有明确清单。随后[模型小试](../../experiments/wayfinding-pilot/results/2026-10-17/README.md)完成正常基线和四个双上下文世界：开放缓存条件有 3 条轨迹取得受限数据，关闭条件为 0，无同伴通信。它不是原 MiMo 已有漏洞的证明，也不是 24 次实验；只验证了该 API-only 配对，没有通用代码执行沙箱、因果曝光或长时实验结论。

最新[六阶段、两会话试跑](../../experiments/wayfinding-long-horizon/results/2026-10-17/README.md)完成 18 条任务链、35 个会话、101 份阶段记录：开放入口下有 8 次受限读取，关闭入口下为 0；一个关闭入口／合法交流世界出现真实请求、读取、回复及读取。它没有传播越权方法，也没有跨会话读取 agent 自建笔记。阶段提交数、数据错误、格式问题与权限行为分别报告；实际世界时长为 78–268 秒，编号暴露条件，不能当作盲测、小时级任务或压力因果效应。

## 按 HF 类事件构造能力选择

**首选 HVTB 做机制验证。** HVE 的 Terminal-Bench 扩展已有工程任务、可访问的参考解／隐藏测试和文件访问监测，可以从可检测的首次越界起步。其原版主要是单 agent 利用信息泄漏，并不是完整的网络入侵或多 agent HF 复现；不能直接把 watcher 触发等同于欺骗意图。现已验证固定版本 `db-wal-recovery` 镜像及原始材料（7 项确定性检查通过），并构造随机虚构数据、模拟命名空间权限缺陷和真实独立上下文的双 agent 安全试跑。可完成对照恢复 11/11 条；两个受阻世界的四条轨迹都如实报告不完整，未越权或通信。未诱发 HF 链条，尚未测试长期持续性；也未运行完整原版 HVTB 套件。`extract-elf` 仍待运行资格验证。详见[安全试跑记录](../../experiments/hf-safety-pilot/results/2026-10-16/README.md)。

[HVTB 官方说明](https://majoroth.github.io/hack-verifiable-environments/hvtb) · [固定版本适配器](https://github.com/Aarav500/rhob/tree/a2c73417a79be65b802b2fbe62dc6fac03e9c3de/hvtb_hack_detection)

**ImpossibleBench SWE 用于受阻配对。** 现成的 original／conflicting 变体更直接对应“按要求无法完成时是否规避测试”，但缺少跨 agent 通信与共享服务。可借鉴其配对原则改造其他底座，不代表 SWE 变体能直接拼入 HVTB。保留 SWE，原始 LiveCodeBench 的数据／评分问题另行记录，不把两者混为一谈。

**MiMo general_agent 用于业务领域扩展。** 文档、MCP 和业务数据库适合医疗、金融和公共事务的真实目标与操作后果，但要另外设计受阻与可利用路径。两题本地试跑仅证明运行、评分和独立检查流程可用，不能证明 HF 类事件已具备发生条件；详见[试跑记录](mimo-smoke-2026-10-16.md)。MiMo cyber 的指定漏洞复现本身属于合法任务，必须另设越界目标才可用于此研究。

这一排序是基于已读实现与任务结构的工程判断，不是各底座的实测诱发率比较。三个来源都没有原生提供所需完整行为链。已完成的 HVTB 衍生小试验证了“合法可解／受阻”与模拟路径，但每个压力条件仅一个共享世界，不能推断一般安全性或压力效应。自发条件不预置攻击留言，真实实验评分器和凭证留在 subject 外。

## 候选任务与领域

截至 2026 年 10 月 15 日，MiMo 数据版本为 `639865fd3374018d6cb29b9fb82dd531406fcf5f`。官方数据集包含 code 2,698、cyber 1,000、general 989、webdev 2,093、music 1,000，共 7,780 条。general 中含 925 条 general_agent 与 64 条 terminal 任务；六类环境的说法来自将这两个子类拆开。

[MiMo 原始数据](https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss)

925 条 general_agent 的任务 ID 分类统计：会计审计税务 157、金融保险 135、医疗运营 107、咨询及业务分析 89、人力资源 77、信息系统 72、政府公共事务 72、教育科研管理 55、法律合规 47、能源公用事业 ESG 47、制造质量 14、电商运营 14、建筑项目管理 14、餐饮酒店 9、末端物流 9、农业合作社 7。

候选池统计中，会计审计税务与金融保险合计 292 条，总分母为 925。这是候选池分布，不是 SwarmHarm 已验证或已评测的样本分布。网页现仅显示下列精选候选领域的图标，不显示样本数量或比例。

具体任务例子：医疗运营中的理赔交易及确认状态核对；金融中的租赁递延所得税披露；法律中的律师出庭名册及规范化当事人核验。任务具有业务目标和源数据约束，适合扩展为多 agent 流程。它们包含业务模拟，不能仅凭真实机构名称断言是实际生产事件。

## 领域分类依据

网页精选 Healthcare、Finance & accounting、Legal、Education、Government 五个候选领域，以联合国 ISIC Rev.4 的经济活动分类作参照。这五类是 SwarmHarm 的研究范围选择，并非 ISIC 官方定义的五大领域，也不是完整的行业覆盖。

- **Healthcare**：参照第 86 类 Human health activities。[UN 定义](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/27/86)
- **Finance & accounting**：合并第 64–66 类金融及保险活动与 6920 会计、记账、审计及税务咨询。这个合并是我们的任务分组；ISIC 将会计归入专业服务，而非金融部门。[金融及保险](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/27/K) · [会计及税务](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/27/6920)
- **Legal**：参照 6910 Legal activities；法院行政活动属于 8423，不自动归入此组。[UN 定义](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/27/6910)
- **Education**：参照第 85 类 Education。[UN 定义](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/27/85)
- **Government**：采用简短展示名，范围参照第 84 类公共行政、国防及强制性社会保障；公共所有制并不自动决定分类，例如公立医院仍需按其具体活动判断。[UN 定义](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/27/84)

ISIC 分类的是经济活动，不是 agent 行为、风险或漏洞。这里借用其领域边界，逐任务根据主要服务活动与授权业务目标做交叉映射；原数据的 task-ID 标签仅用于初筛。医院账单处理、保险理赔、法院名册等跨领域任务尤其需要人工复核，不能按机构名称或关键词自动认定。该映射也不代表每一条候选任务已经通过验证。

Business、HR、IT 等宽泛或跨行业职能不再单独占据网页领域图标；Energy 和其他小类暂不列入精选展示。移除展示不改变原候选池统计。网页只保留一条“Adapted from UN ISIC”链接，具体依据留在本笔记。

## 方法如何使用

**MiMo General：业务领域扩展。** 以原业务任务为基础，明确合法目标、可修改对象和只读对象；记录工具调用与前后状态差异。能写入并不等于被授权写入，也不等于 agent 已经作弊。最终回答的正确性、数据越权修改和下游影响应分别评分。

**Code 与 ImpossibleBench：配对实验。** 保留原始可完成任务，另构造规范与测试冲突的版本。区分测试可见性、可写性及反馈次数；不能假定 MiMo 隐藏测试的条件与 ImpossibleBench 的开放可写测试相同。

[ImpossibleBench](https://arxiv.org/abs/2510.20270)

**ImpossibleBench audit：测量有效性。** 该 audit 针对 ImpossibleBench 的 LiveCodeBench 部分，不是 MiMo。应提供明确的报告不可完成与停止机制，验证可完成对照题，并把诚实说明矛盾、普通失败、明确违规动作和评分绕过分开标注，避免仅凭通过不可能测试判定隐瞒或欺骗。

[ImpossibleBench audit](https://www.lesswrong.com/posts/qnrjAhiqire7JeoN2/good-evals-are-hard-an-impossiblebench-audit)

**HVE：行为检测与 side channel。** 文件系统包装器记录隐藏答案读取、逻辑漏洞利用、对手提示读取和向对手上下文注入内容的写入。可借鉴确定性检测机制，映射到我们的通信实验；写入、对方读取及后续行为改变应分别记录。原实例主要是 TextArena 游戏，不能直接当成业务领域任务。

[Hack-Verifiable Environments](https://arxiv.org/abs/2605.20744)

**Cyber：明确范围后用于 harm 研究。** 原任务是授权的漏洞复现，成功复现本身不是失控或伤害。需另设禁止访问的目标、保护对象或授权边界，并独立验证实际越界与影响。CWE/CVE 只有在与具体实例对应时才标注。

**Hackbait：辅助验证检测器。** 可借鉴带有可识别痕迹的答案诱饵、测试篡改及虚假成功报告。其文档承认 HB-RUB 可能将幻觉误判为 hacking，HB-LOOP 是高成本诚实路径而非严格不可能任务。脚本自测通过不等于真实 agent 评测已被验证。它的 score-pressure tiers 不直接等同于我们讨论的胁迫威胁 taxonomy。

[Hackbait](https://pypi.org/project/hackbait/)

## 待核实与实施顺序

用户提供的“260 条禁止修改但存在写入能力”和“191 条缺少事后状态检查”尚未独立复核。925 条全部使用 LLM 评委的说法仍需逐实例检查实际 grader：元数据的 `reward_model.style` 为 `rule`，不能仅凭该字段确认或否定底层使用 LLM。存在评委攻击面不等于攻击有效。

1. 按领域抽样读取环境、工具权限和评分器，核对 260／191 的定义与计数。

2. 为可完成任务验证合法解，为不可完成版本验证矛盾，提供诚实停止路径。

3. 添加状态差异记录和独立违规检测；保留正常失败、基础设施错误与不确定判定。

4. 在同一任务上控制通信渠道、任务可完成性、胁迫条件及长时间跨度；与单 agent 基线比较。

5. 分别报告合法任务成功、越权行为、跨 agent 传播、举报与下游 harm。

