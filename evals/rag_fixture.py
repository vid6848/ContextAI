"""A fictional employee handbook, rendered as a PDF, that the RAG eval questions are about."""

import pymupdf

DOCUMENT_NAME = "northwind_handbook.pdf"

SECTIONS = [
    ("1. Working hours", "The standard working week is 37.5 hours, Monday to Friday. Core hours are 10:00 to "
     "15:00. Outside core hours you may start any time between 7:00 and 10:00."),
    ("2. Remote work", "Employees may work remotely up to three days per week. Northwind pays a home-office "
     "budget of €600 once every three years for a desk, chair or monitor."),
    ("3. Annual leave", "Full-time staff receive 28 days of paid annual leave plus public holidays. Up to five "
     "unused days carry over to the next year and must be taken before 31 March."),
    ("4. Sick leave", "If you are ill, notify your manager before 9:30 on the first day. A doctor's note is "
     "required from the fourth consecutive day of absence."),
    ("5. Parental leave", "Primary caregivers receive 20 weeks of fully paid parental leave. Secondary "
     "caregivers receive 6 weeks of fully paid leave, to be taken within the child's first year."),
    ("6. Travel and expenses", "Book economy for flights under six hours; business class requires director "
     "approval. Submit expense claims within 30 days of the purchase, with receipts attached."),
    ("7. Learning budget", "Every employee has a learning budget of €1,500 per year for courses, books and "
     "conferences, plus 5 paid study days."),
    ("8. Equipment and security", "Laptops are replaced every three years. Report a lost or stolen device to "
     "security@northwind.example within 24 hours so it can be wiped remotely."),
    ("9. Probation and notice", "New hires have a probation period of six months, with a notice period of two "
     "weeks. After probation the notice period is one month for both sides."),
    ("10. Gifts and hospitality", "Gifts from suppliers or customers worth more than €50 must be declared to "
     "the compliance team within one week."),
]


def handbook_pdf() -> bytes:
    """Headings in a larger font so the structure-aware chunker splits one passage per section."""
    doc = pymupdf.open()
    page, y = doc.new_page(), 60
    page.insert_text((50, y), "Northwind Labs Employee Handbook", fontsize=20)
    y += 40
    for i, (heading, body) in enumerate(SECTIONS):
        if i and i % 4 == 0:
            page, y = doc.new_page(), 60
        page.insert_text((50, y), heading, fontsize=14)
        y += 26
        unused = page.insert_textbox(pymupdf.Rect(50, y, 545, y + 110), body, fontsize=10)
        y += (110 - unused) + 24
    data = doc.write()
    doc.close()
    return data
