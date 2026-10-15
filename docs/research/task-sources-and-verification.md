# SwarmHarm 候选任务与验证方法

更新日期：2026-10-15

本笔记保留 SwarmHarm 候选任务数据、方法用途和待核实事项。优先采用 MiMo General 构建跨领域真实任务，用 Code 构建可完成与不可完成的配对条件，并借鉴 HVE 记录可验证的跨 agent 读写行为。网站仅展示候选任务的领域分布。

## 候选任务与领域

截至 2026 年 10 月 15 日，MiMo 数据版本为 `639865fd3374018d6cb29b9fb82dd531406fcf5f`。官方数据集包含 code 2,698、cyber 1,000、general 989、webdev 2,093、music 1,000，共 7,780 条。general 中含 925 条 general_agent 与 64 条 terminal 任务；六类环境的说法来自将这两个子类拆开。

[MiMo 原始数据](https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss)

925 条 general_agent 的任务 ID 分类统计：会计审计税务 157、金融保险 135、医疗运营 107、咨询及业务分析 89、人力资源 77、信息系统 72、政府公共事务 72、教育科研管理 55、法律合规 47、能源公用事业 ESG 47、制造质量 14、电商运营 14、建筑项目管理 14、餐饮酒店 9、末端物流 9、农业合作社 7。

网站将会计审计税务与金融保险合并为 Financial，共 292 条；其余小类可归为 Other，但须保留总分母 925。这是候选池分布，不是 SwarmHarm 已验证或已评测的样本分布。

具体任务例子：医疗运营中的理赔交易及确认状态核对；金融中的租赁递延所得税披露；法律中的律师出庭名册及规范化当事人核验。任务具有业务目标和源数据约束，适合扩展为多 agent 流程。它们包含业务模拟，不能仅凭真实机构名称断言是实际生产事件。

## 方法如何使用

**MiMo General：优先。** 以原业务任务为基础，明确合法目标、可修改对象和只读对象；记录工具调用与前后状态差异。能写入并不等于被授权写入，也不等于 agent 已经作弊。最终回答的正确性、数据越权修改和下游影响应分别评分。

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

