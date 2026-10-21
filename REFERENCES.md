# Primary references and implementation boundaries

- [BM25: The Probabilistic Relevance Framework](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf)
- [Retrieval-augmented generation](https://arxiv.org/abs/2005.11401)

The frozen confirmation protocol uses the existing BM25 formulation from Robertson and Zaragoza (2009), [The Probabilistic Relevance Framework: BM25 and Beyond](https://doi.org/10.1561/1500000019) (publisher record and author-hosted PDF verified). The unique-term-overlap comparator is specified directly in [the frozen protocol](experiments/AI01-freeze.json); it is not a claim of reproducing another retrieval system. [The confirmation report](reports/AI01.md) defines source recall and the retrieval-based false support proxy with separate denominators.

The implementation, data provenance and scope limits are documented in [the technical case study](reports/applied-study.md). Citation identifies an algorithmic foundation, not equivalence with the full paper or a claim of hardware performance.
