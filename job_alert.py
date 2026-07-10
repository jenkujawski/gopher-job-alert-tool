"""
STEP 4: Send an email when matching new jobs are found.

This combines everything from before (FETCH -> COMPARE -> FILTER) and
adds the final piece: NOTIFY. If any new jobs pass the keyword filter,
send an email listing them.

Credentials live in config.py, imported below -- never hardcoded here.
"""

import requests
import json
import os
import re
import smtplib
import schedule
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, NOTIFY_EMAIL

SEEN_JOBS_FILE = "seen_jobs.json"

# Add companies here. 'ats' tells the script which fetch function to use.
# For Greenhouse: find the slug in the URL job-boards.greenhouse.io/[slug]
# For Lever: find the slug in the URL jobs.lever.co/[slug]
COMPANIES = [
    {"name": "Honeycomb", "slug": "honeycomb", "ats": "greenhouse"},
    {"name": "HappyCo", "slug": "happyco", "ats": "lever"},
    {"name": "Common Future", "slug": "commonfuture", "ats": "lever"},
    {"name": "Mews", "slug": "mewssystems", "ats": "greenhouse"},
    {"name": "Headspace", "slug": "hs", "ats": "greenhouse"},
    {"name": "Instacart", "slug": "instacart", "ats": "greenhouse"},
    {"name": "Carrot Fertility", "slug": "carrotfertility", "ats": "greenhouse"},
    {"name": "Signifyd", "slug": "signifyd95", "ats": "greenhouse"},
    {"name": "Circle.so", "slug": "circleso", "ats": "greenhouse"},
    {"name": "Nourish", "slug": "usenourish", "ats": "greenhouse"},
    {"name": "Edmentum", "slug": "edmentum", "ats": "greenhouse"},
    {"name": "Blackthorn", "slug": "blackthorn", "ats": "greenhouse"},
    {"name": "CreativeX", "slug": "creativex", "ats": "greenhouse"},
    {"name": "Renaissance Learning", "slug": "renaissancelearning-nam", "ats": "greenhouse"},
    # Ashby companies
    {"name": "Tremendous", "slug": "tremendous", "ats": "ashby"},
    {"name": "DuckDuckGo", "slug": "duck-duck-go", "ats": "ashby"},
    {"name": "Virta Health", "slug": "virtahealth", "ats": "ashby"},
    {"name": "Headway", "slug": "headway", "ats": "ashby"},
    {"name": "Hims & Hers", "slug": "hims-and-hers", "ats": "ashby"},
    # Chainlink Labs removed -- their public page works but their API
    # access is disabled, so it can't be reached this way (confirmed
    # via direct test, not a slug issue).
    {"name": "Smalls", "slug": "smalls", "ats": "ashby"},
    # Oyster's slug wasn't confirmed in the original research -- if this
    # one prints a warning/error when you run the script, that's why.
    # We can look up the correct slug together if it fails.
    {"name": "Oyster", "slug": "oyster", "ats": "ashby"},

    # --- Expansion batch: prioritized by remote-work reputation and
    # data/analyst-relevant sectors, not just volume ---

    # High confidence: verified ATS + strong remote/benefits reputation
    {"name": "Databricks", "slug": "databricks", "ats": "greenhouse"},
    {"name": "Confluent", "slug": "confluent", "ats": "ashby"},
    {"name": "FullStory", "slug": "fullstory", "ats": "ashby"},
    {"name": "Monte Carlo", "slug": "montecarlodata", "ats": "ashby"},
    {"name": "Stripe", "slug": "stripe", "ats": "greenhouse"},
    {"name": "Coinbase", "slug": "coinbase", "ats": "greenhouse"},
    {"name": "Marqeta", "slug": "marqeta", "ats": "ashby"},
    {"name": "Ramp", "slug": "ramp", "ats": "ashby"},
    {"name": "Anthropic", "slug": "anthropic", "ats": "greenhouse"},
    {"name": "OpenAI", "slug": "openai", "ats": "ashby"},
    {"name": "Snowflake", "slug": "snowflake", "ats": "ashby"},
    {"name": "Modern Treasury", "slug": "moderntreasury", "ats": "ashby"},
    {"name": "Linear", "slug": "linear", "ats": "ashby"},
    {"name": "Notion", "slug": "notion", "ats": "ashby"},
    {"name": "Loom", "slug": "loom", "ats": "ashby"},
    {"name": "Deel", "slug": "deel", "ats": "ashby"},
    {"name": "HackerOne", "slug": "hackerone", "ats": "ashby"},
    {"name": "Multiverse", "slug": "multiverse", "ats": "ashby"},
    {"name": "Aurora Solar", "slug": "aurorasolar", "ats": "ashby"},
    {"name": "Boomi", "slug": "boomi", "ats": "ashby"},
    {"name": "NETGEAR", "slug": "netgear", "ats": "ashby"},
    {"name": "Alan", "slug": "alan", "ats": "ashby"},
    {"name": "Clay", "slug": "claylabs", "ats": "ashby"},
    {"name": "Cloudflare", "slug": "cloudflare", "ats": "greenhouse"},

    # Worth trying: strong remote-culture reputation, slug is a best
    # guess -- if these throw a "couldn't fetch" warning, that's why.
    {"name": "GitLab", "slug": "gitlab", "ats": "greenhouse"},
    {"name": "Grafana Labs", "slug": "grafanalabs", "ats": "greenhouse"},
    {"name": "Supabase", "slug": "supabase", "ats": "ashby"},
    {"name": "Elastic", "slug": "elastic", "ats": "greenhouse"},
    {"name": "Articulate", "slug": "articulate", "ats": "lever"},
]

