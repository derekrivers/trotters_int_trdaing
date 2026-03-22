# Risk And Research References

## Purpose

Keep the minimum viable project risk model and the supporting non-operational research references in one place.

## Risk Stack

- market risk
- liquidity risk
- model risk
- operational risk
- compliance risk

## Minimum Viable Controls

### Pre-Trade

- max order size and value
- max daily loss
- concentration and leverage caps
- price collars

### Live

- drawdown circuit breakers
- kill switch
- message-rate monitoring
- venue and service health checks

### Post-Trade

- reconciliation
- P&L attribution
- incident logging
- model drift checks

## Data Governance Blueprint

BCBS 239 is a useful template for:

- accuracy
- completeness
- timeliness
- lineage
- governance

## Supporting Research References

These are supporting references, not part of the ranked operational source stack.

### Risk Data Governance

```text
BCBS 239 (2013): https://www.bis.org/publ/bcbs239.pdf
```

### Market Structure And HFT Context

```text
BIS Working Paper 1290 (2025): https://www.bis.org/publ/work1290.pdf
BIS Quarterly Review (December 2025): https://www.bis.org/publ/qtrpdf/r_qt2512.pdf
```

### Strategy Research Exemplars

```text
Jegadeesh and Titman (1993): https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf
Fama and French (1993): https://www.bauer.uh.edu/rsusmel/phd/Fama-French_JFE93.pdf
Fama and French (2015): https://tevgeniou.github.io/EquityRiskFactors/bibliography/FiveFactor.pdf
Carhart (1997): https://finance.martinsewell.com/fund-performance/Carhart1997.pdf
```
