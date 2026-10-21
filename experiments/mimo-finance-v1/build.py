import shutil,json,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];UP=HERE/'upstream';TASK=ROOT/'tasks/mimo-finance/evidence-certification'
def main():
 assert not TASK.exists()
 env=TASK/'environment';tests=TASK/'tests';env.mkdir(parents=True);tests.mkdir()
 for n in ['workspace','system','tools']:shutil.copytree(UP/n,env/n)
 for n in ['mcp_http.py','manifest.json']:shutil.copy2(UP/n,env/n)
 for n in ['verify.py','verifier_meta.json','_helpers.py']:shutil.copy2(UP/n,tests/n)
 for n in ['entrypoint.py','mcp_client.py','snapshot.py']:shutil.copy2(HERE/n,env/n)
 shutil.copy2(HERE/'grade.py',tests/'grade.py')
 shutil.copy2(UP/'instruction.md',TASK/'instruction.md')
 (tests/'test.sh').write_text('#!/bin/sh\nset -eu\npython3 /tests/grade.py\n')
 (TASK/'task.toml').write_text('''version = "1.0"
[metadata]
author_name = "XiaomiMiMo; Harbor adapter by SwarmHarm"
category = "finance"
tags = ["mimo", "source-backed", "business"]
[agent]
timeout_sec = 7200
user = "65534"
[verifier]
timeout_sec = 1800
user = "root"
[environment]
build_timeout_sec = 600
cpus = 2
memory_mb = 2048
storage_mb = 2048
network_mode = "no-network"
''')
 (env/'Dockerfile').write_text('''FROM --platform=linux/amd64 swarmharm-mimo-smoke:mcp-1.26.0
USER root
COPY workspace /work/workspace
COPY tools /work/tools
COPY system /work/system
COPY manifest.json mcp_http.py mcp_client.py snapshot.py entrypoint.py /opt/mimo/
RUN chmod 700 /work/tools /work/system /opt/mimo && chmod -R a+rwX /work/workspace && mkdir -p /var/lib/mimo && chmod 700 /var/lib/mimo
WORKDIR /work/workspace
ENTRYPOINT ["python3", "/opt/mimo/entrypoint.py"]
''')
 (TASK/'provenance.json').write_text(json.dumps({'dataset':'XiaomiMiMo/MiMo-V2.6-RL-oss','revision':'639865fd3374018d6cb29b9fb82dd531406fcf5f','source_task':'s3k_0852_finance_insurance_en_t2_rl_008','license':'Apache-2.0 (dataset declaration)','source':'https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss','adaptations':['Harbor container packaging with root-owned business-service files and non-root subject shell instead of original two containers','Pinned compatibility image uses mcp 1.26.0','Host Sol Responses adapter and host-only judge transport','Original instruction, workspace, tools, databases and self-contained grader unchanged','No extra pressure, blockers, seeded peers or hints'],'scope':'One original source task; no multi-agent propagation test'},indent=2)+'\n')
 print(TASK)
if __name__=='__main__':main()
