# GRAG Edge Implementation Roadmap

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

This index orders the phase plans. Execute them sequentially unless a plan explicitly marks work optional. Each phase has its own exit gate; do not start a later phase by bypassing an earlier gate.

| Phase | Plan | Depends on | Required |
|---|---|---|---|
| P0 | `2026-09-30-grag-edge-p00-baseline.md` | approved spec | yes |
| P1 | `2026-09-30-grag-edge-p01-qdrant-edge-storage.md` | P0 | yes |
| P2 | `2026-09-30-grag-edge-p02-hybrid-retrieval.md` | P1 | yes |
| P3 | `2026-09-30-grag-edge-p03-memory-provenance.md` | P2 | yes |
| P4 | `2026-09-30-grag-edge-p04-policy-outbox.md` | P3 | yes |
| P5 | `2026-09-30-grag-edge-p05-connectivity-upload.md` | P4 | yes |
| P6 | `2026-09-30-grag-edge-p06-fleet-refresh.md` | P5 | yes |
| P7 | `2026-09-30-grag-edge-p07-conflicts-dedupe.md` | P6 | yes |
| P8 | `2026-09-30-grag-edge-p08-grag-integration.md` | P7 | yes |
| P9 | `2026-09-30-grag-edge-p09-dashboard.md` | P8 | yes |
| P10 | `2026-09-30-grag-edge-p10-demo-tooling.md` | P9 | yes |
| P11 | `2026-09-30-grag-edge-p11-fleet-transfer.md` | P10 | optional |
| P12 | `2026-09-30-grag-edge-p12-hardening-submission.md` | P10; P11 if shipped | yes |

## Cross-phase rules

- Qdrant Edge is the production local memory engine; ChromaDB is removed from the production path by P8.
- Qdrant Edge is embedded in the Edge API process and isolated behind `QdrantEdgeStore`.
- Qdrant Server is optional at runtime; cloud failure must never block edge API readiness.
- SQLite is the operational control plane, not the searchable memory store.
- Local dense embeddings use the existing GRAG embedding service initially; sparse search uses Qdrant Edge `Bm25`.
- Neo4j remains optional enrichment and cannot be required for offline search or local GRAG answers.
- Every phase follows TDD and ends with its exit-gate command plus a commit.
- Execute implementation in an isolated worktree.
