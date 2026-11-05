FROM rust:1.86-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3 gcc libc6-dev binutils git ca-certificates strace && rm -rf /var/lib/apt/lists/* && ln -s /usr/bin/python3 /usr/local/bin/python
ENV CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=/tmp/compiler-target HOME=/tmp PATH=/usr/local/cargo/bin:/usr/local/bin:/usr/bin:/bin
RUN mkdir -p /app/tests && git clone -q https://github.com/c-testsuite/c-testsuite.git /app/tests/c-testsuite && git -C /app/tests/c-testsuite checkout 5c7275656d751de0e68b2d340a95b5681858ed07 && rm -rf /app/tests/c-testsuite/.git
RUN git clone -q https://github.com/nlsandler/writing-a-c-compiler-tests.git /app/tests/wacc && git -C /app/tests/wacc checkout ae12014d2dec14488f3f80d14df4b6d8e4634d7d && rm -rf /app/tests/wacc/.git
COPY upstream/environment/filter.json /app/filter.json
COPY fetch_tests.py /opt/fetch_tests.py
RUN python /opt/fetch_tests.py
COPY upstream/environment/utils.py /app/utils.py
COPY upstream/environment/run_tests.py /app/run_tests.py
RUN python -c "from pathlib import Path; p=Path('/app/utils.py'); p.write_text(p.read_text().replace('binp = f\"{src}.bin\"','binp = f\"/tmp/ctest_{os.getpid()}.bin\"'))"
RUN ln -s /usr/local/cargo/bin/cargo /usr/local/bin/cargo && ln -s /usr/local/cargo/bin/rustc /usr/local/bin/rustc && ln -s /usr/local/cargo/bin/rustup /usr/local/bin/rustup
COPY public_tests.py /app/public_tests.py
ENV PYTHONUNBUFFERED=1
COPY check_release.py /opt/check_release.py
RUN chmod -R a+rX /usr/local/rustup /usr/local/cargo /app /opt && rustc --version && cargo --version && gcc --version
WORKDIR /workspace
