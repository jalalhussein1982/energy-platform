# DRAFT — NOT SENT — ČEPS: terms of use of the structured-data web service

**To:** ČEPS, a.s. — _(address from www.ceps.cz contacts, filled in by the author)_
**Subject:** Terms for automated use of the CepsData web service (`Load`)

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

Kind regards,
_(name, contact)_

---
_Repository record: `docs/01-data-scope.md` §10 (T3: "terms of the web service; confirm the
robots rule does not cover the service; rate expectations"); `docs/06-source-verification.md` §4._
