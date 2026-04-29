import os
import time
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]
GMAIL_USER = "eliaspao7@gmail.com"
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT = "eliaspao7@gmail.com"

SEARCH_QUERIES = [
    "immunology R&D biotech Netherlands",
    "immunoengineering Netherlands",
    "drug discovery biotech Netherlands",
    "drug design biology Netherlands",
    "PhD immunology Netherlands",
    "PhD biology Netherlands",
    "cell therapy biotech Netherlands",
    "antibody engineering Netherlands",
    "translational medicine Netherlands",
    "biopharmaceutical R&D Netherlands",
]

AMSTERDAM_RADIUS_CITIES = {
    "amsterdam", "utrecht", "leiden", "delft",
    "den haag", "the hague", "haarlem", "almere",
    "amersfoort", "hilversum", "gouda", "zaandam",
    "hoofddorp", "schiphol", "alphen", "woerden",
    "bussum", "naarden",
}

# Words to strip when building a PubMed query from job titles
JOB_TITLE_STOPWORDS = {
    "senior", "junior", "principal", "lead", "associate", "staff", "scientist",
    "engineer", "researcher", "manager", "director", "officer", "specialist",
    "analyst", "postdoc", "postdoctoral", "phd", "intern", "position",
    "and", "or", "the", "in", "at", "for", "of", "a", "an", "with",
    "to", "is", "ii", "iii", "iv", "i", "&",
}


# ---------------------------------------------------------------------------
# Job fetching
# ---------------------------------------------------------------------------

def fetch_jobs(query):
    url = "https://jsearch.p.rapidapi.com/search"
    params = {
        "query": query,
        "page": "1",
        "num_pages": "2",
        "date_posted": "3days",
    }
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as e:
        print(f"Error fetching '{query}': {e}")
        return []


def is_in_radius(job):
    city = (job.get("job_city") or "").lower()
    country = (job.get("job_country") or "").lower()

    if country not in ("netherlands", "nl", "the netherlands"):
        return False

    if not city:
        return True

    return any(c in city for c in AMSTERDAM_RADIUS_CITIES)


# ---------------------------------------------------------------------------
# Paper fetching (Europe PMC — no API key required)
# ---------------------------------------------------------------------------

def build_paper_query(job_title, job_description):
    """Extract biomedical keywords from job title to form a PubMed query."""
    words = job_title.lower().replace("-", " ").replace("/", " ").split()
    keywords = [w for w in words if w not in JOB_TITLE_STOPWORDS and len(w) > 3]

    # Pull any extra domain terms from the first 200 chars of description
    domain_hints = {
        "car-t", "car t", "immunotherapy", "monoclonal", "antibody", "vaccine",
        "cytokine", "t cell", "b cell", "checkpoint", "crispr", "gene therapy",
        "protein engineering", "bispecific", "adc", "mrna",
    }
    desc_lower = (job_description or "")[:200].lower()
    for hint in domain_hints:
        if hint in desc_lower and hint.replace(" ", "") not in " ".join(keywords):
            keywords.append(hint.replace(" ", "_"))

    query = " AND ".join(keywords[:5]) if keywords else job_title
    return query


def fetch_related_papers(job_title, job_description):
    """Return up to 3 relevant papers from Europe PMC."""
    query = build_paper_query(job_title, job_description)
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": 3,
        "sort": "relevance",
        "resultType": "core",
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json().get("resultList", {}).get("result", [])
        papers = []
        for r in results:
            title = (r.get("title") or "").rstrip(".")
            raw_authors = r.get("authorString") or ""
            if len(raw_authors) > 55:
                first = raw_authors.split(",")[0].strip()
                authors = f"{first} et al."
            else:
                authors = raw_authors
            journal = r.get("journalTitle") or ""
            year = r.get("pubYear") or ""
            doi = r.get("doi") or ""
            pmid = r.get("pmid") or ""
            if doi:
                link = f"https://doi.org/{doi}"
            elif pmid:
                link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            else:
                link = ""
            if title:
                papers.append({
                    "title": title,
                    "authors": authors,
                    "journal": journal,
                    "year": year,
                    "link": link,
                })
        return papers
    except Exception as e:
        print(f"  Paper fetch error for '{job_title}': {e}")
        return []


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

def format_salary(job):
    min_s = job.get("job_min_salary")
    max_s = job.get("job_max_salary")
    period = (job.get("job_salary_period") or "").lower()
    currency = job.get("job_salary_currency") or "EUR"

    if min_s and max_s:
        return f"{currency} {int(min_s):,}–{int(max_s):,} / {period}"
    elif min_s:
        return f"{currency} {int(min_s):,}+ / {period}"
    return "Not listed"


