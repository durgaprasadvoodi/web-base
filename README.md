# Entry-Level Job Board (HYD / BLR / CHN, 0-2 yrs)

Daily auto-updating job tracker, same pattern as `jb-searcher`:
- **scraper.py** scans offcampusjobdrives.com, keeps only posts mentioning
  Hyderabad / Bengaluru / Bangalore / Chennai *and* 0-2 yrs / fresher-level
  experience, and writes the results to `jobs.json`.
- **.github/workflows/scrape.yml** runs the scraper once a day via GitHub
  Actions and commits the updated `jobs.json` automatically.
- **index.html** is a static page (no backend needed) that reads `jobs.json`
  and renders the filterable table. This is what you publish via GitHub
  Pages.

## Setup (one-time, ~5 minutes)

1. **Create a new GitHub repo** (e.g. `job-tracker`), public.
2. **Upload all files in this folder** to the repo, keeping the folder
   structure (`.github/workflows/scrape.yml` must stay in that exact path).
   Easiest way: on github.com, use "Add file → Upload files" and drag in
   everything, or `git push` from your machine:
   ```bash
   git init
   git add .
   git commit -m "Initial job tracker setup"
   git branch -M main
   git remote add origin https://github.com/<your-username>/job-tracker.git
   git push -u origin main
   ```
3. **Enable GitHub Pages**: repo → Settings → Pages → Source: "Deploy from a
   branch" → Branch: `main`, folder: `/ (root)` → Save. Your site will be at
   `https://<your-username>.github.io/job-tracker/`.
4. **Enable Actions**: repo → Settings → Actions → General → make sure
   "Allow all actions" is selected, and under "Workflow permissions" choose
   "Read and write permissions" (needed so the bot can commit `jobs.json`).
5. **Run it once manually** so you don't have to wait for the daily cron:
   repo → Actions tab → "Daily Job Scrape" → "Run workflow" → Run workflow.
   Wait ~1-2 min, refresh, and `jobs.json` should now have entries.
6. Visit your Pages URL — the table will populate from `jobs.json`.

After that, it runs automatically every day at 04:00 UTC (~9:30 AM IST) and
commits new matches. No further action needed.

## Customizing

- **Change cities**: edit `TARGET_LOCATIONS` in `scraper.py`.
- **Change experience range**: edit `EXPERIENCE_PATTERNS` in `scraper.py`
  (currently matches fresher/0-2yr language; for a strict "0-2" only match,
  narrow the regex list).
- **Change schedule**: edit the `cron` line in
  `.github/workflows/scrape.yml` (uses UTC time).
- **Add more source sites**: add more listing page scraping logic to
  `scraper.py` following the same pattern (fetch listing pages → detail
  pages → filter → append to `jobs.json`).

## Notes / limitations

- This scrapes a third-party site's public listing pages. If that site
  changes its HTML structure, `scraper.py`'s selectors (`h2 a`, `.entry-content`)
  may need small updates.
- Always double-check details (location, experience, deadline) on the actual
  application page before applying — scraped keyword matches can occasionally
  be wrong (e.g. a post mentioning multiple cities where only one has the
  0-2 yr opening).
