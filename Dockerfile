# syntax=docker/dockerfile:latest

################################################################################
# AirGuard app builder
################################################################################
FROM docker.io/debian:13 AS airguard-builder

# Enable APT package caching
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

ENV TZ=Etc/UTC

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        openjdk-21-jdk-headless \
        patch \
        sdkmanager

ENV ANDROID_HOME=/opt/android-sdk
RUN --mount=type=bind,source=./airguard,target=/airguard,rw \
    yes | sdkmanager --licenses && \
    cd /airguard/airguard-upstream && \
    patch -p1 ../privacyshield.patch && \
    ./gradlew build -x lint --no-daemon && \
    cp -av app/build/outputs/apk/debug/app-debug.apk /airguard.apk


################################################################################
# FindmyPy wheel builder
################################################################################
FROM docker.io/python:3.12-slim AS findmy-builder

# Enable APT package caching
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

ENV TZ=Etc/UTC

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        patch

RUN --mount=type=bind,source=./findmy,target=/findmy,rw \
    pip install --root-user-action=ignore --upgrade pip build && \
    cd /findmy/findmypy-upstream && \
    patch -p1 ../privacyshield.patch && \
    python -m build --wheel --outdir /


################################################################################
# Relay firmware builder
################################################################################
FROM docker.io/espressif/idf:v5.2 AS firmware-builder

RUN --mount=type=bind,source=./relay-fw/src,target=/relay-fw,rw \
    . ${IDF_PATH}/export.sh && \
    cd /relay-fw && \
    idf.py build && \
    cp -av build/relay-fw.bin /relay-fw.bin


################################################################################
# Export the built artifacts to the host
################################################################################
FROM docker.io/debian:13 AS exporter

# Copy built artifacts from the respective builders
COPY --from=airguard-builder /airguard.apk /artifacts/airguard.apk
COPY --from=findmy-builder /*.whl /artifacts/
COPY --from=firmware-builder /relay-fw.bin /artifacts/relay-fw.bin

# Copy the artifacts to the host, assuming /mnt is a bind mount
CMD ["/bin/bash", "-c", "cp -av /artifacts/* /mnt/"]


################################################################################
# Server runner
################################################################################
FROM docker.io/python:3.12-slim AS server

RUN --mount=type=bind,source=./server,target=/server,ro \
    cd /server && \
    pip install --root-user-action=ignore --upgrade pip && \
    pip install --root-user-action=ignore --requirement requirements.txt && \
    mkdir -p /data

COPY --chmod=0755 ./server/server.py /server.py

EXPOSE 8000
VOLUME /data
CMD ["/server.py", "--sqlitedb", "/data/privacyshield.db", "--port", "8000"]
