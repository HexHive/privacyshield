# call make with `make DOCKER=podman <target>` to use podman instead of docker
DOCKER ?= sudo docker
SERVER_PORT ?= 8000

.PHONY: all setup run-server

all: setup airguard.apk findmy-0.7.6-py3-none-any.whl relay-fw.bin

setup:
	@echo "Making sure all upstream repos are present"
	@git submodule update --init --recursive || ( \
		git clone --branch=2.4.0 https://github.com/seemoo-lab/airguard.git airguard/airguard-upstream && \
		git clone --branch=v0.7.6 https://github.com/malmeloo/FindMy.py.git findmy/findmypy-upstream \
		) || true

airguard.apk findmy-0.7.6-py3-none-any.whl relay-fw.bin: setup
	@$(DOCKER) build --target exporter --tag privacyshield-exporter:latest .
	@$(DOCKER) run --rm -v $(PWD):/mnt privacyshield-exporter

run-server:
	@$(DOCKER) build --target server --tag privacyshield-server:latest .
	@mkdir -p data
	@$(DOCKER) run --rm -p $(SERVER_PORT):8000 -v ./data:/data:rw privacyshield-server
