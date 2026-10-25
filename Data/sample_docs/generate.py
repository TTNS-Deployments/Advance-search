"""Generate the Advance Search sample documents (PDF, Word, Excel) in this folder.

    python Data/sample_docs/generate.py

The documents describe a fictional company, Meridian Infra Ltd. They are written so that meaning-based
queries that share no keywords with a document still find it (for example "how many days off do I get" finds
the leave policy, which talks about "annual entitlement" and "leave"). ``queries.yaml`` lists the evaluation
queries. Output is deterministic (fixed document dates), so re-running only changes files whose text changed.

Needs: reportlab, python-docx, openpyxl (all in requirements-dev.txt).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXED = dt.datetime(2026, 4, 1, 9, 0, 0)
COMPANY = "Meridian Infra Ltd"

# ---------------------------------------------------------------------------- content

LEAVE_POLICY = {
    "title": "Leave Policy 2026",
    "subtitle": f"{COMPANY} - Human Resources - Effective 1 April 2026",
    "sections": [
        ("1. Purpose and scope", [
            "This policy explains the paid and unpaid leave available to permanent and fixed-term employees of "
            f"{COMPANY} in India. It applies from 1 April 2026 and replaces all earlier leave circulars. Interns and "
            "contractors are covered by the terms of their own agreements.",
            "Leave is planned with your reporting manager and recorded in the HR portal. Approved leave is never "
            "deducted from salary, and no one is asked to work while on approved leave except in a declared emergency.",
        ]),
        ("2. Annual entitlement", [
            "Every full-time employee receives an annual entitlement of 24 working days of earned leave per leave "
            "year (April to March). The entitlement accrues at two days per completed month of service. Part-time "
            "employees accrue on a pro-rata basis according to their contracted hours.",
            "Employees who complete five years of continuous service receive three additional days of earned leave "
            "each year. After ten years the additional allowance rises to five days.",
            "Earned leave should be requested at least two weeks in advance for absences of three working days or "
            "more. Shorter absences can be requested two working days ahead.",
        ]),
        ("3. Carry forward and encashment", [
            "Up to 12 unused days of earned leave may be carried into the next leave year. Any balance above 12 days "
            "lapses on 31 March unless the Head of HR approves an exception because of business needs.",
            "On resignation or retirement, the unused earned leave balance is paid out at the basic salary rate. "
            "Encashment while in service is allowed once a year for a maximum of 10 days.",
        ]),
        ("4. Public holidays", [
            "The company observes 12 public holidays each calendar year. The list for each office is published in "
            "December for the following year. Employees who work on a public holiday at a manager's request receive "
            "a compensatory day within 60 days.",
        ]),
        ("5. Sick leave", [
            "Employees receive 12 days of paid sick leave per leave year. A medical certificate from a registered "
            "doctor is required for absences longer than two consecutive working days. Unused sick leave does not "
            "carry forward and cannot be paid out.",
            "Long-term illness is handled case by case with HR and may combine sick leave, earned leave and unpaid "
            "medical leave.",
        ]),
        ("6. Parental leave", [
            "Birth mothers receive 26 weeks of paid maternity leave for the first two children and 12 weeks for any "
            "further child. Adoptive and commissioning mothers receive 12 weeks from the date the child is handed over.",
            "Fathers and partners receive 15 working days of paid paternity leave, to be taken within six months of "
            "the birth or adoption. Leave can be split into a maximum of three blocks.",
        ]),
        ("7. Other leave", [
            "Bereavement leave: five working days on the death of an immediate family member. Marriage leave: five "
            "working days, once during employment. Voluntary service leave: two days per year for registered "
            "community work.",
            "Unpaid leave of up to three months may be granted for personal reasons after one year of service, "
            "with the approval of the department head and HR.",
        ]),
    ],
}

TRAVEL_POLICY = {
    "title": "Travel and Expense Policy",
    "subtitle": f"{COMPANY} - Finance - Version 3.2",
    "sections": [
        ("1. Principles", [
            "Business travel must have a clear purpose that cannot be met by a video call. Travellers are expected "
            "to spend company funds as carefully as their own and to choose the lowest reasonable fare.",
            "All travel is booked through the corporate travel desk, which holds negotiated rates with airlines "
            "and hotels. Bookings made elsewhere are reimbursed only when the travel desk could not offer a "
            "comparable option.",
        ]),
        ("2. Air and rail", [
            "Domestic flights are booked in economy class. International flights longer than eight hours may be "
            "booked in premium economy for grade M3 and above. Rail travel uses AC 2-tier or the equivalent.",
            "Flights must be booked at least seven days ahead where possible. Changes caused by personal plans are "
            "paid by the traveller.",
        ]),
        ("3. Hotels", [
            "Hotel limits per night, including taxes: metro cities INR 7,500; other cities INR 5,000; international "
            "travel USD 180. Stays above these limits need the approval of the department head before booking.",
        ]),
        ("4. Daily allowance", [
            "A daily allowance covers meals and local incidentals: INR 1,200 per day in metro cities and INR 900 "
            "elsewhere. When meals are provided by a client or event, the allowance is reduced by half.",
        ]),
        ("5. Submitting claims", [
            "Expense claims are submitted in the finance portal within 30 days of returning. Every item above "
            "INR 500 needs an itemised receipt or invoice. Claims older than 90 days are not reimbursed.",
            "Approved claims are paid with the next salary run if approved by the 20th of the month, otherwise in "
            "the following month. Advances for long assignments can be requested from Finance and are settled "
            "against the final claim.",
        ]),
        ("6. Non-reimbursable items", [
            "The company does not pay for alcohol, traffic fines, personal entertainment, minibar items, loss of "
            "personal belongings, or upgrades chosen for personal comfort.",
        ]),
    ],
}

RETENTION = {
    "title": "Records Retention Schedule",
    "subtitle": f"{COMPANY} - Legal and Compliance - Reviewed March 2026",
    "sections": [
        ("1. Why records are kept", [
            "Records are kept for as long as the law or the business needs them, and no longer. When the period "
            "below ends, the record owner arranges secure disposal: shredding for paper and certified wiping for "
            "electronic media.",
        ]),
        ("2. Finance records", [
            "Invoices, purchase orders, payment vouchers and books of account: eight years from the end of the "
            "financial year to which they relate. Bank statements and reconciliations: eight years. Tax returns "
            "and assessments: ten years.",
        ]),
        ("3. People records", [
            "Personnel files of former employees: seven years after the last working day. Payroll records: eight "
            "years. CVs and interview notes of unsuccessful candidates: six months after the position is filled, "
            "unless the candidate agrees to a longer period.",
        ]),
        ("4. Security and facilities", [
            "CCTV footage from office premises: 30 days, unless it is needed for an investigation, in which case it "
            "is kept until the case is closed. Visitor registers: one year. Access card logs: 180 days.",
        ]),
        ("5. Contracts and legal", [
            "Signed customer and supplier contracts: eight years after expiry. Litigation files: ten years after "
            "the final judgement. Board minutes and statutory registers: permanently.",
        ]),
        ("6. Legal hold", [
            "When Legal issues a hold notice, normal disposal stops for every record named in the notice until "
            "Legal lifts the hold in writing.",
        ]),
    ],
}

TABLET_SPEC = {
    "title": "FT-200 Rugged Field Tablet - Product Specification",
    "subtitle": f"{COMPANY} - Field Equipment - Datasheet rev. B",
    "sections": [
        ("Overview", [
            "The FT-200 is an 8-inch rugged tablet issued to field engineers for meter installation, inspection "
            "and asset surveys. It runs Android 14 with the Meridian Field app preinstalled and is managed through "
            "the company device management service.",
        ]),
        ("Power", [
            "Battery: 10,000 mAh lithium-ion, hot-swappable. Typical runtime is up to 14 hours of mixed use with "
            "GPS and mobile data on, or 9 hours with continuous barcode scanning. A full charge takes about 3 hours "
            "with the supplied 30 W adapter. The vehicle dock charges the tablet while driving.",
        ]),
        ("Display", [
            "8-inch IPS panel, 1920 x 1200 pixels, 800 nits peak brightness for direct sunlight, glove and wet-touch "
            "modes, Gorilla Glass Victus.",
        ]),
        ("Durability", [
            "IP67 ingress protection: dust-tight and protected against immersion in water up to 1 metre for 30 "
            "minutes. Tested to MIL-STD-810H for drops of 1.5 metres onto concrete, vibration and temperature "
            "shock. Operating temperature -20 to 60 degrees Celsius.",
        ]),
        ("Connectivity and sensors", [
            "4G LTE and 5G sub-6 GHz, Wi-Fi 6, Bluetooth 5.3, NFC, dual-band GNSS (GPS, NavIC, Galileo) with 1.5 m "
            "accuracy, 1D/2D barcode scanner, 16 MP rear camera with flash.",
        ]),
        ("Warranty and support", [
            "Three-year comprehensive warranty including accidental damage. Faulty units are replaced by the next "
            "working day in metro cities and within three working days elsewhere. Raise requests through the IT "
            "service desk.",
        ]),
    ],
}

SECURITY_POLICY = {
    "title": "Information Security Policy",
    "subtitle": f"{COMPANY} - IT Security - Version 5.0",
    "sections": [
        ("Purpose", 1, [
            "This policy protects the information that customers, employees and partners trust us with. It applies "
            "to every employee, contractor and third party who uses company systems or data.",
        ]),
        ("Acceptable use", 1, [
            "Company devices and accounts are for business use. Limited personal use is allowed if it does not "
            "affect work, break the law or expose company data. Never install unapproved software or disable the "
            "endpoint protection agent.",
        ]),
        ("Passwords and multi-factor authentication", 1, [
            "Passphrases must be at least 14 characters and must not be reused on other sites. Use the company "
            "password manager to store them.",
            "Multi-factor authentication (MFA) is mandatory for email, VPN and every cloud application. Register "
            "the Microsoft Authenticator app on your phone during your first day; the service desk can issue a "
            "hardware key if you cannot use a phone.",
        ]),
        ("Data classification", 1, [
            "Information is classified as Public, Internal, Confidential or Restricted. Confidential and Restricted "
            "information must be encrypted when stored outside company systems and may only be shared with people "
            "who need it for their work.",
        ]),
        ("Reporting incidents", 1, [
            "Report anything suspicious immediately: phishing e-mails, unexpected password prompts, or unusual "
            "account activity. Use the Report Phishing button in Outlook or call the service desk on extension 4357.",
        ]),
        ("Lost or stolen devices", 2, [
            "If a company device is lost or stolen, inform the IT service desk within one hour, even outside office "
            "hours, so the device can be locked and wiped remotely. Then file a police report and send the report "
            "number to the service desk within 48 hours.",
            "A replacement device is issued once the report is logged. Repeated losses caused by negligence may be "
            "handled under the disciplinary policy.",
        ]),
        ("Working outside the office", 2, [
            "Use the company VPN on public networks, lock your screen when you step away, and do not let family "
            "members use company devices.",
        ]),
        ("Backups", 1, [
            "Store work files in OneDrive or SharePoint, which are backed up daily and kept for 90 days. Files kept "
            "only on a local disk are not backed up and cannot be recovered if the device fails.",
        ]),
    ],
    "table": [["Classification", "Example", "Handling"],
              ["Public", "Press releases", "No restrictions"],
              ["Internal", "Org charts, policies", "Company systems only"],
              ["Confidential", "Customer contracts", "Encrypted, need-to-know"],
              ["Restricted", "Payroll, health data", "Named people only, encrypted, logged"]],
}

ONBOARDING = {
    "title": "New Joiner Onboarding Guide",
    "subtitle": f"Welcome to {COMPANY}",
    "sections": [
        ("Before your first day", 1, [
            "You will receive an e-mail from People Operations with your start time, office address and the name of "
            "your onboarding buddy. Bring a government photo ID, your PAN card and a cancelled cheque for payroll "
            "set-up.",
        ]),
        ("Your first week", 1, []),
        ("Day 1: welcome and set-up", 2, [
            "Arrive at reception at 9:30. People Operations collects your documents and gives you your access card. "
            "The IT service desk hands over your laptop and helps you sign in and register multi-factor "
            "authentication. Lunch is with your team and your buddy.",
        ]),
        ("Days 2 and 3: induction sessions", 2, [
            "Induction sessions introduce the company strategy, our customers, safety rules, the code of conduct "
            "and the information security policy. Each session ends with a short quiz in the learning portal.",
        ]),
        ("Days 4 and 5: meet your team", 2, [
            "Your manager walks you through your role, your goals for the first 90 days and the people you will work "
            "with most. Your buddy shows you the tools your team uses every day.",
        ]),
        ("Mandatory training", 1, [
            "Complete these courses in the learning portal within 30 days: Code of Conduct, Information Security "
            "Essentials, Prevention of Sexual Harassment, and Health and Safety. Field roles also complete Working "
            "at Height and Electrical Safety before any site visit.",
        ]),
        ("Probation", 1, [
            "The probation period is six months. Your manager holds check-ins at 30, 60 and 90 days and a final "
            "review before confirmation. Earned leave can be used during probation once it has accrued.",
        ]),
        ("Who to contact", 1, [
            "People Operations: people@meridian-infra.example. IT service desk: extension 4357. Facilities: "
            "extension 2200. Your buddy is your first contact for anything else.",
        ]),
    ],
}

REMOTE = {
    "title": "Hybrid and Remote Working Guidelines",
    "subtitle": f"{COMPANY} - Human Resources",
    "sections": [
        ("Who can work this way", 1, [
            "Office-based roles follow a hybrid pattern: at least three days a week in the office, agreed with "
            "your manager. Fridays and one more day of your choice can be remote. Field and plant roles are not "
            "eligible because the work is on site.",
        ]),
        ("Setting up your home office", 1, [
            "Employees on the hybrid pattern receive a one-time home office allowance of INR 15,000 for a chair, "
            "desk or monitor. Claim it in the finance portal with the receipts within three months of joining "
            "the hybrid pattern.",
        ]),
        ("Staying connected and secure", 1, [
            "Be reachable on Teams during core hours, 10:00 to 16:00. Use the company VPN, keep your laptop "
            "updated and never print confidential documents at home.",
        ]),
        ("Working from another city", 1, [
            "Remote working from another city for more than two weeks needs approval from your manager and HR, "
            "because of tax and insurance rules. Working from outside India is not allowed.",
        ]),
    ],
}

METER_SPEC = {
    "title": "SM-3 Smart Electricity Meter - Datasheet",
    "subtitle": f"{COMPANY} - Metering Products",
    "sections": [
        ("Overview", 1, [
            "The SM-3 is a single-phase smart electricity meter for homes and small shops. It measures energy in "
            "both directions, so it supports rooftop solar, and it sends readings to the head-end system every 15 "
            "minutes.",
        ]),
        ("Measurement", 1, [
            "Accuracy class 1.0 for active energy (IS 16444). Rated current 5-60 A, 240 V, 50 Hz. Records "
            "voltage, current, power factor and maximum demand.",
        ]),
        ("Communication", 1, [
            "NB-IoT cellular module with automatic fallback to RF mesh. Optical port for local reading. Firmware "
            "can be upgraded over the air.",
        ]),
        ("Tamper protection", 1, [
            "The meter raises an event when the cover is opened, when a strong magnet is placed near it, when the "
            "neutral wire is disconnected or when current flows in reverse unexpectedly. Each event is time-stamped, "
            "stored in memory and sent to the head-end immediately.",
        ]),
        ("Prepaid mode", 1, [
            "In prepaid mode the meter keeps a credit balance, warns the customer by SMS when credit is low and "
            "disconnects the supply through its built-in relay when credit runs out, except on public holidays "
            "and at night.",
        ]),
        ("Environment and warranty", 1, [
            "Operating temperature -10 to 55 degrees Celsius, IP54 enclosure, flame-retardant polycarbonate case. "
            "Warranty: five years from installation.",
        ]),
    ],
}

# ---------------------------------------------------------------------------- writers


def write_pdf(path: Path, doc: dict) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    from reportlab import rl_config

    rl_config.invariant = 1  # fixed dates and IDs, so regenerated files are identical
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10.5, leading=15, spaceAfter=6)
    story = [Paragraph(doc["title"], styles["Title"]), Paragraph(doc["subtitle"], styles["Italic"]), Spacer(1, 8 * mm)]
    for i, (heading, paragraphs) in enumerate(doc["sections"]):
        if i and i % 3 == 0:
            story.append(PageBreak())  # several pages, so passages carry page numbers
        story.append(Paragraph(heading, styles["Heading2"]))
        story.extend(Paragraph(p, body) for p in paragraphs)
    pdf = SimpleDocTemplate(str(path), pagesize=A4, title=doc["title"], author=COMPANY,
                            leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm)
    pdf.build(story)


def write_scanned_pdf(path: Path) -> None:
    """A PDF with drawings only and no text layer: what a scanned page looks like to a text extractor."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle("Scanned delivery note")
    width, height = A4
    c.setFillGray(0.93)
    c.rect(40, 60, width - 80, height - 120, fill=1, stroke=0)
    c.setFillGray(0.55)
    y = height - 120
    for i in range(28):  # grey bars where lines of text would be
        c.rect(70, y, (width - 140) * (0.55 + 0.4 * ((i * 37) % 10) / 10), 7, fill=1, stroke=0)
        y -= 22
    c.showPage()
    c.save()


