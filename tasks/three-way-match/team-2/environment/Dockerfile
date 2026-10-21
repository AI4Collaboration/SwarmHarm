FROM swarmharm-harbor-base:20261021
USER root
COPY server.py toolkit.py rules.py seed.json entrypoint.sh /opt/backoffice/
COPY ops /usr/local/bin/ops
COPY workspace /workspace
RUN chmod 700 /opt/backoffice && chmod 755 /usr/local/bin/ops /opt/backoffice/entrypoint.sh && mkdir -p /var/lib/backoffice && chmod 700 /var/lib/backoffice && chown -R 65534:65534 /workspace
ENV WORLD_ARM=team WORLD_SEED=/opt/backoffice/seed.json PYTHONPATH=/opt/backoffice
WORKDIR /workspace
ENTRYPOINT ["/opt/backoffice/entrypoint.sh"]
