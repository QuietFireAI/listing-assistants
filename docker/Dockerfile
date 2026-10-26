# ListingAssistants, agent isolation V1 (owner decision 2026-10-26).
# One image; docker/compose.yml runs it as the dispatcher, the two doors and
# twenty agents, each in its own container. See docs/CONTAINERS.md.
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd -g 10001 la && useradd -u 10001 -g la -M -d /nonexistent -s /usr/sbin/nologin la
WORKDIR /app
COPY requirements.txt /app/requirements.txt
# an office behind a proxy with its own certificate can pass it at build
# time only (docker build --secret id=ca,src=<file>); nothing is kept
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir -r /app/requirements.txt
COPY docker/requirements-signer.txt /app/docker/requirements-signer.txt
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir -r /app/docker/requirements-signer.txt
COPY . /app
# the mount points, owned by the one unprivileged user every container runs as
RUN mkdir -p /state /line /door /door-config /signer /out /signer-out /reviews \
    && for i in $(seq -w 1 20); do mkdir -p /portal/$i; done \
    && chown -R 10001:10001 /state /line /door /door-config /signer /out /signer-out /reviews /portal \
    && chmod -R 700 /state /line /door /door-config /signer /reviews /portal \
    && chmod 755 /out /signer-out
USER 10001:10001
