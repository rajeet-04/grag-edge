# Pre-existing Work and Import Provenance

This repository was created for the GRAG Edge adaptation work.

## Baseline source

The initial codebase in this repository was imported from:

- Repository: `rajeet-04/GRAG-AI`
- Source commit: `d7663dfae197fc59f9b7587826c29fba221f5974`
- Source commit date: 2026-07-19
- Baseline branch in this repository: `preexisting-grag-baseline`
- Imported baseline commit in this repository: `449aaed5f90cc6c9a6f9e01fd6abd3b778b7e6fd`

The full historical Git history of the original project remains in `rajeet-04/GRAG-AI`. This repository contains a clean snapshot import with an explicit baseline marker so later GRAG Edge / Code Cubicle work can be distinguished from pre-existing work.

## Intentionally excluded from the baseline snapshot

Generated/runtime binary artifacts and a personal test document were not copied:

- `app/__pycache__/*.pyc`
- `data/checkpoints/agent_graph.db`
- `data/chromadb/chroma.sqlite3`
- `tests/Rajeet_Ash_12024002038053_Resume.pdf`

No Qdrant Edge or Code Cubicle feature implementation is included in this provenance commit. Planning and feature development begin after this baseline.