def write_docx(path: Path, doc: dict) -> None:
    from docx import Document
    from docx.shared import Pt

    d = Document()
    d.core_properties.title = doc["title"]
    d.core_properties.author = COMPANY
    d.core_properties.created = FIXED
    d.core_properties.modified = FIXED
    d.core_properties.last_modified_by = COMPANY
    d.styles["Normal"].font.size = Pt(11)
    d.add_heading(doc["title"], level=0)
    d.add_paragraph(doc["subtitle"])
    for heading, level, paragraphs in doc["sections"]:
        d.add_heading(heading, level=level)
        for p in paragraphs:
            d.add_paragraph(p)
        if heading == "Data classification" and doc.get("table"):
            table = d.add_table(rows=0, cols=len(doc["table"][0]))
            table.style = "Light Grid Accent 1"
            for row in doc["table"]:
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    cell.text = value
    d.save(str(path))


def _workbook():
    from openpyxl import Workbook

    wb = Workbook()
    wb.properties.creator = COMPANY
    wb.properties.created = FIXED
    wb.properties.modified = FIXED
    wb.remove(wb.active)
    return wb


def _sheet(wb, title, header, rows, widths=None, hidden=False):
    from openpyxl.styles import Font, PatternFill

    ws = wb.create_sheet(title)
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F4A8A")
    for row in rows:
        ws.append(row)
    for i, width in enumerate(widths or [], start=1):
        ws.column_dimensions[chr(64 + i)].width = width
    ws.freeze_panes = "A2"
    if hidden:
        ws.sheet_state = "hidden"
    return ws


