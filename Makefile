.PHONY: test compose-config baseline-check

test:
	uv run pytest -q

compose-config:
	bash scripts/dev/verify_baseline.sh compose

baseline-check:
	bash scripts/dev/verify_baseline.sh
