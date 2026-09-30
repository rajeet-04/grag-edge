.PHONY: test compose-config baseline-check demo-reset demo-start demo-offline demo-online demo-status

test:
	uv run pytest -q

compose-config:
	bash scripts/dev/verify_baseline.sh compose

baseline-check:
	bash scripts/dev/verify_baseline.sh

demo-reset:
	bash scripts/demo/reset.sh

demo-start:
	bash scripts/demo/start.sh

demo-offline:
	bash scripts/demo/offline.sh

demo-online:
	bash scripts/demo/online.sh

demo-status:
	bash scripts/demo/status.sh
