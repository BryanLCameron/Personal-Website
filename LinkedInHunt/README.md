# JobTrack — LinkedIn Job Finder

A polished web app that scrapes live LinkedIn job postings by job title and region.
**No API key required** — uses `python-jobspy` to scrape LinkedIn directly.

> ⚠️ **Heads-up:** Direct LinkedIn scraping is against their Terms of Service.
> This app is intended for personal job-hunting use only, not as a public service.

---

## How It Works

1. You enter a **job title**, **county**, and **state**
2. The Flask backend calls `python-jobspy`, which scrapes LinkedIn's job search pages
3. Results are normalized and returned as JSON to the browser
4. The frontend renders animated job cards with title, company, location, salary, and apply links

---

## Local Setup

### 1. Clone / copy the project files

```
/
├── app.py              ← Flask backend (scrapes LinkedIn via jobspy)
├── wsgi.py             ← WSGI entry point for Hostinger
├── requirements.txt    ← Python dependencies
└── public/
    └── index.html      ← Frontend (self-contained HTML/CSS/JS)
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run locally

```bash
python app.py
```

Open `http://localhost:3000` in your browser.

---

## Deploying to Hostinger (Python / VPS)

### Option A — Hostinger VPS (recommended)

1. SSH into your VPS:
   ```bash
   ssh root@your-server-ip
   ```

2. Install Python and pip if needed:
   ```bash
   apt update && apt install -y python3 python3-pip python3-venv
   ```

3. Upload your files (via SFTP or git clone) to `/var/www/jobtrack/`

4. Install dependencies:
   ```bash
   cd /var/www/jobtrack
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. Run with gunicorn (production server):
   ```bash
   gunicorn --bind 0.0.0.0:3000 --workers 2 --timeout 60 wsgi:application
   ```

6. Set up an Nginx reverse proxy so `bryancameron.io` points to port 3000:
   ```nginx
   server {
       listen 80;
       server_name bryancameron.io www.bryancameron.io;

       location / {
           proxy_pass http://127.0.0.1:3000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_read_timeout 90;
       }
   }
   ```

7. Keep gunicorn running with PM2 or systemd:
   ```bash
   # Using PM2
   npm install -g pm2
   pm2 start "gunicorn --bind 0.0.0.0:3000 --workers 2 --timeout 60 wsgi:application" --name jobtrack
   pm2 save
   ```

### Option B — Hostinger Shared Hosting (Python / Passenger)

1. Upload all files to your public_html directory
2. Make sure `wsgi.py` is in the root — Hostinger's Passenger looks for `application` in this file
3. Set Python version to 3.10+ in the Hostinger control panel
4. In the control panel, run: `pip install -r requirements.txt`

---

## Tuning & Troubleshooting

### Getting blocked by LinkedIn?

LinkedIn occasionally rate-limits or blocks scraping. If you see errors:
- Wait 5–10 minutes and try again
- Reduce search frequency
- Add proxy support in `app.py` (see below)

### Adding proxy rotation (optional)

If you're hitting rate limits frequently, you can add proxies to `jobspy`:

```python
df = scrape_jobs(
    site_name=["linkedin"],
    search_term=title,
    location=location,
    results_wanted=results,
    hours_old=720,
    proxies=["http://user:pass@proxy-host:port"],  # add your proxies here
)
```

Free proxy lists exist but are unreliable; paid services like BrightData or Oxylabs are more stable.

### Increasing result count

In `app.py`, the default is 20 results (max 50 per request). Change this in the `/api/jobs` route:

```python
results = min(int(request.args.get("results", 20)), 50)
```

### Searching multiple job boards

`jobspy` also supports Indeed, Glassdoor, and ZipRecruiter. To add them:

```python
df = scrape_jobs(
    site_name=["linkedin", "indeed", "glassdoor"],
    ...
)
```

---

## Tech Stack

| Layer    | Technology         |
|----------|--------------------|
| Frontend | Vanilla HTML/CSS/JS |
| Backend  | Python 3 + Flask   |
| Scraping | python-jobspy      |
| Server   | Gunicorn + Nginx   |
| Hosting  | Hostinger VPS      |
