# Regulatory Compliance

## Authority Hierarchy

When guidance conflicts, apply:

UK law -> FCA -> HMRC -> exchange or venue rules -> vendor or contract terms.

## Market Abuse Constraints

- Prohibited conduct includes insider dealing, unlawful disclosure of inside information, and market manipulation.
- Any trading workflow should tag information by provenance and only act on information that is provably public and permissible to use.

## Algorithmic Trading Controls

- Pre-trade controls: thresholds, limits, price collars, max size and value, message-rate caps.
- Live controls: strategy health checks, connectivity and latency monitoring, kill switch, cancel-all capability.
- Post-trade controls: audit trail, parameter snapshots, incident logging.

## Practical Interpretation

- Treat compliance constraints as a system-design input, not a documentation afterthought.
- Do not treat the FCA NSM as a real-time news feed; use it as an archive and audit source.

## Primary References

```text
FCA MAR 7A.3 (algo requirements): https://handbook.fca.org.uk/handbook/MAR/7A/3.html
FCA best execution (client orders): https://handbook.fca.org.uk/handbook/COBS/11/2A.html
FCA NSM user guide (archive/timing): https://www.fca.org.uk/publication/primary-market/nsm-investor-user-guide.pdf
```