def write_procurement(path: Path) -> None:
    wb = _workbook()
    _sheet(wb, "Approval limits", ["Spend band (INR)", "Approver", "Quotes required", "Purchase order needed", "Typical lead time"], [
        ["Up to 50,000", "Line manager", "1 quote", "No (corporate card allowed)", "2 days"],
        ["50,001 to 5,00,000", "Department head", "2 written quotes", "Yes", "1 week"],
        ["5,00,001 to 50,00,000", "Chief Financial Officer", "3 written quotes and a comparison sheet", "Yes", "2-3 weeks"],
        ["Above 50,00,000", "Managing Director and the Board purchase committee", "Formal tender", "Yes, with contract", "6-8 weeks"],
        ["Any amount, single source", "Chief Financial Officer", "Single-source justification form", "Yes", "Depends on case"],
        ["Any amount, IT hardware or software", "Head of IT and the budget owner", "Per spend band above", "Yes", "Per spend band above"],
    ], [26, 44, 38, 30, 20])
    _sheet(wb, "Preferred vendors", ["Category", "Vendor", "Contract ends", "Account manager", "Payment terms"], [
        ["Laptops and tablets", "Apex Devices Pvt Ltd", "2027-03-31", "R. Iyer", "45 days"],
        ["Office stationery", "PaperTrail Supplies", "2026-12-31", "S. Menon", "30 days"],
        ["Cleaning services", "SparkleWorks Facility Services", "2027-06-30", "A. Khan", "30 days"],
        ["Travel desk", "Skyline Corporate Travel", "2026-09-30", "P. Das", "15 days"],
        ["Electrical tools", "VoltLine Industrial", "2027-01-31", "M. Joshi", "60 days"],
        ["Cloud services", "Nimbus Cloud India", "2028-03-31", "K. Rao", "30 days"],
    ], [24, 34, 16, 18, 16])
    _sheet(wb, "Internal notes", ["Note"], [["Draft thresholds under review - not for circulation"]], [60], hidden=True)
    wb.save(str(path))


