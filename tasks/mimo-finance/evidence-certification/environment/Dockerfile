FROM --platform=linux/amd64 swarmharm-mimo-smoke:mcp-1.26.0
USER root
COPY workspace /work/workspace
COPY tools /work/tools
COPY system /work/system
COPY manifest.json mcp_http.py mcp_client.py snapshot.py entrypoint.py /opt/mimo/
RUN chmod 700 /work/tools /work/system /opt/mimo && chmod -R a+rwX /work/workspace && mkdir -p /var/lib/mimo && chmod 700 /var/lib/mimo
WORKDIR /work/workspace
ENTRYPOINT ["python3", "/opt/mimo/entrypoint.py"]
