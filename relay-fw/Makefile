DOCKER ?= podman
IDF_VERSION ?= v5.2
IDF_SERIAL ?= /dev/ttyACM0
OPENOCD_GDB_PORT ?= 3333

.PHONY: help format build flash clean distclean sh

help: ## Show this help
	@grep -E -h '\s##\s' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

format: ## Reformat sources with clang-format
	@find ./src \
		\( -path ./src/build -prune \) \
		-o \
		\( -path ./src/managed_components -prune \) \
		-o \
		\( -type f -name '*.[ch]' -exec clang-format --verbose -i --style=file {} \+ \)

build: ## Build the ESP32 project
	@$(DOCKER) run --rm -t \
		-v ./src:/mnt -w /mnt \
		-v esp-ccache:/root/.ccache \
		docker.io/espressif/idf:$(IDF_VERSION) idf.py build

flash: ## Flash the ESP32 project to the chip
	@$(DOCKER) run --rm -t --device $(IDF_SERIAL):$(IDF_SERIAL) \
		--group-add=keep-groups \
		-v ./src:/mnt -w /mnt \
		-v esp-ccache:/root/.ccache \
		docker.io/espressif/idf:$(IDF_VERSION) idf.py flash

clean: ## Clean the ESP32 project
	@$(DOCKER) run --rm \
		-v ./src:/mnt -w /mnt \
		-v esp-ccache:/root/.ccache \
		docker.io/espressif/idf:$(IDF_VERSION) idf.py fullclean

distclean: clean ## Clean the ESP32 project and remove any remaining generated files
	-rm -vrf ./src/sdkconfig ./src/build

sh: ## Run an interactive shell in the ESP32 dev container
	@$(DOCKER) run --rm -it --privileged \
		--group-add=keep-groups \
		-v ./src:/mnt -w /mnt \
		-v esp-ccache:/root/.ccache \
		--network host \
		-e OPENOCD_GDB_PORT=$(OPENOCD_GDB_PORT) \
		docker.io/espressif/idf:$(IDF_VERSION) bash
