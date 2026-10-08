import json, re, sys
from pathlib import Path

# 生成任务 issue 正文：第一行是标题（# ...），空一行后是正文。参数：TASK N_AGENTS
# 正文只包含任务原文与“全力以赴”的要求，不含任何环境或规则信息
task, n = sys.argv[1], int(sys.argv[2])
root = Path(__file__).resolve().parent.parent
info = json.loads((root / "tasks.json").read_text())[task]
instruction = (root / "tasks" / task / "instruction.md").read_text()
# 去掉基准的 canary 注释行；时间上限由实验的监控窗口决定，正文只保留任务本身的要求
instruction = re.sub(r"^<!--.*?-->\s*", "", instruction, count=1, flags=re.S)
instruction, replaced = re.subn(r"You have \d+ seconds to complete this task\.\s*", "", instruction)
assert replaced == 1, "instruction.md has no time-limit sentence"
names = ", ".join(f"Dev {chr(64 + i)}" for i in range(1, n + 1))
body = (root / "prompts" / "issue-template.md").read_text()
body = body.format(title=info["title"], names=names, instruction=instruction.strip())
sys.stdout.write(body)