def write_budget(path: Path) -> None:
    wb = _workbook()
    depts = [
        ("Engineering", 42000000, 45000000, 47000000, 51000000),
        ("Field operations", 38000000, 39500000, 41000000, 40500000),
        ("Marketing", 9500000, 11000000, 14500000, 12000000),
        ("Sales", 16000000, 16500000, 17000000, 19000000),
        ("Human resources", 5200000, 5200000, 5600000, 5400000),
        ("Information technology", 12500000, 13000000, 18500000, 12000000),
        ("Finance and legal", 6100000, 6100000, 6300000, 6800000),
        ("Facilities", 7400000, 7200000, 7300000, 7600000),
    ]
    _sheet(wb, "Operating budget", ["Department", "Q1 (INR)", "Q2 (INR)", "Q3 (INR)", "Q4 (INR)", "Full year (INR)", "Budget owner"],
           [[d, a, b, c, e, a + b + c + e, o] for (d, a, b, c, e), o in zip(depts, [
               "VP Engineering", "COO", "Head of Marketing", "Head of Sales", "Head of HR", "CIO", "CFO", "Facilities Manager"])],
           [26, 14, 14, 14, 14, 18, 22])
    _sheet(wb, "Capital projects", ["Project", "Department", "Approved amount (INR)", "Spend to date (INR)", "Expected completion"], [
        ["Smart meter roll-out phase 2", "Field operations", 150000000, 62000000, "2027-02-28"],
        ["Data centre exit and cloud migration", "Information technology", 48000000, 21000000, "2026-11-30"],
        ["Pune office refurbishment", "Facilities", 22000000, 4000000, "2026-10-31"],
        ["Field tablet refresh (FT-200)", "Field operations", 18500000, 18500000, "2026-06-30"],
    ], [38, 24, 22, 20, 20])
    _sheet(wb, "Assumptions", ["Assumption", "Value"], [
        ["Exchange rate used for USD costs", "INR 84 per USD"],
        ["Salary increase from 1 July 2026", "8 percent"],
        ["Contingency held by Finance", "3 percent of operating budget"],
    ], [40, 30])
    wb.save(str(path))


