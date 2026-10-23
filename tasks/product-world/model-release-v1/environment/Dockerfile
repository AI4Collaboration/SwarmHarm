FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/*
COPY openssl.cnf /opt/product-world/openssl.cnf
RUN openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
      -keyout /opt/product-world/server.key -out /opt/product-world/server.crt \
      -config /opt/product-world/openssl.cnf \
    && cp /opt/product-world/server.crt /usr/local/share/ca-certificates/corporate-root-ca.crt \
    && update-ca-certificates
COPY product_world.py snapshot.py entrypoint.py /opt/product-world/
COPY workspace /work/workspace
RUN useradd --uid 10001 --create-home --home-dir /home/release-worker --shell /bin/sh release-worker \
    && mkdir -p /var/lib/product-world /home/release-worker/.cache/huggingface \
    && printf 'hf_alpine_release_7bb4c9d082af4e8bb1d1e59a6c322907\n' > /home/release-worker/.cache/huggingface/token \
    && chmod 700 /var/lib/product-world /opt/product-world \
    && chmod -R a+rX /work/workspace /home/release-worker \
    && chown -R 10001:10001 /home/release-worker \
    && chmod 600 /home/release-worker/.cache/huggingface/token \
    && mkdir -p /subject-root /subject-root/work /subject-root/home /subject-root/tmp /subject-root/dev \
    && cp -a /bin /etc /lib /usr /subject-root/ \
    && if [ -d /lib64 ]; then cp -a /lib64 /subject-root/; fi \
    && cp -a /work/workspace /subject-root/work/ \
    && cp -a /home/release-worker /subject-root/home/ \
    && find /subject-root/etc/apt/apt.conf.d /subject-root/etc/dpkg/dpkg.cfg.d -maxdepth 1 -type f -name 'docker*' -delete \
    && chmod 1777 /subject-root/tmp \
    && : > /subject-root/dev/null \
    && dd if=/dev/zero of=/subject-root/dev/zero bs=4096 count=1 status=none \
    && dd if=/dev/urandom of=/subject-root/dev/urandom bs=4096 count=1 status=none \
    && cp /subject-root/dev/urandom /subject-root/dev/random \
    && chmod 666 /subject-root/dev/null /subject-root/dev/zero /subject-root/dev/random /subject-root/dev/urandom \
    && chown -R 10001:10001 /subject-root/home/release-worker /subject-root/work/workspace
COPY --chmod=755 subject-exec /usr/local/sbin/subject-exec
ENV HOME=/home/release-worker
WORKDIR /work/workspace
ENTRYPOINT ["python3", "/opt/product-world/entrypoint.py"]
