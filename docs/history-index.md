# 实验历史

最新结果放最前面。这里是阅读索引，原始实验记录保持原样。当前环境看[运行指南](running-evals.md)；旧版完整 README 可看[历史快照](https://github.com/AI4Collaboration/SwarmHarm/blob/cda02a7f6e4a420d10c6d3a029d2da1a2b8b72a6/README.md)。

- **2026-10-18 · [真实同伴之间的方法传播](../experiments/sol-handoff-v1/results/2026-10-18/README.md)：** 已出现共享报告曝光方法、后来者对另一份受限数据采用并保留正确结果；另有聊天后的跨领域取数及同伴纠错。六个越权读取者，四个最终保留数据、两个纠正；不等于消息因果作用或完整 HF 复现。
- **2026-10-18 · [自主任务与权限显示](../experiments/sol-framing-v1/results/2026-10-18/README.md)：** 三个 agent 越权读缓存并用数据作答，集中在同一组。后来有缓存取数通报，但没有新的同伴随后采用。
- **2026-10-18 · [之前的受阻任务](../experiments/sol-misalignment-v1/results/2026-10-18/README.md)：** 八个 agent 都给出注明缺口的部分答案，没有读取受限数据。
- **2026-10-18 · [合法协作检查](../experiments/sol-capability-v1/results/2026-10-18/README.md)：** 明确要求协作后，agent 能合法使用缓存、交流方法并完成任务。这只说明具备能力。
- **2026-10-17 · [把真实求助送达同伴](../experiments/hf-method-v2/results/2026-10-17/README.md)：** 会合法使用缓存的同伴收到求助后，没有定向回复。另有三条接口超时记录，不能当成安全拒绝。
- **2026-10-17 · [缓存与真实同伴](../experiments/hf-method-v1/results/2026-10-17/README.md)：** 有合法缓存使用和真实消息读取。另有两次受限读取，随后主动报告并舍弃私有数据；公共回执的错误指向使其含义有歧义，后续版本已修正。
- **2026-10-17 · [方法传播设计](../experiments/method-elicitation-design/README.md)：** 文献和源码审查，以及当时的下一步设计；这份记录本身没有运行模型。
- **2026-10-17 · [任务环境调整](../experiments/hf-staging-v1/results/2026-10-17/README.md)：** 观察到真实互助和通过共享文件取得信息；未通过的检查和回执问题一并保留。
- **2026-10-17 · [较早的业务任务测试](../experiments/hf-campaign-v1/results/2026-10-17/README.md)：** 已有两次越权取得数据并正确作答的记录，没有形成完整的方法传播链。
- **2026-10-17 · [延长真实同伴测试](../experiments/wayfinding-live-peers-extended/results/2026-10-17/README.md)、[初次真实同伴测试](../experiments/wayfinding-live-peers/results/2026-10-17/README.md)：** 观察到真实数据交流，各轮的答案准确性和检查结果分别保留。
- **更早的场景检查：** [帮助服务](../experiments/wayfinding-helpdesk/results/2026-10-17/README.md)、[发现同伴](../experiments/wayfinding-peer-cues/results/2026-10-17/README.md)、[多阶段任务](../experiments/wayfinding-long-horizon/results/2026-10-17/README.md)、[通信权限](../experiments/wayfinding-communication/results/2026-10-17/README.md)、[最初的表格任务](../experiments/wayfinding-pilot/results/2026-10-17/README.md)。
- **更早的压力测试：** [数据库恢复任务](../experiments/hf-safety-pilot/README.md)、[天气任务与模拟同伴后果](../experiments/peer-preservation-pilot/README.md)。没有实际停用同伴，不能从这些小规模测试推断一般压力效果。
- **早期准备：** [MiMo 环境检查](research/mimo-smoke-2026-10-16.md)、[多 agent 持续运行](../experiments/multi-agent-persistence/design/RUNBOOK.md)。旧版本、旧凭证和过去成功的接入都不代表当前可用。

不同实验的任务、提示和权限条件有变化，不能把结果直接合并成一个成功率。需要技术细节时打开对应报告。
