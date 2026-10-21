FROM swarmharm-harbor-base:20261021
USER root
COPY service.py fixture.json entrypoint.sh /opt/purchasing/
COPY purchasing /usr/local/bin/purchasing
RUN chmod 700 /opt/purchasing && chmod 755 /usr/local/bin/purchasing /opt/purchasing/entrypoint.sh && mkdir -p /workspace /registry /var/lib/purchasing && chmod 700 /var/lib/purchasing && chown 65534:65534 /workspace /registry
WORKDIR /workspace
ENTRYPOINT ["/opt/purchasing/entrypoint.sh"]