KEYWORDS = [
    "analyst",
    "data",
    "operations",
    "business intelligence",
    "bi",
    "reporting",
    "insights",
]

# ---------------------------------------------------------------------
# HARD FILTERS -- a job failing ANY of these gets thrown out completely,
# no matter how well it scores otherwise. These are your "required" and
# "dealbreaker" criteria: things reliable enough to detect in text that
# you'd never want to see regardless of anything else about the listing.
# ---------------------------------------------------------------------

MIN_SALARY = 75000
MAX_LISTING_AGE_DAYS = 30

# Simple phrase matches -- if any of these appear anywhere in the title
# or description, the job is rejected outright. Kept as plain phrases
# (not word-boundary-checked) since these are specific enough strings
# that false positives are unlikely.
DEALBREAKER_PHRASES = [
    "fast-paced",
    "salary to be determined",
    "answering phone calls",
    "video submission",
    "submit a video",
    "homework assignment",
    "not financially motivated",
    "willing to go the extra mile",
    "one-way video interview",
    "asynchronous video interview",
    "personality assessment",
    "personality test",
    "commission-based",
    "commission structure",
]

# Word-boundary phrases -- same idea, but these are short/common enough
# words that we only want a match when they appear as their own word
# (e.g. "on-call" as a standalone term, not buried inside another word).
DEALBREAKER_WORDS = [
    "on-call",
    "oncall",
]

CUSTOMER_SERVICE_TITLE_PHRASES = [
    "customer service",
    "call center",
    "customer support representative",
]


def contains_phrase(text, phrase):
    return phrase.lower() in text.lower()


def contains_word(text, word):
    pattern = r"\b" + re.escape(word) + r"\b"
    return re.search(pattern, text.lower()) is not None


def extract_salary_range(text):
    """
    Looks for dollar amounts in the text and returns (min, max) as plain
    numbers, or None if nothing salary-shaped is found. Handles common
    formats: "$75,000 - $95,000", "$75K - $95K", "$75,000".

    Deliberately strict about what counts as a match: only numbers that
    are either comma-formatted (75,000) or have a K suffix (75K) are
    treated as salary. A bare number like "$215" with no comma and no K
    is almost never a real salary figure in a job posting -- it's more
    likely a stray dollar amount (a fee, a small stipend, a typo), so we
    skip those rather than risk badly misreading a listing's actual pay.

    This is still a best-effort text search, not a guarantee -- job
    descriptions phrase salary in a lot of different ways, so this will
    miss some and shouldn't be treated as perfectly reliable.
    """
    pattern = r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s?[kK])\b"

    scaled_numbers = []
    for match in re.finditer(pattern, text):
        raw = match.group(0)
        raw_number = match.group(1)
        num = float(raw_number.replace(",", "").rstrip("kK ").strip())
        if "k" in raw.lower():
            num *= 1000
        scaled_numbers.append(num)

    if not scaled_numbers:
        return None

    return min(scaled_numbers), max(scaled_numbers)


def extract_pto_weeks(text):
    """
    Looks for phrasing like "3 weeks PTO" or "4 weeks of paid time off"
    and returns the number as a float, or None if nothing matches.
    """
    pattern = r"(\d+(?:\.\d+)?)\s*weeks?\s*(?:of\s*)?(?:pto|paid time off|vacation)"
    match = re.search(pattern, text.lower())
    if match:
        return float(match.group(1))
    return None


