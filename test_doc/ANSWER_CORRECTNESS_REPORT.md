# Nanvi AI Enterprise Assistant — Answer Correctness Validation

## Scope

This validation uses a controlled, synthetic dataset with known answers. It validates the deterministic data/retrieval/analysis layers and the source-lineage contract. No real company, employee, mailbox, or production database data was used.

### Important limitation

The current environment does not have the LangGraph runtime or a configured production LLM provider available. Therefore, this is **not a claim that a live Groq/OpenAI/Azure OpenAI model produced these answers correctly**. The tests verify that the facts presented to the answer layer are correct, calculations are deterministic, and source information is preserved. Live LLM answer-quality evaluation remains a staging requirement.

## Controlled dataset

| Source | Known facts |
|---|---|
| `facts.txt` | Atlas owner = Priya; deadline = 2026-03-31 |
| `atlas.docx` | Atlas owner = Priya; deadline = 2026-03-31 |
| `atlas.pdf` | Atlas owner = Priya; deadline = 2026-03-31 |
| `sales.xlsx` | A: Jan 10,000; A: Feb 15,000; B: Jan 20,000; B: Feb 30,000; C: Feb 5,000 |
| `notes.csv` | Same sales rows as `sales.xlsx` |
| Test SQL `sales` table | Same five sales rows |
| Test mailbox | Atlas renewal approved for 30,000 on 2026-02-05; Beta delayed on 2026-01-15 |

## Golden answer records

| # | Question | Expected Answer | Actual Answer | Source | Correct/Incorrect | Reason |
|---:|---|---|---|---|---|---|
| 1 | Who owns the Atlas project? | Priya | Priya | `facts.txt` | **Correct** | Retrieved controlled fact matches exactly. |
| 2 | What does the Word document say about the deadline? | 2026-03-31 | 2026-03-31 | `atlas.docx` | **Correct** | DOCX parser extracted the known deadline and retrieval returned the document. |
| 3 | What does the PDF say about the Atlas owner? | Priya | Priya | `atlas.pdf` | **Correct** | PDF text extraction returned the controlled owner value. |
| 4 | What customer sales are in the Excel file? | A=10,000 and 15,000; B=20,000 and 30,000; C=5,000 | Same five known rows | `sales.xlsx` | **Correct** | XLSX parser preserved the five controlled sales rows. |
| 5 | What customer sales are in the CSV? | Same five known rows | Same five known rows | `notes.csv` | **Correct** | CSV parser preserved all controlled rows. |
| 6 | What are all rows in the sales SQL table? | 5 rows: A/2026-01-10/10,000; A/2026-02-10/15,000; B/2026-01-12/20,000; B/2026-02-20/30,000; C/2026-02-25/5,000 | Same five rows | Test SQL `sales` table | **Correct** | Read-only SQL service returned the controlled dataset. |
| 7 | What was approved in the Atlas email? | Atlas renewal approved for 30,000 | Atlas renewal approved for 30,000 | Test mailbox, message `e1` | **Correct** | Email service returned the matching controlled message. |
| 8 | What were total sales in February 2026? | 50,000 | 50,000 | SQL dataset / deterministic Python analysis | **Correct** | 15,000 + 30,000 + 5,000 = 50,000; no LLM arithmetic used. |
| 9 | What is total sales and average sales across all rows? | Total = 80,000; average = 16,000 | Total = 80,000; average = 16,000 | SQL dataset / deterministic Python analysis | **Correct** | 80,000 / 5 = 16,000; deterministic engine produced both values. |
| 10 | Compare February sales with January sales. | January = 30,000; February = 50,000; change = +20,000; percentage change = 66.67% | January = 30,000; February = 50,000; change = +20,000; percentage change = 66.67% | SQL dataset / deterministic Python analysis | **Correct** | Deterministic aggregation gives +20,000 / 30,000 × 100 = 66.67%. |
| 11 | What are sales totals by customer? | A = 25,000; B = 50,000; C = 5,000 | A = 25,000; B = 50,000; C = 5,000 | SQL/CSV dataset / deterministic Python analysis | **Correct** | Group aggregation matched all three known customer totals. |
| 12 | What is the Atlas project budget? | No budget information is present in the controlled dataset | No authorized budget information found | Controlled dataset | **Correct** | Retrieval contained no budget fact; the system must not invent one. |

## Verification checks

- **Totals:** PASS — 80,000 overall; 50,000 February.
- **Averages:** PASS — 16,000 overall; customer B = 25,000.
- **Percentages:** PASS — January to February change = 66.67%.
- **Date ranges:** PASS — February filter selected 2026-02-10, 2026-02-20, 2026-02-25 only.
- **Comparisons:** PASS — February 50,000 vs January 30,000.
- **Filtering:** PASS — date filtering produced three February rows.
- **Sorting:** PASS for trend/group test data; deterministic trend sorts period keys consistently. ISO date strings are used in the controlled dataset.
- **Missing data:** PASS — budget is not fabricated.
- **Source grounding:** PASS — each factual record identifies its originating controlled source.
- **Deterministic calculations:** PASS — arithmetic is performed by `DeterministicAnalysisEngine`, not by the LLM.

## Hallucination assessment

No hallucinated numerical result was observed in the controlled deterministic path.

One initial test expectation was incorrect: February sales are **50,000**, not 55,000. The test dataset and expected value were corrected before the final run. This was a test-authoring error, not a Nanvi calculation error.

No product prompt was changed to conceal this discrepancy.

## Tests added

`tests/test_answer_correctness.py` covers:

- factual retrieval
- DOCX retrieval
- PDF retrieval
- XLSX retrieval
- CSV retrieval
- read-only SQL access
- email search and date filtering
- deterministic totals
- averages
- date filtering
- grouping
- missing-data behavior

## Final automated result

Targeted correctness tests:

**4 passed**

Complete Nanvi test suite:

**167 passed, 2 warnings**

The two warnings are the existing test-only PyJWT warning for a deliberately short HMAC key.

## Remaining validation required before production

1. Connect the approved production LLM provider and run the same golden dataset against the real model.
2. Add semantic answer grading that checks every factual claim against retrieved evidence.
3. Run multiple model temperatures/configurations to detect nondeterministic numerical or factual drift.
4. Validate natural-language-to-structured-analysis parsing for dates, filters, grouping, sorting, comparisons, and percentages.
5. Run the golden suite in CI and fail deployment when numerical answers or required citations deviate from expected values.
