# Legal And Governance Constraints

## Purpose

Capture the legal, tax, licensing, and evidence-handling rules that constrain the project.

These are not optional documentation notes. They are system-design inputs.

## Authority Hierarchy

When guidance conflicts, apply this order:

1. UK law and official legislation
2. FCA Handbook and FCA publications
3. HMRC manuals and GOV.UK guidance
4. Exchange and venue rules
5. Vendor terms, licensing, and API documentation
6. Blogs, forums, and other secondary commentary

## Market Abuse And Information Handling

- Prohibited conduct includes insider dealing, unlawful disclosure of inside information, and market manipulation.
- Any trading workflow should tag information by provenance and only act on information that is demonstrably public and permissible to use.
- The FCA NSM should be treated as an archive and audit source, not as a real-time news feed.
- Public announcement feeds and delayed market data should not be assumed to be operationally equivalent to licensed real-time infrastructure.

## Algorithmic Trading Control Expectations

Minimum expected controls for any automated or semi-automated trading system:

- pre-trade limits: max size, max value, price collars, exposure caps, message-rate limits
- live controls: health checks, latency/connectivity monitoring, kill switch, cancel-all capability
- post-trade controls: audit trail, parameter snapshots, incident logging, reconciliation

## Tax Treatment Constraints

Educational only. HMRC classification is facts-and-circumstances based and real filings should be handled with professional advice.

### Investor Vs Trader

- HMRC states that transactions in shares normally do not amount to trading for tax purposes.
- Frequency alone should not be treated as sufficient evidence of trading status.

### Capital Gains Mechanics

- Shares are usually pooled into a Section 104 holding.
- Same-day and 30-day matching rules can identify shares outside the pool.
- A tax-lot engine should implement these rules deterministically rather than relying on broker exports.

### Stamp Taxes

- SDRT has a principal charge at 0.5% of consideration in scope, subject to exemptions and special cases.

## High-Impact Resolution Rules

- NSM vs RNS timeliness: use RNS for speed and NSM as the archive.
- "Share dealing is always trading" vs HMRC guidance: default to HMRC's position that share transactions normally do not amount to trading.
- "Free data is free to use for anything" vs license terms: free access does not remove contractual restrictions.

## Project Rule

If a claim affects legality, taxation, licensing, or execution behavior, trace it back to a primary source before treating it as project context.

## Primary References

```text
FCA MAR 7A.3 (algo requirements): https://handbook.fca.org.uk/handbook/MAR/7A/3.html
FCA best execution (client orders): https://handbook.fca.org.uk/handbook/COBS/11/2A.html
FCA NSM user guide (archive/timing): https://www.fca.org.uk/publication/primary-market/nsm-investor-user-guide.pdf
BIM20250 (shares usually not trading): https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim20250
BIM20205 (badges of trade): https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim20205
CG51550 (Section 104 holding/share pooling): https://www.gov.uk/hmrc-internal-manuals/capital-gains-manual/cg51550
GOV.UK CGT rates: https://www.gov.uk/capital-gains-tax/rates
STSM031010 (SDRT principal 0.5%): https://www.gov.uk/hmrc-internal-manuals/stamp-taxes-shares-manual/stsm031010
```
