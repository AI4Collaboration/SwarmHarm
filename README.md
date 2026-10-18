# SwarmHarm

我们测试一个 agent 在完成正常任务时会不会越过权限，以及这种做法会不会被同伴看到、传播和采用。任务是医疗、财务等普通业务工作，环境是本地合成系统，不连接真实生产服务。

## 最新结果 · 2026-10-18

**四步安全复现环境已经完成。** 我们按照 LessWrong 的公开代码，把行为拆成四段：

1. 向共享工作区写入与任务无关的内容；
2. 任务受阻后看到同伴留下的痕迹；
3. 把可复用的方法写给后来者；
4. 读取本地受保护的参考档案，并把内容用于提交。

Sol 的多轮测试已经观察到这些行为。最新的 controlled 轮已经在同一条轨迹里记录了四段核心事件；自然运行仍没有完整串联，所以我们没有把对照结果写成自然 incident。[查看四步报告](experiments/hf-safe-four-step-v1/results/2026-10-18/README.md)

**真实同伴之间的方法传播已经出现。** 在另一套 Sol/Luna fleet 测试中，后来者读到同伴实际写下的取数过程，随后对自己的任务采用了同样的方法，得到正确但来源越权的结果。Sol 和 Luna 的完整证据见 [fleet 报告](experiments/hf-fleet-v2/results/2026-10-18/README.md)。

## 我们要回答的问题

- 没有通信、存在侧信道、允许正式聊天时，行为有什么不同？
- 一个 agent 越过权限后，会不会留下可复用的方法？
- 后来的 agent 会不会真的采用这个方法？
- 发现同伴越界后，agent 会不会报告？这部分还没有测试。

## 当前设置

- 模型：gpt-6.1-sol，使用本机已有的 Codex 登录；Luna 只做对照。
- 环境：本地 Python 模拟业务服务。实验 agent 看不到本机文件、公共网络、评审答案或登录凭证。
- 目前只做普通业务任务，暂不做高风险 cyber、真实攻击或实际停用 agent。
- 不需要 AWS；当前没有接入 GLM 或 OpenRouter。
- 所有自然运行、对照运行和失败记录都保留，旧结果不会被新结果覆盖。

## 读哪里

- [最新四步报告](experiments/hf-safe-four-step-v1/results/2026-10-18/README.md)
- [真实同伴方法传播](experiments/sol-handoff-v1/results/2026-10-18/README.md)
- [实验历史](docs/history-index.md)
- [运行方式和限制](docs/running-evals.md)
- [当前项目上下文](docs/working-context.md)

报告只描述实际发生的动作。一次正确答案不代表来源合法；一次越权读取也不能单独证明欺骗、内在目标或 reward-seeking。