def get_remote_status(job):
    """
    Returns 'remote', 'hybrid', 'onsite', or 'unknown'.

    Lever and Ashby tell us this directly via workplace_type. Greenhouse
    doesn't expose a structured field for it, so for Greenhouse jobs we
    fall back to scanning the title + description text -- less reliable,
    flagged as 'unknown' if we can't tell either way rather than
    guessing wrong in either direction.
    """
    workplace_type = (job.get("workplace_type") or "").lower()
    if "remote" in workplace_type:
        return "remote"
    if "hybrid" in workplace_type:
        return "hybrid"
    if "onsite" in workplace_type or "on-site" in workplace_type:
        return "onsite"

    # Fallback: text search (mainly for Greenhouse, which has no
    # structured field).
    combined_text = (job["title"] + " " + job.get("description", "")).lower()
    has_remote_word = contains_word(combined_text, "remote")
    has_hybrid_word = contains_word(combined_text, "hybrid")
    has_onsite_phrase = ("on-site" in combined_text) or ("on site" in combined_text) or ("in office" in combined_text) or ("in-office" in combined_text)

    if has_hybrid_word or has_onsite_phrase:
        return "hybrid" if has_hybrid_word else "onsite"
    if has_remote_word:
        return "remote"
    return "unknown"


def passes_hard_filters(job):
    """
    Checks a job against every required/dealbreaker rule. Returns
    (True, None) if it passes everything, or (False, reason) for the
    FIRST rule it fails -- we stop at the first failure since one
    dealbreaker is enough to reject the job regardless of the rest.
    """
    title = job["title"]
    description = job.get("description", "")
    combined_text = title + " " + description

    # -- Listing age --
    if job.get("posted_date"):
        try:
            posted = datetime.fromisoformat(job["posted_date"].replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - posted).days
            if age_days > MAX_LISTING_AGE_DAYS:
                return False, f"listing is {age_days} days old (over {MAX_LISTING_AGE_DAYS})"
        except (ValueError, TypeError):
            pass  # if the date doesn't parse cleanly, don't reject over it

    # -- Remote status --
    remote_status = get_remote_status(job)
    if remote_status in ("hybrid", "onsite"):
        return False, f"not fully remote ({remote_status})"

    # -- Salary --
    # Evasive language about pay is treated as a real dealbreaker -- a
    # company choosing vague wording is a different signal than a
    # company that simply didn't include a number in this posting.
    salary_text_sources = combined_text + " " + (job.get("compensation_text") or "")
    if contains_phrase(salary_text_sources, "competitive salary"):
        return False, "says 'competitive salary' instead of a number"

    # If a number IS stated, it still has to clear your minimum. If no
    # number is found at all, we let it through rather than reject --
    # plenty of good companies simply don't state pay in every posting,
    # and rejecting all of them risked losing good companies along with
    # bad ones. (A salary bonus still applies during scoring below if a
    # strong number is found.)
    salary_range = extract_salary_range(salary_text_sources)
    if salary_range is not None:
        salary_min, salary_max = salary_range
        if salary_max < MIN_SALARY:
            return False, f"salary tops out at ${salary_max:,.0f}, below your ${MIN_SALARY:,} minimum"

    # -- Dealbreaker phrases --
    for phrase in DEALBREAKER_PHRASES:
        if contains_phrase(combined_text, phrase):
            return False, f"contains dealbreaker phrase: '{phrase}'"

    for word in DEALBREAKER_WORDS:
        if contains_word(combined_text, word):
            return False, f"contains dealbreaker: '{word}'"

    # -- Customer service focus (checked against title only, since a
    # description mentioning "customer service" once among many other
    # duties isn't the same as the role BEING customer service) --
    title_lower = title.lower()
    for phrase in CUSTOMER_SERVICE_TITLE_PHRASES:
        if phrase in title_lower:
            return False, f"title suggests a customer service role: '{phrase}'"

    return True, None


# ---------------------------------------------------------------------
# SCORING -- for jobs that pass the hard filters above, add up points
# for nice-to-haves and subtract points for red flags. This is a
# starting point, not a precise science -- the score is meant to help
# you triage at a glance, not replace actually reading the listing.
# ---------------------------------------------------------------------

POSITIVE_CRITERIA = [
    # (phrase-or-word, points, "word" or "phrase")
    ("4-day workweek", 3, "phrase"),
    ("four-day workweek", 3, "phrase"),
    ("4 day work week", 3, "phrase"),
    ("401k match", 1, "phrase"),
    ("401(k) match", 1, "phrase"),
    ("mental health", 1, "phrase"),
    ("therapy", 1, "phrase"),
]

