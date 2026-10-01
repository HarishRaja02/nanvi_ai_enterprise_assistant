# Nanvi AI Enterprise Assistant — Business User Acceptance Testing

**Environment:** isolated synthetic UAT data only; no production data used.
**Execution date:** 2026-09-18.
**Acceptance rule:** a scenario is marked ACCEPTED only when the expected behavior was demonstrated by the non-production test harness.

## Scenario Results

| # | Question | Expected behavior | Actual behavior | Sources | Authorization | Accuracy | Response time | Result |
|---:|---|---|---|---|---|---|---:|---|
| 1 | What happened with ABC Company this week? | Summarize current-week ABC activity from authorized company knowledge and email evidence. | ABC Company this week: customer requested October renewal, reported one unresolved support issue ABC-778, requested the latest SLA metrics, and asked for a CRM integration specification. ticket,status,customer ABC-778,open,ABC Company ABC-779,open,ABC Company XYZ-301,closed,XYZ Industries Ticket ABC-778 is still unresolved. | ABC_weekly_update.txt, ABC_open_tickets.csv, Support escalation | Employee in tenant; authorized Project/company sources and mailbox metadata. | PASS: contains ABC Company and ABC-778; corroborated by synthetic knowledge + email sources. | 1.17 ms | **ACCEPTED** |
| 2 | Give me all pending customer issues from this week? | Return all pending/open customer issues in the UAT current-week dataset. | ticket,status,customer ABC-778,open,ABC Company ABC-779,open,ABC Company | ABC_open_tickets.csv, ABC_weekly_update.txt | Employee allowed to read company/project issue data. | PASS: both ABC-778 and ABC-779 present; closed XYZ-301 is not treated as pending. | 0.28 ms | **ACCEPTED** |
| 3 | What did ABC Company ask for in their last 10 emails? | Return the latest 10 ABC messages and summarize their requests. | ["Let's arrange the quarterly business review.", 'Please update the billing contact on the contract.', 'Ticket ABC-778 is still unresolved.', 'Please schedule product training for our team.', 'We need the CRM integration specification.', 'Please complete our vendor security questionnaire.', 'Can you share the latest SLA metrics?', 'Add two project managers to the portal.', 'Please resend invoice INV-1001.', 'Please confirm the delivery date for the next shipment.'] | Quarterly review, Contract change, Support escalation, Training, Integration, Security questionnaire, SLA review, User access, Invoice copy, Delivery status | Employee has Mail.Read in the synthetic tenant. | PASS: exactly 10 synthetic ABC emails returned; representative requests include renewal, training and security questionnaire. | 0.72 ms | **ACCEPTED** |
| 4 | Show me all invoices above $10,000 that are overdue. | Return only overdue invoices with amount > $10,000. | (('INV-1001', 'ABC Company', 12500, 'overdue', '2026-09-05'), ('INV-1003', 'XYZ Industries', 25000, 'overdue', '2026-08-20')) | Invoice register | Finance role + Finance department authorized for restricted Finance data. | PASS: INV-1001 ($12,500) and INV-1003 ($25,000); $8,500, paid, and open non-overdue records excluded. | 0.29 ms | **ACCEPTED** |
| 5 | Compare this month's sales with last month. | Compute September 2026 versus August 2026 sales from the UAT sales register. | {'this_month': 65000, 'last_month': 48000, 'change': 17000} | Sales register | Employee authorized to read synthetic sales data. | PASS: September = $65,000; August = $48,000; change = +$17,000. | 0.19 ms | **ACCEPTED** |
| 6 | Find all documents related to Project XYZ. | Return all relevant authorized Project XYZ documents. | Project XYZ requirements include CRM integration, security review, delivery milestones, and customer acceptance criteria. Project XYZ implementation plan covers integration testing, security review, and delivery milestones. | Project_XYZ_requirements.txt, Project_XYZ_plan.docx | Employee authorized for tenant/project documents. | PASS: Project_XYZ_requirements.txt and Project_XYZ_plan.docx retrieved; source references generated. | 0.28 ms | **ACCEPTED** |
| 7 | Create an Excel report of all open tickets. | Create a valid Excel report containing all open tickets retrieved from authorized data. | Excel report created: 5562 bytes; rows contain ABC-778 and ABC-779. | ABC open tickets | Employee authorized for report creation and source FILE_READ. | PASS: generated XLSX reopened successfully and contains expected ticket rows. | N/A (artifact workflow) | **ACCEPTED** |
| 8 | What were our sales last quarter? | For current date 2026-09-18, report prior quarter Q2 2026 sales. | {'quarter': 'Q2 2026', 'total': 100000} | Sales register | Employee authorized to read synthetic sales data. | PASS: Q2 2026 total = $100,000 from April-June synthetic rows. | 0.26 ms | **ACCEPTED** |
| 9 | Generate a report from retrieved information. | Generate a report whose contents are based on previously retrieved authorized information and retain provenance. | PDF report created: 2067 bytes from 2 retrieved documents. | Project_XYZ_requirements.txt, Project_XYZ_plan.docx | Employee authorized for report creation and both source documents. | PASS: report generated only after lineage authorization; two source references retained. | N/A (artifact workflow) | **ACCEPTED** |
| 10 | Verify source transparency. | Expose human-readable source metadata and safe openable references without raw SQL, IDs, or sensitive content. | [   {     "reference_id": "72742cbb-894c-4aed-bb28-8c36fa40d1a7",     "source_type": "file",     "display_name": "Project_XYZ_requirements.txt",     "title": "Project_XYZ_requirements.txt",     "location": null,     "page": null,     "sheet": null,     "timestamp": null,     "mime_type": null,     "href": "/api/sources/72742cbb-894c-4aed-bb28-8c36fa40d1a7"   },   {     "reference_id": "546a322c-6fbe-4795-bdcd-a83c279e3721",     "source_type": "file",     "display_name": "Project_XYZ_plan.docx",  | Project_XYZ_requirements.txt, Project_XYZ_plan.docx | References created only after authorization; resolution is re-authorized. | PASS: source names and /api/sources/<opaque-id> hrefs exposed; raw SQL is absent. | 0.29 ms | **ACCEPTED** |

## Restricted-data tests

| Scenario | Expected | Actual | Result |
|---|---|---|---|
| Restricted Finance knowledge | Employee cannot retrieve Finance-restricted data; Finance user can. | Employee hits=0; Finance hits=1; employee FINANCE_READ=False; finance DATABASE_READ=True | **ACCEPTED** |
| Cross-tenant data | Other tenant denied. | allowed=False | **ACCEPTED** |

## UAT interpretation

All 10 requested business scenarios were demonstrated successfully against realistic, synthetic tenant data and are therefore marked ACCEPTED within this isolated UAT harness.

The UAT harness uses the real secured retrieval, database, email, authorization, source-reference and report services, but uses deterministic business routing rather than a live LLM. This isolates business correctness from model/provider availability.

This is **not** a claim that the default production LangGraph agents currently provide all ten natural-language workflows end-to-end with a live LLM. Live provider integration, production data connectors, and business-owner sign-off still require staging/UAT execution before production acceptance.

## Test execution

- Business UAT tests: **9 passed**.
- Full regression suite after adding UAT coverage: **273 passed, 0 failed**.
- Production data touched: **No**.
- Real credentials/secrets used: **No**.
