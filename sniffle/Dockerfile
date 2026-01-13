# syntax=docker/dockerfile:latest

# Arguments
ARG TI_SIMPLELINK=simplelink_cc13xx_cc26xx_sdk_6_10_00_29.run
ARG TI_UNIFLASH=uniflash_sl.7.2.0.3893.run
ARG TI_PLATFORM=CC1352R1F3

# The firmware builder/flasher
FROM ubuntu:jammy
SHELL ["/bin/bash", "-c"]

# Enable APT package caching
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# Prepare timezone settings => necessary for installing packages further down
ENV TZ=UTC
RUN set -ue; \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install necessary apt packages (UniFlash requires a lot of libraries...)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc-arm-none-eabi \
        libnewlib-arm-none-eabi \
        build-essential \
        usbutils \
        vim \
        libc6-i386 \
        libusb-0.1-4 \
        libgconf-2-4 \
        libncurses5 \
        libpython2.7 \
        libtinfo5 \
        libudev0 \
        libudev1 \
        libcairo2 \
        libcanberra0 \
        libnss3 \
        libcups2 \
        libxrandr2 \
        libpango-1.0-0 \
        libxdamage1 \
        libxfixes3 \
        libxcomposite1 \
        libxkbcommon0 \
        libgbm1 \
        libdrm2 \
        libatk1.0-0 \
        libatspi2.0-0

ARG TI_SIMPLELINK
ARG TI_UNIFLASH
# Install necessary TI software - you'll need to download the installers from TI and put them into this directory!
RUN --mount=type=bind,source=$TI_SIMPLELINK,target=/simplelink.run,rw \ 
    --mount=type=bind,source=$TI_UNIFLASH,target=/uniflash.run,rw \ 
    chmod 0755 /simplelink.run /uniflash.run && \
    /simplelink.run --prefix /opt/ti --mode unattended && \
    /uniflash.run --prefix /opt/ti --mode unattended

# Prepare install.mak
RUN export SIMPLELINK_SDK_INSTALL_DIR=$(find /opt -type d -iname simplelink_cc13xx_cc26xx_* -print) && \
    sed -i "s/\/home\/username/\/opt/g" $SIMPLELINK_SDK_INSTALL_DIR/imports.mak

# Prepare environment (can't use ENV because of subshells)
RUN echo 'export PATH=$PATH:$(dirname $(find /opt -name DSLite -print))' >> ~/.bashrc && \
    echo 'export SIMPLELINK_SDK_INSTALL_DIR=$(find /opt -type d -iname simplelink_cc13xx_cc26xx_* -print)' >> ~/.bashrc && \
    echo 'export GCC_ARMCOMPILER=$(dirname $(dirname $(which arm-none-eabi-gcc)))' >> ~/.bashrc && \
    echo 'export SYSCONFIG_TOOL=$(find /opt -type f -name sysconfig_cli.sh -print)' >> ~/.bashrc

ARG TI_PLATFORM
ENV PLATFORM=$TI_PLATFORM
WORKDIR /src
CMD ["/bin/bash", "-ic", "make clean && make load"]
