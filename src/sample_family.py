#!/usr/bin/env python3
"""Sample pages matched only by the AI-addressing query family (not by the exact list)."""
import json, sys
sys.argv = [sys.argv[0], 'out_family'] + sys.argv[1:]
import ipi_search_exp as m  # reuses queries, select(), sample(), fetch()

n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
q = '%s AND NOT %s' % (m.ADR_Q, m.B_Q)
rows = m.sample(q, n, 'ADR_not_B', 3)
with open(m.OUT / 'samples_address.jsonl', 'w') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print('done', len(rows), flush=True)