def write_migration_plan(path: Path) -> None:
    wb = _workbook()
    d = dt.date
    _sheet(wb, "Milestones", ["Phase", "Milestone", "Owner", "Start", "End", "Status"], [
        ["1. Discovery", "Application inventory and dependency mapping complete", "Cloud architect", d(2026, 4, 6), d(2026, 5, 15), "Done"],
        ["2. Landing zone", "Network, identity and security baseline built in the cloud tenant", "Platform team", d(2026, 5, 18), d(2026, 6, 26), "Done"],
        ["3. Pilot", "Three low-risk applications moved and validated", "Migration lead", d(2026, 6, 29), d(2026, 7, 31), "Done"],
        ["4. Waves 1-3", "Remaining 42 applications moved in three waves", "Migration lead", d(2026, 8, 3), d(2026, 10, 9), "In progress"],
        ["5. Production cutover", "Customer billing and meter data platforms switched to the cloud (go-live weekend)", "Programme manager", d(2026, 10, 17), d(2026, 10, 18), "Planned"],
        ["6. Hypercare", "Two weeks of extended support after cutover", "Service desk", d(2026, 10, 19), d(2026, 10, 30), "Planned"],
        ["7. Data centre exit", "Old servers wiped and returned; colocation contract ends", "Infrastructure manager", d(2026, 11, 2), d(2026, 11, 30), "Planned"],
    ], [20, 64, 22, 12, 12, 12])
    _sheet(wb, "Risks", ["Risk", "Likelihood", "Impact", "Mitigation", "Owner"], [
        ["Billing system performs worse after the move", "Medium", "High", "Load test at 2x peak before cutover; keep rollback plan for 72 hours", "Programme manager"],
        ["Key engineers unavailable during the cutover weekend", "Low", "High", "Named back-ups for every runbook step; leave freeze from 10 to 25 October", "Migration lead"],
        ["Data transfer over the network takes longer than planned", "Medium", "Medium", "Seed bulk data with offline transfer devices two weeks before", "Infrastructure manager"],
        ["Cloud costs exceed the approved budget", "Medium", "Medium", "Monthly cost review; reserved instances for steady workloads", "Finance business partner"],
        ["Security gaps in the new environment", "Low", "High", "Penetration test after wave 1 and before cutover", "Security officer"],
    ], [48, 12, 10, 64, 24])
    _sheet(wb, "Contacts", ["Role", "Name", "Extension"], [
        ["Programme manager", "Divya Nair", "5101"],
        ["Migration lead", "Arjun Mehta", "5102"],
        ["Cloud architect", "Farah Siddiqui", "5103"],
    ], [24, 20, 12])
    wb.save(str(path))