RED_FLAG_CRITERIA = [
    ("minimal guidance", -1, "phrase"),
    ("we're a family", -2, "phrase"),
    ("like a family", -2, "phrase"),
    ("work hard, play hard", -1, "phrase"),
    ("wear many hats", -1, "phrase"),
    ("sense of urgency", -1, "phrase"),
    ("self-starter", -1, "word"),
    ("other duties as assigned", -1, "phrase"),
    ("team player", -1, "phrase"),
    ("can hit the ground running", -1, "phrase"),
    ("rockstar", -1, "word"),
    ("ninja", -1, "word"),
    ("unlimited pto", -1, "phrase"),
]


def score_job(job):
    """
    Returns (score, reasons) where reasons is a list of short strings
    explaining what added or subtracted points -- shown in the email so
    you can see WHY a job scored the way it did, not just the number.
    """
    combined_text = job["title"] + " " + job.get("description", "")
    score = 0
    reasons = []

    for phrase_or_word, points, match_type in POSITIVE_CRITERIA:
        matched = contains_word(combined_text, phrase_or_word) if match_type == "word" else contains_phrase(combined_text, phrase_or_word)
        if matched:
            score += points
            reasons.append(f"+{points}: {phrase_or_word}")

    for phrase_or_word, points, match_type in RED_FLAG_CRITERIA:
        matched = contains_word(combined_text, phrase_or_word) if match_type == "word" else contains_phrase(combined_text, phrase_or_word)
        if matched:
            score += points
            reasons.append(f"{points}: {phrase_or_word}")

    salary_range = extract_salary_range(combined_text + " " + (job.get("compensation_text") or ""))
    if salary_range and salary_range[1] >= 90000:
        score += 3
        reasons.append(f"+3: salary up to ${salary_range[1]:,.0f}")

    pto_weeks = extract_pto_weeks(combined_text)
    if pto_weeks and pto_weeks >= 3.5:
        score += 2
        reasons.append(f"+2: {pto_weeks} weeks PTO mentioned")

    return score, reasons


