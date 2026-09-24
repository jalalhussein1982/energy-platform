# DRAFT — NOT SENT — ČEPS: terms of the structured-data web service, and `value1` / `value2` in `Load`

**To:** ceps@ceps.cz (general contact, www.ceps.cz/en/contact, read 2026-09-24)
**Subject:** Automated use of the CepsData web service (`Load`) — terms, and a question on `value1` / `value2`

Dear Sir or Madam,

I am building a data-ingestion system that reads the system load (`Load`, aggregation QH,
function AVG, version RT) from your structured-data web service, one request every
15 minutes. Before I rely on it, I would like to confirm the following:

1. Under what terms may the web-service data be collected automatically, stored, and used?
2. `robots.txt` on www.ceps.cz disallows all crawling. Does that rule apply to the documented
   web service as well, or only to the website?
3. Is there a rate limit or a preferred polling frequency?
4. May a few days of real responses be published in a public code repository as test data,
   and with what attribution?

Until then, only synthetic test data with the same structure is published.

I also have a question on the data itself. In the `Load` response, `value1` is described as
"Load including pumping [MW]" and `value2` as "Load [MW]". For 19 September 2026, with
aggregation QH (and HR), function AVG and version RT, `value1` equals `value2` on every item,
while for the daily aggregate (DY) they differ (`value1` = 6 642.343, `value2` = 6 419.655).

5. Does the real-time quarter-hour series include pumped-storage consumption at all, or is
   `value1` in QH/RT the same quantity as `value2` by construction?
6. If they differ in some periods, which series is the "system load" figure you publish?

We store both series as published (`value1` as load including pumping, `value2` as load) and
record the equality as an open question.

Kind regards,
Jalal Hussein

---
_Repository record: `docs/01-data-scope.md` §10 (T3: "terms of the web service; confirm the
robots rule does not cover the service; rate expectations"); `docs/06-source-verification.md`
§4 and §4.2 (`value1` equals `value2` on every QH item). Merged 2026-09-24 from the two earlier
drafts (`ceps-web-service-terms.md`, `ceps-load-value1-value2.md`) so ČEPS receives one letter._
