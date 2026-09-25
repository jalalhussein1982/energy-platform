"""Synthetic review probes on memory or the isolated temporary PostgreSQL helper."""
from pathlib import Path
from dataclasses import asdict
from datetime import timedelta
import json

from energy_platform.bronze import Bronze, MemoryBlobStore, MemoryCaptureLog
from energy_platform.bronze.fixtures import load_fixture
from energy_platform.contracts.manifest import load_manifest
from energy_platform.runtime import capture, process, restore_drill
from energy_platform.runtime.replay import replay_range
from energy_platform.store import derivation_for
from probe_store import fresh_store
from energy_platform.parse import parser_ref
from tests.runtime.harness import Clock, runtime, T1, SCHEDULED

results = {}
# Two committed, admitted targets share one dataset and transport, but publish different versions.
store = fresh_store()
bronze = Bronze(MemoryBlobStore(), MemoryCaptureLog())
manifests=[]
for target, fixture in [('ote_imbalance_settlement','ordinary_day'), ('ote_imbalance_settlement_monthly','march_2026_month')]:
    m = load_manifest(Path('targets')/target/'manifest.yaml')
    entry,payload=load_fixture(Path('targets')/target/'fixtures'/fixture)
    bronze.ingest(entry,payload)
    clock=Clock(entry.fetched_at+timedelta(minutes=1))
    rt=runtime(m,store=store,bronze=bronze,clock=clock,payload=payload)
    reports=process(rt)
    assert reports and all(r.outcome in {'ok','noop'} for r in reports), reports
    manifests.append(m)
# Clock is after all fixture dates. Reconcile over the full history is handled by drill itself.
clock=Clock(max(e.fetched_at for m in manifests for e in bronze.log.list(m.target_id))+timedelta(days=1))
scratch=fresh_store()
report=restore_drill(manifests,scratch=scratch,replica=bronze,live=store,clock=clock)
results['shared_dataset_first_drill']=asdict(report)
results['shared_dataset_second_drill']=asdict(restore_drill(manifests,scratch=scratch,replica=bronze,live=store,clock=clock))
assert not report.ok, 'Probe hypothesis refuted: first shared-dataset rebuild passed'
assert results['shared_dataset_second_drill']['ok'], 'Control failed: warmed rebuild does not pass'
# An ordinary manifest mapping revision gets a distinct derivation, as intended.
rt=runtime(T1, store=fresh_store())
assert capture(rt,SCHEDULED).outcome=='ok'
assert process(rt)[0].outcome=='ok'
changed=T1.model_copy(update={'mapping': T1.mapping.model_copy(update={'ignore_fields': (*T1.mapping.ignore_fields, 'DisplayNote')})})
rt2=runtime(changed,store=rt.store,bronze=rt.bronze,clock=rt.clock)
old_d=derivation_for(T1,parser_ref(T1)).derivation_id
new_d=derivation_for(changed,parser_ref(changed)).derivation_id
assert old_d!=new_d
replay_range(rt2,SCHEDULED,SCHEDULED+timedelta(minutes=1))
process(rt2)
changed_drill=restore_drill([changed],scratch=fresh_store(),replica=rt.bronze,live=rt.store,clock=rt.clock)
results['mapping_revision_drill']=asdict(changed_drill)
results['mapping_revision_derivations']={'old':old_d,'new':new_d}
assert not changed_drill.ok, 'Probe hypothesis refuted: historical mapping reproduced'
print(json.dumps(results,indent=2,default=str))