def write_price_list(path: Path) -> None:
    wb = _workbook()
    _sheet(wb, "Stationery", ["Item", "Item code", "Unit", "Unit price (INR)", "Minimum order"], [
        ["A4 copier paper, 75 gsm", "ST-1001", "Box of 5 reams", 1450, 2],
        ["A3 copier paper, 80 gsm", "ST-1002", "Ream of 500 sheets", 690, 1],
        ["Ballpoint pens, blue", "ST-1010", "Pack of 50", 400, 1],
        ["Whiteboard markers, assorted", "ST-1015", "Pack of 4", 180, 5],
        ["Spiral notebooks, A5", "ST-1020", "Pack of 10", 550, 1],
        ["Toner cartridge, office printer", "ST-1030", "Each", 4200, 1],
    ], [34, 12, 22, 16, 14])
    _sheet(wb, "Field equipment", ["Item", "Item code", "Unit", "Unit price (INR)", "Minimum order"], [
        ["Insulated screwdriver set", "FE-2001", "Set of 7", 2150, 5],
        ["Digital clamp meter", "FE-2010", "Each", 6800, 2],
        ["Safety helmet with chin strap", "FE-2020", "Each", 520, 20],
        ["High-visibility jacket", "FE-2021", "Each", 340, 20],
        ["Spare battery for FT-200 tablet", "FE-2030", "Each", 3900, 10],
    ], [34, 12, 16, 16, 14])
    wb.save(str(path))


