#!/usr/bin/env python3
"""
Scrapes job postings from:
  1. offcampusjobdrives.com (listing + detail pages)
  2. Public Telegram channels (e.g. t.me/latestmncjobs), via their public
     web preview at t.me/s/<channel> — no login needed.

Keeps only postings matching:
  - Experience: 0-2 years (freshers / entry level)
  - Location: Hyderabad, Bengaluru/Bangalore, or Chennai

Writes/updates jobs.json with a cumulative record (new jobs are appended,
each with a "first_seen" date and a "source" field, so the front-end can
show what's new and where it came from.

Designed to be run daily by GitHub Actions.
"""

import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://offcampusjobdrives.com"

# Only crawl the first few listing pages each run (site is sorted newest-first,
# so we don't need to walk all ~60+ pages every day).
LISTING_PAGES_TO_SCAN = 6

# Category pages worth checking (fresher + experienced, both filtered by
# experience text later since some "experienced" posts still say 0-2 yrs).
LISTING_URLS = [
    f"{BASE}/category/fresher-jobs/",
    f"{BASE}/",
]

# Public Telegram channels to scan (just the @username, no @ or t.me/ prefix).
# Add more channel usernames here to track additional sources.
TELEGRAM_CHANNELS = [
    "latestmncjobs",
]

TARGET_LOCATIONS = {
    "hyderabad": "Hyderabad",
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "chennai": "Chennai",
}

# Patterns that indicate 0-2 years / fresher-level experience
EXPERIENCE_PATTERNS = [
    r"\b0\s*-\s*2\s*year",
    r"\b0\s*to\s*2\s*year",
    r"\b0\s*-\s*1\s*year",
    r"\bfresher",
    r"\bentry[\s-]?level",
    r"\b0\+?\s*years?\b",
    r"\bgraduate\b",
    r"\btrainee\b",
    r"\bapprentice\b",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobSearcherBot/1.0; "
                  "+https://github.com/) job-tracker-script"
}

DATA_FILE = Path(__file__).parent / "jobs.json"


def fetch(url, retries=3, timeout=20):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            pass
        time.sleep(2)
    return None


def get_listing_posts(url):
    """Return list of (title, link, published_date) from a listing page."""
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for h2 in soup.select("h2 a"):
        title = h2.get_text(strip=True)
        link = h2.get("href")
        if not link or not title:
            continue
        posts.append({"title": title, "link": link})
    return posts


def detect_locations(text):
    text_lower = text.lower()
    found = set()
    for key, label in TARGET_LOCATIONS.items():
        if key in text_lower:
            found.add(label)
    return sorted(found)


def detect_experience_match(text):
    text_lower = text.lower()
    for pattern in EXPERIENCE_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def scrape_post_detail(link):
    html = fetch(link)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("article") or soup.select_one(".entry-content") or soup
    return content.get_text(" ", strip=True)


def get_telegram_messages(channel):
    """Return a list of {title, link, text} for recent posts in a public
    Telegram channel, scraped from its public preview page (no login)."""
    url = f"https://t.me/s/{channel}"
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    messages = []
    for msg_div in soup.select("div.tgme_widget_message"):
        text_div = msg_div.select_one("div.tgme_widget_message_text")
        if not text_div:
            continue
        text = text_div.get_text("\n", strip=True)
        if not text:
            continue

        post_id = msg_div.get("data-post")  # e.g. "latestmncjobs/12345"
        permalink = f"https://t.me/{post_id}" if post_id else url

        # Prefer the actual "apply" link over the telegram/whatsapp promo links
        apply_link = None
        for a in text_div.select("a"):
            href = a.get("href", "")
            if href and "t.me/" not in href and "whatsapp.com" not in href:
                apply_link = href
                break
        link = apply_link or permalink

        first_line = text.split("\n")[0].strip()
        title = first_line if first_line else text[:80]

        messages.append({"title": title, "link": link, "text": text,
                          "source": "Telegram: @" + channel})
    return messages


def load_existing():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def main():
    existing = load_existing()
    existing_by_link = {job["link"]: job for job in existing}

    today = date.today().isoformat()

    # --- Source 1: offcampusjobdrives.com ---
    # These come from the listing page without detail text, so we fetch the
    # full post page separately (below) to check location/experience.
    site_posts = []
    for listing_url in LISTING_URLS:
        for page in range(1, LISTING_PAGES_TO_SCAN + 1):
            page_url = listing_url if page == 1 else f"{listing_url}page/{page}/"
            posts = get_listing_posts(page_url)
            if not posts:
                break
            site_posts.extend(posts)

    for post in site_posts:
        post["source"] = "Off-Campus Job Drives"
        post["text"] = None  # fetched lazily below, only for new links

    # --- Source 2: Telegram channels ---
    # Messages already contain the full text, no extra fetch needed.
    telegram_posts = []
    for channel in TELEGRAM_CHANNELS:
        telegram_posts.extend(get_telegram_messages(channel))
        time.sleep(1)

    all_candidates = site_posts + telegram_posts

    seen_links = set()
    new_count = 0
    for post in all_candidates:
        link = post["link"]
        if link in seen_links:
            continue
        seen_links.add(link)

        if link in existing_by_link:
            # Already tracked — skip re-checking to save time.
            continue

        # Telegram messages already carry their full text; site posts need
        # a follow-up fetch of the detail page for the experience/location text.
        detail_text = post.get("text")
        if detail_text is None:
            detail_text = scrape_post_detail(link)
            time.sleep(1)  # be polite to the source site

        combined_text = f"{post['title']} {detail_text}"

        locations = detect_locations(combined_text)
        experience_match = detect_experience_match(combined_text)

        if not locations or not experience_match:
            continue  # doesn't match our filter, don't store it

        job_entry = {
            "title": post["title"],
            "link": link,
            "locations": locations,
            "experience_match": True,
            "source": post.get("source", "Unknown"),
            "first_seen": today,
        }
        existing_by_link[link] = job_entry
        new_count += 1

    # Keep only the most recent 300 entries to keep the file small
    all_jobs = sorted(
        existing_by_link.values(), key=lambda j: j["first_seen"], reverse=True
    )[:300]

    DATA_FILE.write_text(json.dumps(all_jobs, indent=2))
    print(f"Scan complete. {new_count} new job(s) added. "
          f"{len(all_jobs)} total tracked. Updated {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
