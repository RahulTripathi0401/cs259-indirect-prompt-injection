#!/usr/bin/env python3
"""Exact indicator matching vs. search-engine queries for in-page prompt injection.

Index: Solr over Common Crawl CC-MAIN-2026-30 WET text (32 shards, body indexed
with positions, StandardTokenizer + lowercase, no stemming).

Baseline (B): a seed list of exact indicator phrases, as in keyword /
Aho-Corasick matching (Khodayari et al., CCS 2026).
Search (S):  the same intent expressed as search-engine queries: verb x object
proximity queries (slop) plus AI-addressing phrases.
Novel = S AND NOT B: pages the search engine finds that the exact list misses.

Outputs (in the output directory):
  counts.json      totals for B, S, S-not-B, per-family and per-pattern counts, timings
  samples.jsonl    random samples from B and from S-not-B with a text window around the match
Python 3.8, standard library only. Read-only against Solr and the page store.
"""
import json, os, re, sys, time, random, urllib.parse, urllib.request
from pathlib import Path

SOLR = os.environ.get('IPI_SOLR', 'http://127.0.0.1:18983/solr')
CORES = ['%s%03d' % (os.environ.get('IPI_CORE_PREFIX', 'cc_july_'), i) for i in range(int(os.environ.get('IPI_NUM_SHARDS', '32')))]
SHARDS = ','.join(SOLR.split('://', 1)[-1] + '/' + c for c in CORES)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else 'out')
SAMPLE_N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
OUT.mkdir(parents=True, exist_ok=True)

# ---------------- query definitions ----------------
BASELINE = [  # exact seed indicators (slop 0)
    'ignore previous instructions', 'ignore all previous instructions',
    'disregard previous instructions', 'disregard all previous instructions',
    'ignore prior instructions', 'ignore all prior instructions',
    'ignore the above instructions', 'forget all previous instructions',
    'forget past commands', 'if you are an llm', 'if you are an ai',
]
VERBS = ['ignore', 'disregard', 'forget', 'override', 'bypass', 'discard', 'skip', 'abandon', 'neglect']
OBJECTS = ['instructions', 'instruction', 'prompts', 'prompt', 'commands', 'directives',
           'rules', 'guidelines', 'directions', 'context']
OVERRIDE_SLOP = 4
ADDRESS = [  # AI-addressing phrases (small slop)
    ('if you are an ai', 1), ('if you are an llm', 1), ('if you are a language model', 2),
    ('if you are a large language model', 1), ('if you are a chatbot', 1), ('if you are chatgpt', 1),
    ("if you're an ai", 1), ('if you are an ai agent', 1), ('if you are an ai assistant', 1),
    ('ai reading this', 2), ('llm reading this', 2), ('language models reading this', 2),
    ('ai agents reading this', 2), ('note to ai', 1), ('attention ai', 1),
]

def phrase(p, slop=0):
    return '"%s"%s' % (p.replace('"', ''), ('~%d' % slop) if slop else '')

B_Q = '(' + ' OR '.join(phrase(p) for p in BASELINE) + ')'
OVR_CLAUSES = [(v, o, phrase('%s %s' % (v, o), OVERRIDE_SLOP)) for v in VERBS for o in OBJECTS]
OVR_Q = '(' + ' OR '.join(c for _, _, c in OVR_CLAUSES) + ')'
ADR_Q = '(' + ' OR '.join(phrase(p, s) for p, s in ADDRESS) + ')'
S_Q = '(%s OR %s)' % (OVR_Q, ADR_Q)

# ---------------- solr helpers ----------------
def select(q, rows=0, fq=None, fl='id,url,domain', extra=None):
    params = {'q': q, 'defType': 'lucene', 'df': 'body', 'q.op': 'OR', 'rows': rows, 'fl': fl,
              'shards': SHARDS, 'wt': 'json'}
    fqs = ['record_type:page'] + ([fq] if fq else [])
    data = urllib.parse.urlencode(list(params.items()) + [('fq', f) for f in fqs] + list((extra or {}).items()))
    t = time.perf_counter()
    for attempt in range(4):
        try:
            req = urllib.request.Request(SOLR + '/' + CORES[0] + '/select', data=data.encode(),
                                         headers={'Content-Type': 'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req, timeout=600) as r:
                res = json.load(r)
            return res, time.perf_counter() - t
        except Exception as e:  # transient overload
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))

def count(q, fq=None):
    res, dt = select(q, 0, fq)
    return res['response']['numFound'], dt

