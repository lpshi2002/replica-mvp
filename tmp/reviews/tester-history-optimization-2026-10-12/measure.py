import ast
import hashlib
import json
from pathlib import Path
from typing import Any
from replica_mvp import web_demo
from replica_mvp.web_checkpoint import evaluator_version

output = Path('tmp/reviews/tester-history-optimization-2026-10-12')
source = (output / 'web_demo.py.before').read_text()
node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == '_tester_prompt')
namespace = {'json': json, 'Any': Any, '_COMPANY_START': web_demo._COMPANY_START}
exec(compile(ast.Module(body=[node], type_ignores=[]), '<before>', 'exec'), namespace)
before_prompt = namespace['_tester_prompt']
fields = ('index', 'action', 'element', 'value', 'reason', 'error')
root = Path('work/delphi-ai-v4/single-harness-2026-10-09/final-results/runs')
runs = [root / 'claim-001/web-attempt-004-5fa1c5939ec3',
        root / 'claim-002/web-attempt-002-31975ba1bb37',
        root / 'claim-003/web-attempt-002-a80003d5034d']


def size(text):
    return {'characters': len(text), 'utf8_bytes': len(text.encode())}


def add(bucket, old, new):
    bucket['samples'] += 1
    for side, text in [('before', old), ('after', new)]:
        for key, value in size(text).items():
            bucket[side][key] += value


def bucket():
    return {'samples': 0, 'before': size(''), 'after': size('')}


rows = []
for run in runs:
    events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
    result = json.loads((run / 'demo-result.json').read_text())
    plan = json.loads((run / 'demo-plan.json').read_text())
    checkpoint = json.loads((run / 'checkpoint.json').read_text()) if (run / 'checkpoint.json').exists() else {}
    records = {c['case_id']: c for c in checkpoint.get('cases', [])}
    cases = {c['id']: c for c in plan['cases']}
    histories = {}
    row = {'claim': run.parent.name, 'run': str(run), 'history_payload': bucket(), 'full_prompt': bucket()}
    row['evidence_hashes_before'] = {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in run.rglob('*') if p.is_file()}
    for event in events:
        case_id = event['case_id']
        history = histories.setdefault(case_id, [])
        old_history = history[-15:]
        new_history = web_demo._tester_history(history)
        add(row['history_payload'], json.dumps(old_history, ensure_ascii=False),
            json.dumps(new_history, ensure_ascii=False, separators=(',', ':')))
        assert len(new_history) == len(old_history)
        for old, new in zip(old_history, new_history):
            for key in fields:
                if key != 'reason':
                    assert old.get(key) == new.get(key), (case_id, key)
            if old.get('error') or old['action'] in {'done', 'give_up'} or len(old.get('reason') or '') <= 160:
                assert old.get('reason') == new.get('reason')
        record = records.get(case_id)
        if record:
            # The final observation repeats the last event ID; use its first, pre-action observation.
            observed = next(o['page'] for o in record['observations'] if o['event_id'] == event['event_id'])
            case = dict(cases[case_id])
            instance = record.get('instance') or {}
            case.update({k: instance[k] for k in ('goal', 'steps', 'facts') if k in instance})
            uploads = sorted(u['path'] for u in case.get('uploads', []))
            remaining = plan['budget']['max_actions_per_case'] - event['index'] + 1
            company = record.get('surface') == 'company_app'
            old = before_prompt(case, uploads, observed, history, remaining, company)
            new = web_demo._tester_prompt(case, uploads, observed, history, remaining, company)
            old_data, new_data = json.loads(old), json.loads(new)
            old_data.pop('previous_actions')
            new_data.pop('previous_actions')
            assert old_data == new_data
            add(row['full_prompt'], old, new)
        history.append({k: event[k] for k in fields})
    assert row['evidence_hashes_before'] == {
        str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in run.rglob('*') if p.is_file()}
    rows.append(row)

summary = {'history_payload': bucket(), 'full_prompt': bucket()}
for name in summary:
    for row in rows:
        summary[name]['samples'] += row[name]['samples']
        for side in ('before', 'after'):
            for metric in ('characters', 'utf8_bytes'):
                summary[name][side][metric] += row[name][side][metric]
for row in [*rows, summary]:
    for name in ('history_payload', 'full_prompt'):
        b = row[name]
        if b['before']['utf8_bytes']:
            b['reduction_percent'] = {metric: round(100 * (1 - b['after'][metric] / b['before'][metric]), 3)
                                      for metric in ('characters', 'utf8_bytes')}
versions = ('web_demo.py', 'web_checkpoint.py', 'model_calls.py', 'bundle_runtime.py')
before_version = hashlib.sha256(''.join(hashlib.sha256(
    (output / 'web_demo.py.before' if name == 'web_demo.py' else Path('src/replica_mvp') / name).read_bytes()
).hexdigest() for name in versions).encode()).hexdigest()
assert before_version != evaluator_version()
report = {'method': 'Before/after current tester serializer, replaying identical saved histories and pre-action observations; no live model calls or token/cost estimate.',
          'missing_full_prompt_observations': 'claim-003 has no checkpoint; only its history payload is compared.',
          'evaluator_before': before_version, 'evaluator_after': evaluator_version(),
          'original_evidence_unchanged': True, 'summary': summary, 'runs': rows}
(output / 'measurement.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'summary': summary, 'runs': [{k:v for k,v in r.items() if k != 'evidence_hashes_before'} for r in rows],
                  'evaluator_changed': before_version != evaluator_version()}, ensure_ascii=False, indent=2))
