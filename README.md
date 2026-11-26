# Search Patterns vs. a Fixed List: Finding Agent-Directed Text in Common Crawl

Code and results for the experiment in our CS259 (UCLA, Fall 2026) final report,
*The World Wide Web: The Future of the Web and the Threat of Indirect Prompt Injection*,
by Rahul Tripathi and Armaan Oberai.

Prior work on in-page prompt injection ([Khodayari et al., CCS 2026](https://trouge.net/papers/promptinjection_ccs2026.pdf))
finds injections by matching a fixed list of exact indicator phrases. People paraphrase.
We ask whether **search-engine queries that express the pattern** behind those phrases find
agent-directed pages that a fixed list misses, and with what precision.

## Setup

- **Corpus:** Common Crawl CC-MAIN-2026-30 (July 2026), plain-text WET records, 1,892,968,130 pages.
- **Index:** Apache Solr 10, 32 shards, word positions stored (phrase and proximity queries),
  standard tokenizer + lowercasing, no stemming.
- **Query sets:**
  - **Exact list `B`** (baseline): 11 seed indicator phrases, exact match
    (e.g. *ignore all previous instructions*, *if you are an LLM*).
  - **Override queries `O`:** verb × scope × object with up to 2 words between terms (Lucene slop 2):
    9 verbs (*ignore, disregard, forget, …*) × 10 scope words (*previous, prior, your, …*) ×
    8 objects (*instructions, prompts, rules, …*) = 720 clauses.
  - **AI-addressing queries `A`:** 15 phrases addressing the reader as an AI
    (e.g. *if you are ChatGPT*, *AI agents reading this*).
  - Search set `S = O ∪ A`. Overlaps (`S \ B`, `B \ S`) are computed exactly in Solr as Boolean queries.
- **Labeling:** up to 40 pages per set, one per domain. A page is a true positive if its text is
  written to instruct or steer an AI agent; pages that discuss, quote, or demonstrate prompt
  injection are false positives. Single annotator.

## Results

| Set | Pages | Sampled precision (95% Wilson CI) | Est. agent-directed pages |
|---|---:|---|---:|
| Exact list `B` | 102,396 | 19/39 = 48.7% (33.9–63.8%) | ~49.9K |
| AI-addressing, not in `B` | 56,066 | 28/40 = 70.0% (54.6–81.9%) | ~39.2K |
| Override (scoped, v2), not in `B` | 17,597 | 9/32 = 28.1% (15.6–45.4%) | ~4.9K |
| Override (loose, v1), not in `B` | 898,693 | 0/35 | ~0 |

- Search queries match 175,994 pages and miss only **6** of the exact list's pages.
- They add about **44K** agent-directed pages to the list's ~49.9K, nearly doubling the total.
- Loose proximity queries (v1: no scope word, slop 4) return only noise; query design matters.
- Each count query over 1.89B pages takes 1–25 seconds.

**Limitations:** the seed list has 11 phrases (the paper used 3,963); WET text has no HTTP headers,
`<meta>` tags, comments, or structured data, where most injections live; samples are small and
labeled by one annotator. "Agent-directed" is broader than "injection", so these counts are not
directly comparable to the paper's 15,387 injections.

## Repository layout

```
src/
  ipi_search_exp.py      # v1: exact list vs. loose override (slop 4) + AI-addressing queries
  ipi_search_exp_v2.py   # v2: scoped override queries (verb + scope + object, slop 2)
  sample_family.py       # samples pages matched by AI-addressing queries but not by the list
results/
  v1/, v2/               # counts.json (hits and time per query and per clause), samples.jsonl
  family/                # samples_address.jsonl
  labels.json            # manual labels for every sampled page, with the labeling criterion
  SUMMARY.md             # results table
```

`samples.jsonl` records hold the page id, URL, domain, the matched text, and a short window of
page text around the match, taken from the public Common Crawl corpus.

## Running

The scripts need Python 3.8+ (standard library only) and are read-only against Solr. They were run
on the machine that hosts the index, and use a local page-store reader (`query_store.fetch`) to
fetch full page text for sampling. Point them at your own setup with environment variables:

| Variable | Meaning | Default |
|---|---|---|
| `IPI_SOLR` | Solr base URL | `http://127.0.0.1:18983/solr` |
| `IPI_CORE_PREFIX` | shard core name prefix | `cc_july_` |
| `IPI_NUM_SHARDS` | number of shards | `32` |
| `IPI_STORE_BIN` | directory containing `query_store.py` | our server path |
| `IPI_STORE_CONF` | page-store config (`search.json`) | our server path |

```bash
python3 src/ipi_search_exp.py out_v1 40      # output dir, samples per set
python3 src/ipi_search_exp_v2.py out_v2 40
cd src && python3 sample_family.py 40        # writes out_family/samples_address.jsonl
```

Estimated pages = hits × sampled precision; interval bounds are scaled the same way.

## Citation

R. Tripathi and A. Oberai, "The World Wide Web: The Future of the Web and the Threat of Indirect
Prompt Injection," CS259 Final Report, University of California, Los Angeles, Fall 2026.