def fetch_greenhouse_jobs(company_slug):
    """
    ?content=true tells Greenhouse to include the full job description
    text in this same request -- no separate request per job needed.
    Greenhouse doesn't give us a clean structured "remote" field the way
    Lever and Ashby do, so remote status here gets figured out later by
    scanning the description text itself.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data["jobs"]:
        # "content" is HTML -- strip tags down to plain text for keyword
        # searching later.
        description_html = job.get("content") or ""
        description_text = BeautifulSoup(description_html, "html.parser").get_text(" ")

        jobs.append({
            "title": job["title"],
            "url": job["absolute_url"],
            "description": description_text,
            "posted_date": job.get("updated_at"),  # ISO date string
            "workplace_type": None,  # Greenhouse doesn't expose this directly
        })
    return jobs


def fetch_lever_jobs(company_slug):
    """
    Lever gives us workplaceType directly ('remote', 'hybrid', 'on-site',
    or 'unspecified') -- a real field the company sets, not something we
    have to guess from text. Much more reliable than scanning words.
    """
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data:
        # createdAt is milliseconds since 1970 -- convert to an ISO date
        # string so it's handled the same way as the other two platforms.
        created_at_ms = job.get("createdAt")
        posted_date = None
        if created_at_ms:
            posted_date = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc).isoformat()

        jobs.append({
            "title": job["text"],
            "url": job["hostedUrl"],
            "description": job.get("descriptionPlain") or "",
            "posted_date": posted_date,
            "workplace_type": job.get("workplaceType"),  # 'remote' / 'hybrid' / 'on-site' / 'unspecified'
        })
    return jobs


def fetch_ashby_jobs(company_slug):
    """
    Ashby's public API. Note: this is a different endpoint than the one
    mentioned in the original planning doc (jobs.ashbyhq.com/.../feed) --
    that one is outdated. The correct, currently-working endpoint is
    api.ashbyhq.com/posting-api/job-board/[slug].

    includeCompensation=true adds a compensation summary string when the
    company has entered one (e.g. "$81K - $87K") -- not every company
    fills this in, but when they do, it saves us from guessing.
    """
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}?includeCompensation=true"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data["jobs"]:
        compensation_text = (job.get("compensation") or {}).get("compensationTierSummary") or ""

        jobs.append({
            "title": job["title"],
            "url": job["jobUrl"],
            "description": job.get("descriptionPlain") or "",
            "posted_date": job.get("publishedAt"),  # ISO date string
            "workplace_type": job.get("workplaceType"),  # 'Remote' / 'Hybrid' / 'Onsite'
            "compensation_text": compensation_text,
        })
    return jobs


def fetch_jobs_for_company(company):
    """
    Looks at the company's 'ats' value and calls the matching fetch
    function. This is the piece that lets the main loop below stay
    simple -- it doesn't need to know or care which ATS each company
    uses, it just calls this one function and gets jobs back either way.
    """
    if company["ats"] == "greenhouse":
        return fetch_greenhouse_jobs(company["slug"])
    elif company["ats"] == "lever":
        return fetch_lever_jobs(company["slug"])
    elif company["ats"] == "ashby":
        return fetch_ashby_jobs(company["slug"])
    else:
        print(f"  Skipping {company['name']}: unknown ATS '{company['ats']}'")
        return []


def load_seen_jobs():
    if not os.path.exists(SEEN_JOBS_FILE):
        return set()
    with open(SEEN_JOBS_FILE, "r") as f:
        return set(json.load(f))


def save_seen_jobs(seen_urls):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen_urls), f, indent=2)


def matches_keywords(title):
    title_lower = title.lower()
    for keyword in KEYWORDS:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, title_lower):
            return True
    return False


def send_notification(scored_jobs):
    """
    scored_jobs is a list of (job, score, reasons) tuples, already
    sorted highest score first.
    """
    subject = f"🎯 {len(scored_jobs)} new job match(es) found"

    body_lines = ["New job listings that passed your filters, best score first:\n"]
    for job, score, reasons in scored_jobs:
        body_lines.append(f"[{score:+d}] {job['title']}")
        body_lines.append(f"{job['url']}")
        if reasons:
            body_lines.append("  " + " | ".join(reasons))
        body_lines.append("")
    body = "\n".join(body_lines)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, NOTIFY_EMAIL, msg.as_string())

    print(f"Email sent to {NOTIFY_EMAIL}")


def check_all_companies():
    """
    One full run: fetch every company, compare against seen jobs,
    filter for keyword matches, email if anything matches, save state.

    This is the exact same logic that used to sit directly under
    'if __name__ == "__main__":' -- it's just wrapped in a function now
    so the scheduler below can call it once immediately and then again
    every hour, instead of it only being able to run once.
    """
    seen_urls = load_seen_jobs()
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting check...")
    print(f"Loaded {len(seen_urls)} previously seen job URLs\n")

    all_current_jobs = []

    for company in COMPANIES:
        print(f"Fetching {company['name']} ({company['ats']})...")
        try:
            company_jobs = fetch_jobs_for_company(company)
            all_current_jobs += company_jobs
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Couldn't fetch {company['name']}: {e}")

    print(f"\nFound {len(all_current_jobs)} total current listings\n")

    new_jobs = []
    for job in all_current_jobs:
        if job["url"] not in seen_urls:
            new_jobs.append(job)
            seen_urls.add(job["url"])

    print(f"{len(new_jobs)} new listing(s) since last run\n")

    matching_jobs = [job for job in new_jobs if matches_keywords(job["title"])]
    print(f"{len(matching_jobs)} match your keywords -- checking full details on those\n")

    scored_jobs = []
    filtered_out_count = 0
    for job in matching_jobs:
        passed, reason = passes_hard_filters(job)
        if not passed:
            filtered_out_count += 1
            print(f"  ❌ {job['title']} -- {reason}")
            continue
        score, reasons = score_job(job)
        scored_jobs.append((job, score, reasons))

    # Best-scoring jobs first
    scored_jobs.sort(key=lambda item: item[1], reverse=True)

    print(f"\n{filtered_out_count} filtered out by required/dealbreaker criteria")

    if scored_jobs:
        print(f"✅ {len(scored_jobs)} passed everything:\n")
        for job, score, reasons in scored_jobs:
            print(f"  [{score:+d}] {job['title']}")
            print(f"    {job['url']}")
        send_notification(scored_jobs)
    else:
        print("Nothing passed all filters this run. No email sent.")

    save_seen_jobs(seen_urls)
    print(f"Saved {len(seen_urls)} total job URLs to {SEEN_JOBS_FILE}")


if __name__ == "__main__":
    # GitHub sets this environment variable automatically whenever a
    # workflow runs. We use it to tell the difference between "running
    # on your laptop" (keep looping every hour forever) and "running in
    # GitHub Actions" (run once -- GitHub's own scheduler is what calls
    # this script every hour in the cloud, so we don't need our own
    # while-loop there).
    running_in_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"

    if running_in_github_actions:
        check_all_companies()
    else:
        check_all_companies()  # run once immediately so you don't wait an hour to see it work

        schedule.every(1).hours.do(check_all_companies)
        print("\n⏰ Scheduler is running. Checking every hour. Press Ctrl+C to stop.")

        while True:
            schedule.run_pending()
            time.sleep(60)
