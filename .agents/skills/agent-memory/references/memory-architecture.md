# References for agent-memory skill

## Hindsight Biomimetic Architecture
- **World Facts**: Objective system truths (e.g. "We run PostgreSQL 16 on AWS Aurora").
- **Experience Facts**: Historical agent interactions and code review findings.
- **Observations**: Deduplicated beliefs synthesized over time, complete with proof counts and lineage.
- **Mental Models**: High-level syntheses guiding autonomous decision-making.

## Hybrid Search Ranking
Hindsight uses a 4-layer retrieval algorithm:
1. **Dense Vector Embeddings**: Captures semantic intent and synonymy.
2. **BM25 Lexical Search**: Matches exact technical terms, acronyms, and variable names (e.g., `ZATCA`, `UUIDv7`, `RCSI`).
3. **Graph Relations**: Traverses entity-relationship links between components and services.
4. **Temporal Weighting**: Prioritizes recent observations while respecting historical lineage.
