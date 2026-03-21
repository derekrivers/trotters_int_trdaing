# Ranked Free Sources for UK Professional Stock Trading

This project uses a short list of canonical sources. The goal is to prioritize:

- legal and official truth for UK obligations,
- venue-native truth for execution mechanics,
- government-register truth for issuer structure,
- pragmatic free market-data tooling for research pipelines.

## Ranked Top Five

1. FCA: Handbook and National Storage Mechanism
2. HMRC: manuals and GOV.UK rates
3. London Stock Exchange: MIT201, rulebook, RNS, delayed-data terms
4. Companies House: REST and streaming APIs
5. Alpha Vantage: free market-data API with quota and terms constraints

## Why This Ranking

The ranking is governance-first. The highest-cost failures in this domain are compliance, tax, and execution misuse, so official and venue-native sources come before market-data convenience.

## Direct Primary Links

```text
FCA Handbook: https://handbook.fca.org.uk/home
FCA MAR 7A.3 (algo controls): https://handbook.fca.org.uk/handbook/MAR/7A/3.html
FCA NSM landing page: https://www.fca.org.uk/markets/primary-markets/regulatory-disclosures/national-storage-mechanism
FCA NSM user guide (export limits, not real-time): https://www.fca.org.uk/publication/primary-market/nsm-investor-user-guide.pdf

HMRC BIM20250 (shares usually not a trade): https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim20250
HMRC CG51550 (Section 104 holding/share pooling): https://www.gov.uk/hmrc-internal-manuals/capital-gains-manual/cg51550
GOV.UK CGT rates: https://www.gov.uk/capital-gains-tax/rates
HMRC STSM031010 (SDRT 0.5% principal rate): https://www.gov.uk/hmrc-internal-manuals/stamp-taxes-shares-manual/stsm031010

LSE MIT201 (Guide to the trading system): https://docs.londonstockexchange.com/sites/default/files/documents/mit201-guide-to-the-trading-system-15-7-20251208.pdf
LSE Rules (effective 19 January 2026): https://docs.londonstockexchange.com/sites/default/files/documents/rules-of-the-london-stock-exchange-effective-19-january-2026_0.pdf
LSE RNS: https://www.lse.co.uk/rns/
LSE delayed market data terms: https://www.londonstockexchange.com/delayed-market-data/terms-and-conditions.htm

Companies House API home: https://developer.company-information.service.gov.uk/
Companies House REST API overview: https://developer.company-information.service.gov.uk/overview
Companies House authentication: https://developer.company-information.service.gov.uk/authentication
Companies House rate limiting: https://developer-specs.company-information.service.gov.uk/guides/rateLimiting
Companies House streaming API overview: https://developer-specs.company-information.service.gov.uk/streaming-api/guides/overview
Companies House service info (not verified): https://resources.companieshouse.gov.uk/serviceInformation.shtml

Alpha Vantage documentation: https://www.alphavantage.co/documentation/
Alpha Vantage support (25/day): https://www.alphavantage.co/support/
Alpha Vantage terms (commercial use definition): https://www.alphavantage.co/terms_of_service/
```
