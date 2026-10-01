"""Generate realistic enterprise documents in C:\\CompanyData."""
import os
import csv
from pathlib import Path
from docx import Document as DocxDocument
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

ROOT = Path("C:/CompanyData")

def create_pdf(filepath: Path, title: str, sections: list[tuple[str, str]]):
    doc = SimpleDocTemplate(str(filepath), pagesize=letter)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, spaceAfter=14, textColor=colors.HexColor('#1a365d'))
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=13, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor('#2b6cb0'))
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=8)

    story = [Paragraph(title, title_style), Spacer(1, 10)]
    for sec_title, sec_text in sections:
        story.append(Paragraph(sec_title, heading_style))
        for para in sec_text.strip().split("\n\n"):
            story.append(Paragraph(para.replace("\n", " "), body_style))
        story.append(Spacer(1, 6))
    doc.build(story)

def create_docx(filepath: Path, title: str, sections: list[tuple[str, str]]):
    doc = DocxDocument()
    doc.add_heading(title, 0)
    for sec_title, sec_text in sections:
        doc.add_heading(sec_title, level=1)
        for para in sec_text.strip().split("\n\n"):
            doc.add_paragraph(para.replace("\n", " "))
    doc.save(str(filepath))

def create_xlsx(filepath: Path, sheets_data: dict[str, list[list]]):
    wb = Workbook()
    first = True
    for sheet_name, rows in sheets_data.items():
        if first:
            ws = wb.active
            ws.title = sheet_name
            first = False
        else:
            ws = wb.create_sheet(title=sheet_name)
        for row in rows:
            ws.append(row)
    wb.save(str(filepath))