# ---------------- page fetch (reuse the store reader) ----------------
sys.path.insert(0, os.environ.get('IPI_STORE_BIN', '/mnt/beegfs/dgx/tripathi/commoncrawl/bin'))
from query_store import fetch  # noqa: E402
CONF = json.loads(Path(os.environ.get('IPI_STORE_CONF', '/mnt/beegfs/dgx/tripathi/commoncrawl/crawls/CC-MAIN-2026-30/incremental-system-v1/search.json')).read_text())

VERB_RE = '|'.join(VERBS)
OBJ_RE = '|'.join(OBJECTS)
MATCH_RE = re.compile(r'\b(%s)\b(?:\W+\w+){0,4}?\W+\b(%s)\b|if you(?: are|\'re) an? (?:ai|llm|language model|large language model|chatbot)|(?:ai|llm|language models?|ai agents?) reading this|note to ai|attention ai|if you are chatgpt' % (VERB_RE, OBJ_RE), re.I | re.S)

def window(text, width=260):
    m = MATCH_RE.search(text)
    if not m:
        return None, None
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return re.sub(r'\s+', ' ', text[a:b]), re.sub(r'\s+', ' ', m.group(0))

def sample(q, n, tag, seed):
    """Uniform-ish sample: restrict to random SHA-256 id prefixes, take first hits."""
    rnd = random.Random(seed)
    got, seen_domains, tried = [], set(), 0
    hexd = '0123456789abcdef'
    while len(got) < n and tried < 400:
        tried += 1
        p = rnd.choice(hexd) + rnd.choice(hexd)
        res, _ = select(q, rows=5, fq='id:%s*' % p, fl='id,url,domain')
        for d in res['response']['docs']:
            if len(got) >= n or d['domain'] in seen_domains:
                continue  # one page per domain to avoid template floods
            try:
                page = fetch(CONF, d['id'])
            except Exception as e:
                continue
            w, m = window(page.get('text', ''))
            seen_domains.add(d['domain'])
            got.append({'set': tag, 'id': d['id'], 'url': d['url'], 'domain': d['domain'], 'match': m, 'window': w})
    return got

def main():
    t0 = time.perf_counter()
    out = {'index_docs': None, 'queries': {}, 'baseline_phrases': BASELINE,
           'override_verbs': VERBS, 'override_objects': OBJECTS, 'override_slop': OVERRIDE_SLOP,
           'address_phrases': ADDRESS}
    out['index_docs'], _ = count('*:*')
    for name, q in [('B', B_Q), ('S', S_Q), ('S_not_B', '%s AND NOT %s' % (S_Q, B_Q)),
                    ('B_not_S', '%s AND NOT %s' % (B_Q, S_Q)),
                    ('override', OVR_Q), ('override_not_B', '%s AND NOT %s' % (OVR_Q, B_Q)),
                    ('address', ADR_Q), ('address_not_B', '%s AND NOT %s' % (ADR_Q, B_Q))]:
        n, dt = count(q)
        out['queries'][name] = {'hits': n, 'seconds': round(dt, 2)}
        print(name, n, round(dt, 2), flush=True)
    # per-seed exact counts
    out['baseline_each'] = {}
    for p in BASELINE:
        n, dt = count(phrase(p))
        out['baseline_each'][p] = {'hits': n, 'seconds': round(dt, 2)}
    # per-pattern novel counts
    out['override_each'] = {}
    for v, o, c in OVR_CLAUSES:
        n, dt = count('%s AND NOT %s' % (c, B_Q))
        out['override_each']['%s~%s' % (v, o)] = {'novel_hits': n, 'seconds': round(dt, 2)}
    out['address_each'] = {}
    for p, s in ADDRESS:
        n, dt = count('%s AND NOT %s' % (phrase(p, s), B_Q))
        out['address_each'][p] = {'novel_hits': n, 'seconds': round(dt, 2)}
    (OUT / 'counts.json').write_text(json.dumps(out, indent=1))
    print('counts done', round(time.perf_counter() - t0, 1), flush=True)
    samples = sample(B_Q, SAMPLE_N, 'B', 1) + sample('%s AND NOT %s' % (S_Q, B_Q), SAMPLE_N, 'S_not_B', 2)
    with open(OUT / 'samples.jsonl', 'w') as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')
    out['total_seconds'] = round(time.perf_counter() - t0, 1)
    (OUT / 'counts.json').write_text(json.dumps(out, indent=1))
    print('all done', out['total_seconds'], flush=True)

if __name__ == '__main__':
    main()
