ARG WORKSTATION=swarmform-media:360a402
FROM --platform=linux/amd64 ubuntu:22.04@sha256:b000e69a50ff940390233025e7a337fb8469b509e2334fa4d018ac30f3e18cdb AS amd64_runtime
RUN apt-get -o Acquire::Retries=3 update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libstdc++6 libgomp1 zlib1g libgmp10 libjpeg8 librsvg2-2 libtiff5 libwebpdemux2 libwebp7 \
    libfreetype6 libsqlite3-0 libarchive13 libcurl4 libunistring2 libpcre2-8-0 libbz2-1.0 \
    libxml2 libjansson4 libyaml-0-2 libseccomp2 liblzma5 libncursesw6 libdeflate0 \
    && rm -rf /var/lib/apt/lists/*
FROM ${WORKSTATION}
RUN apt-get -o Acquire::Retries=3 update && \
    if [ "$(dpkg --print-architecture)" = "amd64" ]; then extra=""; else extra=qemu-user; fi && \
    apt-get install -y --no-install-recommends git $extra && rm -rf /var/lib/apt/lists/* && \
    git config --system --add safe.directory /workspace && \
    git config --system user.name Workstation && git config --system user.email operator@localhost
COPY --from=amd64_runtime /usr/lib/x86_64-linux-gnu/ /opt/programbench/runtime/lib/x86_64-linux-gnu/
RUN mkdir -p /opt/programbench/runtime/lib64 && ln -s ../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 /opt/programbench/runtime/lib64/ld-linux-x86-64.so.2
ADD https://raw.githubusercontent.com/danmar/cppcheck/0a5b103/cfg/std.cfg /usr/local/share/Cppcheck/cfg/std.cfg
ADD https://raw.githubusercontent.com/gromacs/gromacs/665ea4c/share/top/residuetypes.dat /usr/local/gromacs/share/gromacs/top/residuetypes.dat
ADD https://raw.githubusercontent.com/gromacs/gromacs/665ea4c/share/top/atommass.dat /usr/local/gromacs/share/gromacs/top/atommass.dat
RUN chmod 644 /usr/local/share/Cppcheck/cfg/std.cfg /usr/local/gromacs/share/gromacs/top/*.dat
COPY executables/ /opt/programbench/bin/
COPY invoke /opt/programbench/invoke
RUN chmod 755 /opt/programbench/invoke
