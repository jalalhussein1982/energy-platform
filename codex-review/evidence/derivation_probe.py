"""Simulate a core-only mapping bugfix, with the release identity used by current builds."""
import json
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from tests.runtime.harness import runtime, SCHEDULED
from energy_platform.runtime import capture,process
from energy_platform.runtime.process import map_payload
from energy_platform.runtime.replay import replay_range
from energy_platform.mapping import MappingResult
from energy_platform.store import derivation_for
from energy_platform.parse import parser_ref
from probe_store import fresh_store
rt=runtime(store=fresh_store())
assert capture(rt,SCHEDULED).outcome=='ok'
assert process(rt)[0].inserted==192
old=derivation_for(rt.manifest,parser_ref(rt.manifest)).derivation_id
def first_price():
    return next(r.value for r in rt.store.current_rows(rt.manifest.contract.dataset_id) if r.observation.metric=='price_vwap')
before=first_price()
def corrected(manifest,payload,ctx):
    r=map_payload(manifest,payload,ctx)
    return MappingResult(tuple(o.model_copy(update={'value':o.value+Decimal('1')}) if o.metric=='price_vwap' and o.value is not None else o for o in r.observations),r.events)
with patch('energy_platform.runtime.process.map_payload',corrected):
    replay_range(rt,SCHEDULED,SCHEDULED+timedelta(minutes=1))
    still_same=derivation_for(rt.manifest,parser_ref(rt.manifest)).derivation_id
    bad=process(rt)
    after=first_price()
    assert after==before and bad[0].inserted==0 and old==still_same
    rt.clock.advance(timedelta(seconds=1))
    with patch('energy_platform.__version__','0.0.2'):
        new=derivation_for(rt.manifest,parser_ref(rt.manifest)).derivation_id
        replay_range(rt,SCHEDULED,SCHEDULED+timedelta(minutes=1))
        good=process(rt)
        fixed=first_price()
assert fixed==before+Decimal('1') and good[0].inserted==192
print(json.dumps({'same_version':{'derivation_before':old,'derivation_after':still_same,'price_before':before,'price_after':after,'process':[asdict(r) for r in bad]},'bumped_version_control':{'derivation':new,'price_after':fixed,'process':[asdict(r) for r in good]}},indent=2,default=str))
