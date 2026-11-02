"""Build sample/jobs.csv and sample/jobs.xlsx from local fixtures.

Nothing here contacts a job site. The rows are made up so a reader can see
the columns before running their own search.
"""

from __future__ import annotations

import sys
from pathlib import Path


def sample_rows() -> list[dict]:
    """A mixed set of professions, countries, and experience levels.

    An office job is never labelled Remote. A Remote place is always remote.
    """
    return [
        {
            "is_new": "yes",
            "title": "Registered Nurse",
            "company": "Harbor General Hospital",
            "location": "Amsterdam, Netherlands",
            "date_posted": "2026-10-20",
            "source": "indeed",
            "source_type": "aggregator",
            "url": "https://example.com/jobs/nurse-amsterdam",
            "description": "Ward nursing on a medical unit. Dutch with patients is required.",
            "role_searched": "Nurse",
            "place_searched": "Amsterdam, Netherlands",
            "salary": "3,400–4,100 EUR/month",
            "job_type": "Full-time",
            "is_remote": "No",
            "level": "Unknown",
            "languages": "Dutch",
            "visa": "Unknown",
        },
        {
            "is_new": "yes",
            "title": "Staff Nurse",
            "company": "Harbor General Hospital",
            "location": "Amsterdam, Netherlands",
            "date_posted": "2026-10-18",
            "source": "Harbor General careers",
            "source_type": "company site",
            "url": "https://example.com/jobs/staff-nurse",
            "description": "Experienced ward nurse. Fluent Dutch is required for this team.",
            "role_searched": "Nurse",
            "place_searched": "Amsterdam, Netherlands",
            "salary": "4,200 EUR/month",
            "job_type": "Full-time",
            "is_remote": "No",
            "level": "Senior",
            "languages": "Dutch",
            "visa": "No sponsorship (guessed from the text)",
        },
        {
            "is_new": "no",
            "title": "Warehouse Operative",
            "company": "Vistula Logistics",
            "location": "Warsaw, Poland",
            "date_posted": "2026-10-15",
            "source": "indeed",
            "source_type": "aggregator",
            "url": "https://example.com/jobs/warehouse-warsaw",
            "description": "Pick and pack in a Warsaw warehouse. Day shifts.",
            "role_searched": "Warehouse Worker",
            "place_searched": "Warsaw, Poland",
            "salary": "5,500–6,200 PLN/month",
            "job_type": "Full-time",
            "is_remote": "No",
            "level": "Unknown",
            "languages": "",
            "visa": "Unknown",
        },
        {
            "is_new": "yes",
            "title": "Graduate Marketing Assistant",
            "company": "Plaza Studio",
            "location": "Madrid, Spain",
            "date_posted": "2026-10-21",
            "source": "linkedin",
            "source_type": "aggregator",
            "url": "https://example.com/jobs/marketing-madrid",
            "description": "A first role supporting campaign reporting. Spanish is useful.",
            "role_searched": "Marketing",
            "place_searched": "Madrid, Spain",
            "salary": "24,000 EUR/year",
            "job_type": "Full-time",
            "is_remote": "No",
            "level": "Entry",
            "languages": "Spanish",
            "visa": "Sponsorship offered (guessed from the text)",
        },
        {
            "is_new": "yes",
            "title": "Customer Support Specialist",
            "company": "Kindred Support",
            "location": "Remote - Worldwide",
            "date_posted": "2026-10-19",
            "source": "remote ok",
            "source_type": "remote board",
            "url": "https://example.com/jobs/support-worldwide",
            "description": "Help customers by chat. The role is open worldwide. Fluent English is required.",
            "role_searched": "Customer Support",
            "place_searched": "Remote",
            "salary": "18–22 USD/hour",
            "job_type": "Full-time",
            "is_remote": "Yes",
            "level": "Unknown",
            "languages": "English",
            "visa": "Unknown",
        },
        {
            "is_new": "no",
            "title": "Accountant",
            "company": "Maple Ledger",
            "location": "Toronto, Ontario, Canada",
            "date_posted": "2026-10-12",
            "source": "indeed",
            "source_type": "aggregator",
            "url": "https://example.com/jobs/accountant-toronto",
            "description": "Month-end close for a Toronto office. The role is on site.",
            "role_searched": "Accountant",
            "place_searched": "Toronto, Canada",
            "salary": "65,000–75,000 CAD/year",
            "job_type": "Full-time",
            "is_remote": "No",
            "level": "Unknown",
            "languages": "",
            "visa": "No sponsorship (guessed from the text)",
        },
        {
            "is_new": "yes",
            "title": "Software Engineer",
            "company": "Northwind Labs",
            "location": "Berlin, Germany",
            "date_posted": "2026-10-22",
            "source": "linkedin",
            "source_type": "aggregator",
            "url": "https://example.com/jobs/engineer-berlin",
            "description": "Build web services from the Berlin office.",
            "role_searched": "Software Engineer",
            "place_searched": "Berlin, Germany",
            "salary": "70,000–85,000 EUR/year",
            "job_type": "Full-time",
            "is_remote": "No",
            "level": "Unknown",
            "languages": "",
            "visa": "Unknown",
        },
        {
            "is_new": "yes",
            "title": "Principal Software Engineer",
            "company": "Northwind Labs",
            "location": "Berlin, Germany",
            "date_posted": "2026-10-11",
            "source": "Northwind Labs careers",
            "source_type": "company site",
            "url": "https://example.com/jobs/principal-berlin",
            "description": "Lead a small platform group. The team sits in Berlin.",
            "role_searched": "Software Engineer",
            "place_searched": "Berlin, Germany",
            "salary": "110,000 EUR/year",
            "job_type": "Full-time",
            "is_remote": "No",
            "level": "Senior",
            "languages": "English",
            "visa": "Sponsorship offered (guessed from the text)",
        },
    ]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from save_results import write_outputs

    rows = sample_rows()
    sample = root / "sample"
    sample.mkdir(exist_ok=True)
    places = []
    for row in rows:
        place = row["place_searched"]
        if place not in places:
            places.append(place)
    write_outputs(rows, sample / "jobs.csv", sample / "jobs.xlsx", place_names=places)
    print(f"Wrote {len(rows)} made-up rows to sample/jobs.csv and sample/jobs.xlsx.")


if __name__ == "__main__":
    main()
