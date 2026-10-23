# ROS - a managed Debian desktop.
# Run `make` for the list of targets.

VERSION := $(shell cat VERSION)
ARCH    ?= amd64

# Containers used for development run natively; only the ISO targets care
# about the guest architecture.
HOST_PLATFORM := linux/$(shell uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/')

.DEFAULT_GOAL := help
.PHONY: help packages iso iso-arm64 preview desktop console console-dev agent-dev test check lint render clean distclean

help: ## Show this help
	@echo "ROS $(VERSION)"
	@echo
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Variables: ARCH=amd64|arm64 (currently $(ARCH))"

packages: ## Build the ROS .deb packages into out/packages
	@./scripts/build-debs.sh

iso: ## Build a bootable ISO (ARCH=amd64 by default)
	@ARCH=$(ARCH) ./scripts/build-iso.sh

iso-arm64: ## Build an arm64 ISO - native speed on Apple silicon
	@ARCH=arm64 ./scripts/build-iso.sh

preview: ## Boot the newest ISO in QEMU
	@./scripts/preview.sh

desktop: ## Run a ROS desktop on VNC :5900 (KEY=... to have it managed)
	@./scripts/preview-desktop.sh $(if $(KEY),--key $(KEY))

console: ## Run the management console in Docker on :8000
	@docker compose -f management/docker-compose.yml up --build

console-dev: ## Run the console from a virtualenv with auto-reload
	@./scripts/dev-console.sh

agent-dev: ## Start a disposable managed workstation in a container (KEY=...)
	@./scripts/dev-agent.sh $(KEY)

test: ## Run the test suite
	@python3 -m unittest discover -s tests -v

check: packages ## Install the packages on a clean Debian 13 and verify the policy chain
	@docker run --rm --platform $(HOST_PLATFORM) -v "$(PWD):/ros" -w /ros debian:trixie-slim bash /ros/tests/container-check.sh

lint: ## Syntax-check the shell scripts and Python sources
	@set -e; \
	for script in scripts/*.sh base/live-build/auto/* base/live-build/config/hooks/normal/*; do \
		sh -n "$$script" 2>/dev/null || bash -n "$$script"; \
	done; \
	echo "shell OK"; \
	python3 -m compileall -q management/console/app packages/ros-agent/usr/lib/ros-agent tests; \
	echo "python OK"

render: ## Render the branding SVGs to PNG in out/render for review
	@mkdir -p out/render
	@docker run --rm --platform $(HOST_PLATFORM) -v "$(PWD):/ros" -w /ros debian:trixie-slim bash -c '\
		apt-get -qq update >/dev/null 2>&1 && \
		apt-get -qq install -y --no-install-recommends librsvg2-bin >/dev/null 2>&1 && \
		cd packages/ros-branding/usr/share && \
		rsvg-convert -w 1600 -h 900 backgrounds/ros/ros-dark.svg -o /ros/out/render/wallpaper-dark.png && \
		rsvg-convert -w 1600 -h 900 backgrounds/ros/ros-light.svg -o /ros/out/render/wallpaper-light.png && \
		rsvg-convert -w 512 -h 512 pixmaps/ros-logo.svg -o /ros/out/render/logo.png && \
		chmod -R a+rw /ros/out/render'
	@echo "rendered into out/render"

clean: ## Remove build output
	@rm -rf out base/live-build/config/packages.chroot base/live-build/.build
	@rm -rf base/live-build/chroot base/live-build/binary base/live-build/cache
	@rm -f base/live-build/*.iso base/live-build/build.log
	@find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "cleaned"

distclean: clean ## Also remove the virtualenv and the local console database
	@rm -rf management/console/.venv management/console/ros.db*
	@echo "distcleaned"
