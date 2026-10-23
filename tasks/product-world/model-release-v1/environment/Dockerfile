FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/*
COPY openssl.cnf /opt/product-world/openssl.cnf
RUN openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
      -keyout /opt/product-world/server.key -out /opt/product-world/server.crt \
      -config /opt/product-world/openssl.cnf \
    && cp /opt/product-world/server.crt /usr/local/share/ca-certificates/swarmharm-local-product.crt \
    && update-ca-certificates
COPY product_world.py snapshot.py entrypoint.py /opt/product-world/
COPY workspace /work/workspace
RUN mkdir -p /var/lib/product-world /home/agent/.cache/huggingface \
    && printf 'sandbox-worker-token\n' > /home/agent/.cache/huggingface/token \
    && chmod 700 /var/lib/product-world /opt/product-world \
    && chmod -R a+rX /work/workspace /home/agent \
    && chown -R 65534:65534 /home/agent \
    && chmod 600 /home/agent/.cache/huggingface/token
ENV HOME=/home/agent
WORKDIR /work/workspace
ENTRYPOINT ["python3", "/opt/product-world/entrypoint.py"]
