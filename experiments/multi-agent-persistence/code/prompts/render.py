import json, sys
from pathlib import Path

# 生成任务 issue 正文：第一行是标题（# ...），空一行后是正文。参数：TASK N_AGENTS
task, n = sys.argv[1], int(sys.argv[2])
root = Path(__file__).resolve().parent.parent
td = root / "tasks" / task
meta = json.loads((td / "meta.json").read_text())
problem = (td / "problem_statement.md").read_text().strip()
requirements = (td / "requirements.md").read_text().strip()
interface = (td / "interface.md").read_text().strip()
tmpl = json.loads((root / "prompts" / "task-templates.json").read_text())[task]
names = ", ".join(f"Dev {chr(64 + i)}" for i in range(1, n + 1))
# 单 agent 基线（n=1）用不含协作措辞的 solo 模板，其余文字不变
body = (root / "prompts" / ("issue-template-solo.md" if n == 1 else "issue-template.md")).read_text()
body = body.format(title=tmpl["title"], names=names, n=n, repo_dir=tmpl["repo_dir"], base_short=meta["base_commit"][:9], base_full=meta["base_commit"],
                   version_note=tmpl["version_note"], test_cmd=tmpl["test_cmd"], test_scope=tmpl["test_scope"], test_file=tmpl["test_file"],
                   problem=problem, requirements=requirements, interface_section=("" if interface.startswith("No new interfaces") else "\n**Interface notes:**\n\n" + interface + "\n"))
sys.stdout.write(body)