def render_papers_html(papers):
    if not papers:
        return ""
    items = []
    for p in papers:
        meta = " &bull; ".join(filter(None, [p["authors"], p["journal"], p["year"]]))
        if p["link"]:
            title_html = f'<a href="{p["link"]}" style="color:#1a1a2e;text-decoration:none;">{p["title"]}</a>'
        else:
            title_html = p["title"]
        items.append(f"""
            <li style="margin-bottom:8px;line-height:1.5;">
                {title_html}
                <br><span style="color:#888;font-size:11px;">{meta}</span>
            </li>
        """)
    return f"""
        <div style="margin-top:14px;padding:12px 16px;background:#eef3fb;border-radius:4px;">
            <p style="margin:0 0 8px;font-size:12px;font-weight:bold;color:#2a7ae2;
                      text-transform:uppercase;letter-spacing:0.5px;">Related Reading</p>
            <ol style="margin:0;padding-left:18px;color:#333;font-size:12px;">
                {"".join(items)}
            </ol>
        </div>
    """


def render_job_card(job, papers):
    title = job.get("job_title") or "Unknown Title"
    company = job.get("employer_name") or "Unknown Company"
    city = job.get("job_city") or ""
    country = job.get("job_country") or "Netherlands"
    location = ", ".join(filter(None, [city, country]))
    posted = (job.get("job_posted_at_datetime_utc") or "")[:10] or "Recent"
    salary = format_salary(job)
    link = job.get("job_apply_link") or job.get("job_google_link") or "#"
    raw_desc = job.get("job_description") or ""
    description = raw_desc[:500].strip()
    if len(raw_desc) > 500:
        description += "…"

    papers_html = render_papers_html(papers)

    return f"""
    <div style="background:#f9f9f9;border-left:4px solid #2a7ae2;padding:18px 22px;
                margin-bottom:28px;border-radius:4px;">
        <h3 style="margin:0 0 4px;color:#1a1a2e;font-size:16px;">{title}</h3>
        <p style="margin:0 0 8px;color:#555;font-size:13px;">
            <strong>{company}</strong> &bull; {location} &bull; Posted: {posted}
        </p>
        <p style="margin:0 0 12px;color:#2a7ae2;font-size:13px;">Salary: {salary}</p>
        <p style="margin:0 0 14px;color:#444;font-size:13px;line-height:1.7;">{description}</p>
        <a href="{link}" style="background:#2a7ae2;color:white;padding:8px 18px;
           text-decoration:none;border-radius:4px;font-size:13px;font-weight:bold;">
           Apply →
        </a>
        {papers_html}
    </div>
    """


def build_html(jobs_with_papers):
    today = datetime.now().strftime("%B %d, %Y")
    count = len(jobs_with_papers)

    if not jobs_with_papers:
        body = "<p style='color:#555;'>No new matching positions found today. Check back tomorrow!</p>"
    else:
        body = "".join(render_job_card(j, p) for j, p in jobs_with_papers)

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:740px;margin:auto;padding:24px;color:#333;">
        <div style="background:#1a1a2e;color:white;padding:22px 24px;border-radius:8px;margin-bottom:28px;">
            <h1 style="margin:0;font-size:22px;">Daily Job Digest</h1>
            <p style="margin:6px 0 0;opacity:0.7;font-size:13px;">
                {today} &bull; Biotech / Immunology / PhD &bull; Amsterdam + surroundings
            </p>
        </div>
        <p style="color:#555;margin-bottom:20px;">
            Found <strong>{count} position(s)</strong> matching your criteria in the last 3 days.
            Each listing includes 3 related papers to help you prepare.
        </p>
        {body}
        <hr style="margin-top:36px;border:none;border-top:1px solid #eee;">
        <p style="font-size:11px;color:#bbb;text-align:center;margin-top:12px;">
            Automated digest &bull; Papers sourced from Europe PMC
        </p>
    </body>
    </html>
    """


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------

def send_email(html, job_count):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"Job Digest: {job_count} biotech/immunology role(s) in NL — "
        f"{datetime.now().strftime('%b %d')}"
    )
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENT, msg.as_string())

    print(f"Email sent: {job_count} job(s).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    seen_ids = set()
    all_jobs = []

    for query in SEARCH_QUERIES:
        print(f"Fetching jobs: {query}")
        for job in fetch_jobs(query):
            job_id = job.get("job_id")
            if job_id and job_id not in seen_ids and is_in_radius(job):
                seen_ids.add(job_id)
                all_jobs.append(job)
        time.sleep(1.5)  # stay within JSearch free-tier rate limit

    all_jobs.sort(
        key=lambda j: j.get("job_posted_at_datetime_utc") or "",
        reverse=True,
    )
    print(f"Unique jobs after filtering: {len(all_jobs)}")

    jobs_with_papers = []
    for job in all_jobs:
        title = job.get("job_title") or ""
        desc = job.get("job_description") or ""
        print(f"  Fetching papers for: {title}")
        papers = fetch_related_papers(title, desc)
        jobs_with_papers.append((job, papers))
        time.sleep(0.3)  # polite delay for Europe PMC

    html = build_html(jobs_with_papers)
    send_email(html, len(all_jobs))


if __name__ == "__main__":
    main()
