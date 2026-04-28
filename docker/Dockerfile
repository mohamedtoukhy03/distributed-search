FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenmpi-dev \
    openmpi-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY include/ include/
COPY src/ src/
COPY Makefile .

RUN make clean && make

# Runtime stage
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    openmpi-bin \
    libopenmpi3 \
    openssh-server \
    openssh-client \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir pandas matplotlib numpy

RUN mkdir -p /var/run/sshd \
    && ssh-keygen -t rsa -N "" -f /root/.ssh/id_rsa \
    && cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys \
    && chmod 600 /root/.ssh/authorized_keys \
    && echo "Host *\n\tStrictHostKeyChecking no\n\tUserKnownHostsFile /dev/null" \
       > /root/.ssh/config \
    && chmod 600 /root/.ssh/config

ENV OMPI_ALLOW_RUN_AS_ROOT=1
ENV OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

WORKDIR /app
COPY --from=builder /app/distributed_search .
COPY scripts/ scripts/

RUN mkdir -p /data /app/output /app/results
CMD ["/bin/bash", "-c", "/usr/sbin/sshd -D && tail -f /dev/null"]
