# Exact indicator list vs. search-engine queries (initial results, 2026-11-16)

Index: Apache Solr over Common Crawl CC-MAIN-2026-30 (July 2026) WET text, 1,892,968,130 pages, 32 shards (dgx.sdsu.edu).
Scripts: `ipi_search_exp.py` (v1, loose), `ipi_search_exp_v2.py` (v2, scope words), `sample_family.py` (AI-addressing sample).
Remote outputs: `~/ipi-search-exp-20261116/{out,out_v2,out_family}`. Labels: `results/labels.json` (single annotator).

| Set | Pages | Sampled precision (95% Wilson CI) | Est. agent-directed pages |
|---|---|---|---|
| Exact list (11 seed phrases) | 102,396 | 19/39 = 48.7% (33.9–63.8%) | ~49.9K (34.7K–65.3K) |
| Override queries v2, not in exact list | 17,597 | 9/32 = 28.1% (15.6–45.4%) | ~4.9K (2.7K–8.0K) |
| AI-addressing queries, not in exact list | 56,066 | 28/40 = 70.0% (54.6–81.9%) | ~39.2K (30.6K–45.9K) |
| Override queries v1 (loose), not in list | 898,693 | 0/35 | ~0 |

Exact list pages not matched by v2 search queries: 6. Query latency over 1.89B pages: 1–25 s per query.

Caveats: seed list is 11 phrases (the paper used 3,963), so "not in list" overstates the gap versus the paper;
WET text only (no headers/HTML/meta, where the paper finds ~70% of injections); samples are one-per-domain and
score-ranked within random id buckets, not uniform; single annotator; 8 unverifiable AI-addressing samples counted as false positives.
