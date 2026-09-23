# DRAFT — NOT SENT — OTE: reuse of public market data and redistribution of samples

**To:** OTE, a.s. — _(address from www.ote-cr.cz contacts, filled in by the author)_
**Subject:** Permission to reuse public market data (web service `PublicDataService`) and to publish small samples

Dear Sir or Madam,

I am building a data-ingestion system that reads OTE's public market results through the
`PublicDataService` web service and the published daily files. Specifically, it reads
`GetImPricePeriodE` (intraday market), `GetDamPricePeriodE` (day-ahead market),
`GetImbalanceSettlementPeriodE` (imbalance settlement, versions 0, 1 and 2) and the daily
`IM_15MIN_DD_MM_YYYY_EN.xlsx` file. Requests are limited to at most one every 15 minutes per
data set, plus hourly re-reads of the previous three days.

Your Terms of Use say the content may not be reproduced "without the prior written consent of
the Operator". I would therefore like to ask:

1. May the data be collected automatically at the frequency above and stored for internal
   analysis?
2. May small samples, a few days of real responses, be published in a public code repository
   as test data? If so, with what attribution wording?
3. Is there a preferred polling frequency or rate limit for the web service and the daily
   files?
4. When are the monthly (version 1) and final (version 2) imbalance settlements normally
   published for a month? On 23 September 2026 the monthly settlement for August was
   available and the final settlement for June was not.

Until I have your answer, the repository contains only synthetic test data with the same
structure, and no OTE values.

Kind regards,
_(name, contact)_

---
_Repository record: `docs/01-data-scope.md` §10 (T1, T2, E1, imbalance settlement: "written
confirmation of reuse and attribution wording"), V-3; `docs/06-source-verification.md` §1.4, §9.1._
