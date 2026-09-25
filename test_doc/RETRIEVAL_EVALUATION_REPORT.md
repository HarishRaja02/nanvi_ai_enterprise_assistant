# Nanvi Retrieval Evaluation Report

Controlled corpus: 9 document/email sources plus isolated test identities. No production data used.

## Results

- Test records: **12**
- Relevant-source retrieval cases: **10/10**
- Missing relevant source: **0**
- Irrelevant returned results (aggregate): **9**
- Permission-filtering failures: **0**
- Duplicate returned source IDs: **0**
- Empty-result case correctly empty: **1 / 1**

## Evaluation records

| Question | Expected | Actual top result | Returned source(s) | Correct | Reason |
|---|---|---|---|---|---|
| Project Atlas launch date | 2026-10-15 | Project Atlas launches on 2026-10-15. Milestone review is 2026-10-01. | projects/roadmap.txt | PASS | Relevant source retrieved. |
| Q2 revenue | 150000 | Quarter Revenue Q1 120000 Q2 150000 Q3 130000 | finance/revenue.csv; reports/revenue-summary.pdf; sales/monthly.csv | PASS | Relevant source retrieved. 2 irrelevant result(s) also returned. |
| Alice salary | NO_ACCESS | EMPTY | None | PASS | Relevant source retrieved. |
| Acme renewal PDF | 2026-11-30 | Customer renewal for Acme is due on 2026-11-30. | customers/renewal.pdf; mail-1 | PASS | Relevant source retrieved. 1 irrelevant result(s) also returned. |
| A-100 stock | 42 | SKU Stock A-100 42 B-200 17 | inventory.xlsx; sales/monthly.csv | PASS | Relevant source retrieved. 1 irrelevant result(s) also returned. |
| remote work days | three | Remote work policy allows three remote days per week. | policy.txt | PASS | Relevant source retrieved. |
| Acme renewal email | 2026-11-30 | Acme renewal is due on 2026-11-30. | mail-1; customers/renewal.pdf | PASS | Relevant source retrieved. 1 irrelevant result(s) also returned. |
| Alice project owner | Alice | Alice is the Atlas project owner. | people/alice.docx; projects/roadmap.txt; hr/salary.docx | PASS | Relevant source retrieved. 2 irrelevant result(s) also returned. |
| March revenue | 300 | Month Revenue January 100 February 200 March 300. | sales/monthly.csv; reports/revenue-summary.pdf | PASS | Relevant source retrieved. 1 irrelevant result(s) also returned. |
| Acme renewal | 2026-11-30 | Acme renewal is due on 2026-11-30. | mail-1; customers/renewal.pdf | PASS | Relevant source retrieved. |
| annual revenue summary | 150000 | Annual revenue summary: Q1 120000, Q2 150000, Q3 130000. | reports/revenue-summary.pdf; sales/monthly.csv | PASS | Relevant source retrieved. 1 irrelevant result(s) also returned. |
| something completely absent | EMPTY | EMPTY | None | PASS | Relevant source retrieved. |

## Pipeline validation

- **Ingestion/extraction:** PDF, DOCX, XLSX and CSV parsers were exercised with generated fixtures; TXT was directly indexed through the local-file path.
- **Chunking:** bounded chunking was exercised, including multi-section PDF/XLSX document indexing.
- **Metadata:** filename/path/source type plus PDF page and XLSX sheet are preserved by `index_document`.
- **Embeddings:** deterministic test embedding exercised the provider contract; no production embedding vendor was assumed.
- **Vector storage:** in-memory vector store exercised with cosine search.
- **Retrieval:** hybrid keyword + vector retrieval exercised.
- **Filtering:** RBAC/ABAC/tenant restrictions applied before reranking and before the result reaches the agent/LLM.
- **Ranking:** measured failures were found in zero-similarity pollution and source-term ambiguity; both were fixed without increasing `top_k`.
- **Context construction:** typed `PromptContext` preserves user/retrieved/tool-result separation; retrieval output contains only authorized chunks.
- **Source preservation:** source identity is retained and page/sheet locations are preserved for structured document sections.

## Measured improvements

1. Vector search no longer returns zero-similarity chunks. This eliminated unrelated results for out-of-corpus queries.
2. Authorization is now applied before reranking. Restricted high-scoring chunks can no longer consume the rerank budget and hide an authorized result.
3. Keyword retrieval includes source filenames as metadata, and lexical score is used only as a small deterministic tie-breaker. This corrected measured ambiguity such as `renewal PDF` and `March revenue` without increasing `top_k`.
4. `index_document()` preserves PDF page and XLSX sheet metadata during retrieval.

## Final validation

The complete suite was rerun after the retrieval fixes: **176 passed, 2 warnings**. The warnings are existing test-only PyJWT short-key warnings.