def create_csv(filepath: Path, headers: list[str], rows: list[list]):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def main():
    folders = ["Customers", "Finance", "HR", "Projects", "Contracts"]
    for f in folders:
        (ROOT / f).mkdir(parents=True, exist_ok=True)

    # 1. CUSTOMERS
    cust_dir = ROOT / "Customers"
    create_pdf(
        cust_dir / "acme_corp_account_summary.pdf",
        "Acme Corporation — Key Account Summary 2026",
        [
            ("Account Overview", "Acme Corporation is a Tier-1 Enterprise client with annual recurring revenue (ARR) of $450,000. Contract was renewed on January 15, 2026 for a 3-year term. Primary contact is Sarah Jenkins, VP of Engineering (sarah.jenkins@acme.corp)."),
            ("Service Level Agreement (SLA)", "Target availability is 99.95% uptime. Severity 1 response time SLA is within 15 minutes with 24/7 dedicated support desk. Scheduled maintenance windows occur every second Sunday between 02:00-04:00 UTC."),
            ("Strategic Expansion Roadmap", "Acme plans to onboard 2,500 additional active users in Q3 2026. Custom SSO SAML 2.0 integration and role-based directory sync completed in February 2026. Account manager assigned is David Miller.")
        ]
    )
    create_xlsx(
        cust_dir / "customer_directory_2026.xlsx",
        {
            "Active Customers": [
                ["Customer ID", "Customer Name", "Tier", "ARR ($)", "Contract Start", "Renewal Date", "Account Manager", "Status"],
                ["CUST-001", "Acme Corporation", "Enterprise", 450000, "2026-01-15", "2029-01-14", "David Miller", "Active"],
                ["CUST-002", "Globex Global", "Enterprise", 380000, "2025-06-01", "2027-05-31", "Elena Vance", "Active"],
                ["CUST-003", "Initech Solutions", "Mid-Market", 120000, "2025-11-10", "2026-11-09", "David Miller", "Active"],
                ["CUST-004", "Soylent Healthcare", "Enterprise", 520000, "2026-02-01", "2028-01-31", "Elena Vance", "Active"],
                ["CUST-005", "Umbrella BioTech", "Growth", 85000, "2025-08-15", "2026-08-14", "Marcus Brody", "Active"],
                ["CUST-006", "Hooli Cloud Systems", "Enterprise", 610000, "2026-03-01", "2029-02-28", "Elena Vance", "Active"]
            ]
        }
    )
    create_docx(
        cust_dir / "client_onboarding_process.docx",
        "Standard Client Onboarding Guide",
        [
            ("Phase 1: Kickoff & Requirements (Days 1-5)", "Conduct stakeholder alignment meeting with the client sponsor. Gather architectural requirements, network topology, tenant ID, and security compliance certificates (SOC 2, ISO 27001)."),
            ("Phase 2: Environment Provisioning (Days 6-12)", "Deploy isolated tenant database cluster and configure RBAC roles. Set up dev and staging instances. Verify audit logging and encryption at rest (AES-256)."),
            ("Phase 3: User Acceptance & Go-Live (Days 13-20)", "Perform load testing, conduct admin training workshop, and transition to 24/7 dedicated support team. Sign off on final UAT checklist.")
        ]
    )
    create_csv(
        cust_dir / "support_sla_metrics.csv",
        ["Month", "Tier", "Total Tickets", "Avg First Response (Mins)", "SLA Met %", "CSAT Score"],
        [
            ["2026-01", "Enterprise", "142", "8.5", "99.3%", "4.9/5.0"],
            ["2026-01", "Mid-Market", "88", "24.1", "98.1%", "4.7/5.0"],
            ["2026-02", "Enterprise", "135", "7.9", "99.6%", "4.9/5.0"],
            ["2026-02", "Mid-Market", "94", "22.0", "98.5%", "4.8/5.0"],
            ["2026-03", "Enterprise", "150", "8.1", "99.4%", "4.9/5.0"],
            ["2026-03", "Mid-Market", "82", "21.5", "98.8%", "4.8/5.0"]
        ]
    )

    # 2. FINANCE
    fin_dir = ROOT / "Finance"
    create_xlsx(
        fin_dir / "q1_2026_financial_summary.xlsx",
        {
            "P&L Summary": [
                ["Metric", "Budget Q1 ($)", "Actual Q1 ($)", "Variance ($)", "% Target", "Status"],
                ["Total Revenue", 4200000, 4450000, 250000, "105.9%", "Exceeded"],
                ["Subscription Revenue", 3500000, 3720000, 220000, "106.3%", "Exceeded"],
                ["Professional Services", 700000, 730000, 30000, "104.3%", "Exceeded"],
                ["Cost of Goods Sold (COGS)", 850000, 810000, -40000, "95.3%", "Favorable"],
                ["Gross Profit", 3350000, 3640000, 290000, "108.7%", "Exceeded"],
                ["Operating Expenses (OpEx)", 2100000, 2050000, -50000, "97.6%", "Favorable"],
                ["EBITDA", 1250000, 1590000, 340000, "127.2%", "Outstanding"]
            ],
            "Department Budgets": [
                ["Department", "Allocated ($)", "Spent Q1 ($)", "Remaining ($)", "Headcount"],
                ["Engineering", 1100000, 1060000, 40000, 42],
                ["Sales & Marketing", 750000, 725000, 25000, 26],
                ["Operations", 320000, 310000, 10000, 14],
                ["Finance & Legal", 220000, 215000, 5000, 8],
                ["Human Resources", 180000, 172000, 8000, 6]
            ]
        }
    )
    create_pdf(
        fin_dir / "annual_budget_forecast_2026.pdf",
        "Annual Corporate Budget & Financial Strategy 2026",
        [
            ("Executive Summary", "The 2026 annual financial plan projects total revenue of $18.5M, representing 32% year-over-year growth. Capital expenditure budget is capped at $1.8M primarily targeting cloud infrastructure, SOC 2 Type II audit compliance, and AI platform scaling."),
            ("Cash Flow & Runway", "As of March 1, 2026, total cash and liquid equivalents stand at $6.8M, representing 24 months of runway at current net burn rate of $280,000/month. Break-even operating cash flow is targeted for Q4 2026."),
            ("Fiscal Controls & Delegated Authorities", "Purchases over $10,000 require Department Head and Finance Director approval. Purchases over $50,000 require CEO sign-off. All contracts must include standard 30-day payment terms (Net-30).")
        ]
    )
    create_docx(
        fin_dir / "travel_and_expense_policy.docx",
        "Corporate Travel & Expense Reimbursement Policy 2026",
        [
            ("Policy Overview & Scope", "This policy applies to all full-time employees and contractors traveling on authorized company business. All expenses must be submitted via the expense portal within 30 days of occurrence with itemized receipts."),
            ("Per Diem & Meal Allowances", "Daily domestic meal allowance is $85 per day ($20 breakfast, $25 lunch, $40 dinner). International travel meal allowance is $125 per day. Alcohol expenses must be approved separately by the department manager."),
            ("Lodging & Transportation", "Standard hotel room rates are capped at $220/night in standard cities and $320/night in designated tier-1 high-cost metros (San Francisco, New York, London, Tokyo). Economy airfare is required for all flights under 6 hours."),
            ("Approval Matrix", "Expenses under $500 are auto-approved by direct manager. Expenses between $500 and $5,000 require Department VP approval. Expenses exceeding $5,000 require CFO or CEO approval.")
        ]
    )
    create_csv(
        fin_dir / "vendor_payment_schedule.csv",
        ["Vendor Name", "Category", "Invoice ID", "Amount ($)", "Invoice Date", "Due Date", "Payment Status"],
        [
            ["Amazon Web Services", "Cloud Infrastructure", "INV-2026-0891", "42500.00", "2026-02-28", "2026-03-30", "Scheduled"],
            ["Datadog Inc.", "Monitoring & APM", "INV-DD-4412", "6800.00", "2026-03-01", "2026-03-31", "Approved"],
            ["KPMG LLP", "Audit & Tax Advisory", "INV-KPMG-918", "28000.00", "2026-02-15", "2026-03-17", "Paid"],
            ["GitHub Enterprise", "Developer Tooling", "INV-GH-7712", "12400.00", "2026-01-10", "2026-02-09", "Paid"],
            ["Zoom Video Comm", "Collaboration", "INV-ZM-3301", "3400.00", "2026-03-05", "2026-04-04", "Pending Review"]
        ]
    )

    # 3. HR
    hr_dir = ROOT / "HR"
    create_pdf(
        hr_dir / "employee_handbook_2026.pdf",
        "Nanvi Global Employee Handbook 2026",
        [
            ("Company Mission & Core Values", "Our mission is to empower enterprises with trusted, secure, and delightful AI intelligence. We value: 1. Customer trust above all, 2. Extreme security and data privacy, 3. Radical collaboration, 4. Relentless innovation."),
            ("Working Hours & Hybrid Workplace", "Core collaboration hours are 10:00 AM to 4:00 PM local time. Employees work in a hybrid model: 2 days in office and 3 days remote, with flexible arrangements available upon manager approval."),
            ("Code of Conduct & Anti-Harassment", "We maintain zero tolerance for harassment, discrimination, or retaliation. Any violation can be reported anonymously through the ethics hotline or directly to Kavita Reddy, Head of HR (hr@nanvi.local)."),
            ("Data Protection & Clean Desk Policy", "Employees must lock workstations when leaving desk. Company devices must use full-disk BitLocker encryption and multi-factor authentication (MFA). Confidential documents must not be left unattended.")
        ]
    )
    create_docx(
        hr_dir / "benefits_and_healthcare_plan.docx",
        "Comprehensive Employee Benefits Guide 2026",
        [
            ("Medical, Dental & Vision Coverage", "100% company-paid medical, dental, and vision insurance premiums for employees and 80% coverage for eligible dependents. Plans include BlueCross PPO with $500 annual deductible and comprehensive prescription drug coverage."),
            ("Retirement & 401(k) / EPF Matching", "The company matches 100% of employee 401(k) contributions up to 5% of base salary, with immediate vesting from day one. International employees receive statutory provident fund contributions plus voluntary supplemental pension allowance."),
            ("Wellness & Learning Stipend", "Every employee receives a $1,200 annual wellness stipend ($100/month) applicable to gym memberships, home fitness, or mental health apps. A $2,500 annual professional development budget is available for conferences, certifications, and technical books.")
        ]
    )
    create_docx(
        hr_dir / "leave_and_vacation_policy.docx",
        "Paid Time Off, Sick Leave & Parental Policy",
        [
            ("Paid Time Off (PTO)", "Employees accrue 20 business days of PTO annually (1.67 days per month). Up to 5 unused days can roll over to the next calendar year. PTO requests exceeding 3 consecutive days require 2 weeks advance notice."),
            ("Sick Leave & Mental Health Days", "10 paid sick days per year are provided. Sick leave can also be taken for caring for immediate family members. No doctor note required for absences of 2 days or fewer."),
            ("Parental & Caregiver Leave", "16 weeks of 100% paid parental leave for all new parents (birth, adoption, or foster placement). An additional 4 weeks of phased return-to-work is offered with 80% hours at 100% pay.")
        ]
    )
    create_xlsx(
        hr_dir / "headcount_planning_q2.xlsx",
        {
            "Open Positions Q2": [
                ["Req ID", "Role Title", "Department", "Hiring Manager", "Priority", "Target Start", "Salary Band ($)"],
                ["REQ-101", "Senior AI Systems Engineer", "Engineering", "Rahul Patel", "Critical", "2026-05-01", "175,000 - 210,000"],
                ["REQ-102", "Backend Python Developer", "Engineering", "Rahul Patel", "High", "2026-05-15", "140,000 - 165,000"],
                ["REQ-103", "Enterprise Account Executive", "Sales", "Marcus Brody", "High", "2026-04-15", "130,000 + OTE"],
                ["REQ-104", "Senior Financial Analyst", "Finance", "Priya Sharma", "Medium", "2026-06-01", "115,000 - 135,000"],
                ["REQ-105", "Customer Success Lead", "Operations", "Ankit Singh", "High", "2026-05-01", "110,000 - 130,000"]
            ]
        }
    )

    # 4. PROJECTS
    proj_dir = ROOT / "Projects"
    create_docx(
        proj_dir / "project_phoenix_architecture_plan.docx",
        "Project Phoenix — Enterprise Assistant Architecture 2026",
        [
            ("System Overview & Goals", "Project Phoenix modernizes the core Nanvi assistant architecture into a zero-trust enterprise assistant with strict role-based access control, distributed audit logging, and hybrid vector/keyword document search."),
            ("Security & Boundary Invariants", "AI models never receive raw database credentials, file system paths, or unvetted system prompts. Chunks are strictly filtered against user identity permissions before reranking and LLM context injection."),
            ("Latency & Performance SLAs", "P95 end-to-end chat response time must remain under 1,500ms. Document indexing speed targets 50 pages per second with memory footprint under 512MB per worker process.")
        ]
    )
    create_pdf(
        proj_dir / "mobile_app_redesign_roadmap.pdf",
        "Mobile App 3.0 Redesign Technical Roadmap",
        [
            ("Phase 1: Design System & Core Flutter/React Native", "Implement unified design tokens, dark theme support, and biometric login (FaceID/TouchID). Target completion: April 20, 2026."),
            ("Phase 2: Offline Document Caching & Secure Sync", "Local encrypted SQLite storage for authorized summaries and citation caching. Target completion: May 18, 2026."),
            ("Phase 3: Beta Testing & Enterprise Rollout", "Internal dogfooding with 200 staff, followed by customer pilot with Acme Corp and Soylent Healthcare. Launch target: June 30, 2026.")
        ]
    )
    create_xlsx(
        proj_dir / "engineering_sprint_deliverables.xlsx",
        {
            "Sprint 24 Backlog": [
                ["Issue ID", "Feature / Task", "Assignee", "Story Points", "Status", "Target Release"],
                ["PHX-401", "Gmail connector and IMAP search sync", "Rahul Patel", 8, "In Progress", "v2.4.0"],
                ["PHX-402", "Local CompanyData manual folder scanner", "Dev Team", 5, "Completed", "v2.4.0"],
                ["PHX-403", "Top-5 related files recommendation engine", "Dev Team", 5, "In Progress", "v2.4.0"],
                ["PHX-404", "JWT Dev token role-based login screen", "Frontend Lead", 3, "Completed", "v2.3.9"],
                ["PHX-405", "Audit log SIEM exporter to Splunk/Datadog", "Security Eng", 8, "Backlog", "v2.5.0"]
            ]
        }
    )
    create_csv(
        proj_dir / "infrastructure_migration_milestones.csv",
        ["Milestone ID", "Phase Name", "Target Date", "Status", "Owner", "Impact / Downtime"],
        [
            ["MIG-01", "PostgreSQL 16 Multi-AZ failover cluster", "2026-02-10", "Done", "IT / DevOps", "None (Zero Downtime)"],
            ["MIG-02", "Redis Sentinel HA caching layer", "2026-02-24", "Done", "IT / DevOps", "None"],
            ["MIG-03", "Enterprise folder storage C:\\CompanyData", "2026-03-15", "Done", "Platform Lead", "None"],
            ["MIG-04", "Kubernetes cluster autoscale tier", "2026-04-10", "Planned", "DevOps", "30 mins maintenance"],
            ["MIG-05", "Global CDN & edge security headers", "2026-04-25", "Planned", "Security Team", "None"]
        ]
    )

    # 5. CONTRACTS
    cont_dir = ROOT / "Contracts"
    create_pdf(
        cont_dir / "master_services_agreement_standard.pdf",
        "Master Services Agreement (MSA) — Standard Enterprise Terms",
        [
            ("Section 1: Scope of Licensed Services", "Provider agrees to furnish software-as-a-service (SaaS) AI assistant capabilities pursuant to specific Order Forms. Customer receives a non-exclusive, non-transferable enterprise subscription."),
            ("Section 2: Intellectual Property & Data Ownership", "Customer retains sole and exclusive ownership of all Customer Data, query inputs, uploaded company files, and generated custom reports. Provider shall not use Customer Data to train foundation models without express written consent."),
            ("Section 3: Limitation of Liability & Warranties", "Except for gross negligence or willful misconduct, either party's aggregate liability under this agreement shall not exceed the total fees paid in the twelve (12) months preceding the claim. Standard 99.9% uptime warranty applies.")
        ]
    )
    create_docx(
        cont_dir / "enterprise_license_agreement_apex.docx",
        "Enterprise Software License Agreement — Apex Global Systems",
        [
            ("Parties & Effective Date", "Entered into on February 1, 2026 by and between Nanvi AI Solutions Inc. ('Provider') and Apex Global Systems ('Licensee')."),
            ("Subscription & User Seat Allocations", "Licensee is granted 5,000 Enterprise Tier user licenses. Annual subscription fee is $680,000 payable annually in advance. Overage fees are billed at $12 per active user per month."),
            ("Confidentiality & Security Schedule", "Provider shall maintain SOC 2 Type II certification, conduct annual third-party penetration testing, and provide breach notification within 24 hours of confirmation. Standard California law governs.")
        ]
    )
    create_pdf(
        cont_dir / "mutual_nda_template_v3.pdf",
        "Mutual Non-Disclosure Agreement (Standard Version 3.0)",
        [
            ("Purpose of Disclosure", "The parties wish to explore a potential business relationship concerning AI automation and enterprise software integrations ('Permitted Purpose')."),
            ("Definition of Confidential Information", "Includes all non-public technical, financial, operational, product, customer data, and source code disclosed directly or indirectly in writing or orally."),
            ("Term & Obligations", "The receiving party shall protect Confidential Information with the same degree of care used for its own confidential data (no less than reasonable care) for a duration of five (5) years from disclosure.")
        ]
    )
    create_xlsx(
        cont_dir / "contract_renewal_schedule_2026.xlsx",
        {
            "Upcoming Renewals": [
                ["Contract ID", "Account Name", "Type", "Annual Value ($)", "Renewal Date", "Notice Window (Days)", "Renewal Status"],
                ["CNT-2023-01", "Acme Corporation", "MSA + Order Form", 450000, "2029-01-14", 60, "Renewed (3-Yr)"],
                ["CNT-2024-08", "Apex Global Systems", "Enterprise License", 680000, "2027-01-31", 90, "Active"],
                ["CNT-2024-12", "Globex Global", "MSA", 380000, "2027-05-31", 60, "Active"],
                ["CNT-2025-03", "Initech Solutions", "Subscription", 120000, "2026-11-09", 30, "Upcoming Q4"],
                ["CNT-2025-07", "Hooli Cloud Systems", "Enterprise Tier", 610000, "2029-02-28", 90, "Active"]
            ]
        }
    )

    print("Successfully created all company documents in C:\\CompanyData across Customers, Finance, HR, Projects, Contracts!")

if __name__ == "__main__":
    main()
