# Public source documents

The unmodified PDFs in this folder are publicly released issuer documents, retained for reproducible review examples. Original branding and copyright belong to the respective issuers. Inclusion does not imply endorsement.

| File | Issuer | Publication date | Original source |
|---|---|---|---|
| dbs-fy2025-results.pdf | DBS Group Holdings Ltd | 9 February 2026 | [DBS FY2025 press statement](https://www.dbs.com/iwov-resources/images/investors/quarterly-financials/2025/4Q25_press_statement.pdf) |
| sgx-fy2025-results.pdf | Singapore Exchange Limited | 8 August 2025 | [SGX results announcement and attachments](https://links.sgx.com/1.0.0/corporate-announcements/XUUV259STK54LDMT/) |

Source metadata is stored in `sources.json`. The example article claims in `desk/examples.py` are test inputs, not published news articles. They include deliberately altered and invented statements. Expected outcomes explain the examples and are never passed to the model or used as its response. The application runs actual inference against the supplied PDFs.

The library contains five claim scenarios over these two PDFs. The prepared starter review uses DBS with two claims: net profit of SGD 11.0 billion and deliberately altered total income of SGD 28.9 billion. The PDF reports total income of SGD 22.9 billion. Human assessments are separate for each finding.
