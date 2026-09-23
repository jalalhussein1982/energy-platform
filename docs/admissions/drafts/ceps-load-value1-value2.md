# DRAFT — NOT SENT — ČEPS: `value1` and `value2` in the `Load` series

**To:** ČEPS, a.s. — _(address from www.ceps.cz contacts, filled in by the author)_
**Subject:** Question on the `Load` web-service series ("Load including pumping" vs "Load")

Dear Sir or Madam,

In the `Load` response of the CepsData web service, `value1` is described as "Load including
pumping [MW]" and `value2` as "Load [MW]". For 19 September 2026, with aggregation QH (and HR),
function AVG and version RT, `value1` equals `value2` on every item. For the daily aggregate
(DY) they differ (`value1` = 6 642.343, `value2` = 6 419.655).

Could you tell me:

1. Does the real-time quarter-hour series include pumped-storage consumption at all, or is
   `value1` in QH/RT the same quantity as `value2` by construction?
2. If they differ in some periods, which series is the "system load" figure you publish?

We store both series as published (`value1` as load including pumping, `value2` as load) and
record the equality as an open question.

Kind regards,
_(name, contact)_

---
_Repository record: `docs/06-source-verification.md` §4.2._
