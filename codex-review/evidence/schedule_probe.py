"""Synthetic probe of a capture Job starting 25 seconds after its scheduled minute."""
from dataclasses import asdict
from datetime import timedelta
import json
from tests.runtime.harness import runtime, SCHEDULED
from energy_platform.runtime import capture,process
from energy_platform.runtime.gaps import detect_gaps
from energy_platform.runtime.backfill import backfill
from probe_store import fresh_store
rt=runtime(store=fresh_store())
actual_start=SCHEDULED+timedelta(seconds=25,microseconds=693263)
rt.clock.now=actual_start
assert capture(rt,actual_start).outcome=='ok'
assert process(rt)[0].outcome=='ok'
rt.clock.now=SCHEDULED+timedelta(minutes=31)
gaps=detect_gaps(rt,lookback=timedelta(minutes=31,seconds=1))
phantom=next(g for g in gaps if g.scheduled_for==SCHEDULED)
assert phantom.kind=='missing_capture',phantom
before=[asdict(r) for r in rt.store.runs(rt.target_id)]
refetched=backfill(rt,limit=1)
assert len(refetched)==1 and refetched[0].outcome=='ok'
print(json.dumps({'actual_successful_capture':actual_start,'expected_slot':SCHEDULED,'gaps':[asdict(g) for g in gaps],'ledger_before_backfill':before,'unnecessary_backfill':asdict(refetched[0]),'bronze_capture_count_after':len(rt.bronze.log.list(rt.target_id))},indent=2,default=str))
