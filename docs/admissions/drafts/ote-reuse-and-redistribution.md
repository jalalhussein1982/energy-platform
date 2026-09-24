# SENT 2026-09-24, ANSWERED 2026-09-24 — OTE: reuse of public market data and redistribution of samples

**Sent** by the author on 2026-09-24 at 01:40 UTC from Gmail with questions 1–3 below; **question 4
(imbalance settlement timing) was not in the sent letter**, so 06 §9.1 stays as observed, not
confirmed. **Answered** by the OTE market desk (`Market@ote-cr.cz`) the same day at 08:19 UTC; the
reply is quoted in full at the end of this file and filed in `01` §10, `06` §1.4 and the six OTE
target manifests.

**To:** market@ote-cr.cz (the market desk, www.ote-cr.cz/en/about-ote/contact, read 2026-09-24)
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
Jalal Hussein

---
_Repository record: `docs/01-data-scope.md` §10 (T1, T2, E1, imbalance settlement: "written
confirmation of reuse and attribution wording"), V-3; `docs/06-source-verification.md` §1.4, §9.1._

---

## Reply — OTE market desk, 2026-09-24 08:19 UTC

Quoted verbatim (the numbering answers questions 1–3 above); signed by a member of the market desk.

> 1. For internal use only; must not be published to third parties
> 2. For internal use only; must not be published to third parties
> 3. For the Day Ahead market—once a day, whenever prices for that day are published, usually
>    after 1:05 p.m. For Intraday market, you can also download the results once as a summary for
>    the entire day, or continuously after the close of trading for a given 15-minute contract.

**Reading.** Automated collection and storage for internal analysis is consented to (answer 1);
redistribution of any real payload, including small samples in a public repository, is refused
(answer 2), so the synthetic-fixture rule of `01` §10 is permanent for every OTE target and no
attribution wording exists. Answer 3 names the source's expectations: day-ahead once a day after
about 13:05 Prague; intraday either one daily summary or a fetch after each 15-minute contract
closes — the 15-minute cadence of T1/T2 is the second option; the hourly correction re-reads of
the previous three days (`cadence.correction`) and E1's hourly polling from 12:00 on D−1 go
beyond what was described; decided 2026-09-24 as ADR-033 amendment 3
(corrections once a day, E1 four reads after 13:05).
The message footer states that an OTE e-mail is not a contract and that OTE binds itself only in
signed writing: the reply is the market desk's written answer to the Terms-of-Use question, not
a licence. Evidence: the Gmail thread in the author's account (subject as above).