def main() -> None:
    write_pdf(HERE / "Leave-Policy-2026.pdf", LEAVE_POLICY)
    write_pdf(HERE / "Travel-and-Expense-Policy.pdf", TRAVEL_POLICY)
    write_pdf(HERE / "Records-Retention-Schedule.pdf", RETENTION)
    write_pdf(HERE / "FT-200-Field-Tablet-Specification.pdf", TABLET_SPEC)
    write_scanned_pdf(HERE / "Scanned-Delivery-Note.pdf")
    write_docx(HERE / "Information-Security-Policy.docx", SECURITY_POLICY)
    write_docx(HERE / "New-Joiner-Onboarding-Guide.docx", ONBOARDING)
    write_docx(HERE / "Hybrid-Working-Guidelines.docx", REMOTE)
    write_docx(HERE / "SM-3-Smart-Meter-Datasheet.docx", METER_SPEC)
    write_procurement(HERE / "Procurement-Approval-Matrix.xlsx")
    write_budget(HERE / "FY2026-Budget-Summary.xlsx")
    write_migration_plan(HERE / "Cloud-Migration-Project-Plan.xlsx")
    write_price_list(HERE / "Supplier-Price-List-2026.xlsx")
    print(f"Wrote sample documents to {HERE}")


if __name__ == "__main__":
    main()
