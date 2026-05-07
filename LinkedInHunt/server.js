require('dotenv').config();
const express = require('express');
const axios = require('axios');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// ─── Middleware ─────────────────────────────────────────────────────────────
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ─── Job Search Route ────────────────────────────────────────────────────────
app.get('/api/jobs', async (req, res) => {
  const { title, county, state, page = 1 } = req.query;

  if (!title || !county || !state) {
    return res.status(400).json({
      error: 'Missing required parameters: title, county, and state are all required.'
    });
  }

  const apiKey = process.env.RAPIDAPI_KEY;
  if (!apiKey || apiKey === 'YOUR_RAPIDAPI_KEY_HERE') {
    return res.status(500).json({
      error: 'API key not configured. Please set RAPIDAPI_KEY in your .env file.'
    });
  }

  const query = `${title.trim()} in ${county.trim()}, ${state.trim()}`;

  try {
    const response = await axios.get('https://jsearch.p.rapidapi.com/search', {
      params: {
        query,
        page: parseInt(page, 10),
        num_pages: 2,
        date_posted: 'month',
        employment_types: 'FULLTIME,PARTTIME,CONTRACTOR,INTERN'
      },
      headers: {
        'X-RapidAPI-Key': apiKey,
        'X-RapidAPI-Host': 'jsearch.p.rapidapi.com'
      },
      timeout: 15000
    });

    // Normalize and return the data
    const jobs = (response.data?.data || []).map(job => ({
      id: job.job_id,
      title: job.job_title,
      company: job.employer_name,
      logo: job.employer_logo || null,
      website: job.employer_website || null,
      location: [job.job_city, job.job_state].filter(Boolean).join(', '),
      isRemote: job.job_is_remote || false,
      employmentType: job.job_employment_type || null,
      applyLink: job.job_apply_link,
      description: job.job_description
        ? job.job_description.slice(0, 300).replace(/\s+/g, ' ').trim() + '…'
        : null,
      salary: formatSalary(job),
      postedAt: job.job_posted_at_datetime_utc || null
    }));

    res.json({
      query,
      total: jobs.length,
      page: parseInt(page, 10),
      jobs
    });

  } catch (err) {
    console.error('[JSearch Error]', err.response?.data || err.message);

    if (err.response?.status === 403 || err.response?.status === 401) {
      return res.status(401).json({ error: 'Invalid or expired API key. Please check your RAPIDAPI_KEY.' });
    }
    if (err.response?.status === 429) {
      return res.status(429).json({ error: 'API rate limit reached. Please wait a moment and try again.' });
    }

    res.status(500).json({ error: 'Failed to fetch jobs. Please try again shortly.' });
  }
});

// ─── Helpers ─────────────────────────────────────────────────────────────────
function formatSalary(job) {
  const { job_min_salary, job_max_salary, job_salary_currency, job_salary_period } = job;

  if (!job_min_salary && !job_max_salary) return null;

  const currency = job_salary_currency || 'USD';
  const period = job_salary_period === 'YEAR' ? '/yr'
    : job_salary_period === 'HOUR' ? '/hr'
    : job_salary_period === 'MONTH' ? '/mo'
    : '';

  const fmt = (n) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n);

  if (job_min_salary && job_max_salary) {
    return `${fmt(job_min_salary)} – ${fmt(job_max_salary)}${period}`;
  }
  if (job_min_salary) return `From ${fmt(job_min_salary)}${period}`;
  if (job_max_salary) return `Up to ${fmt(job_max_salary)}${period}`;
  return null;
}

// ─── Catch-all: serve index.html ─────────────────────────────────────────────
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ─── Start ───────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n🚀  Job Finder running at http://localhost:${PORT}`);
  console.log(`    API Key: ${process.env.RAPIDAPI_KEY ? '✅ Configured' : '❌ Not set — add RAPIDAPI_KEY to .env'}\n`);
});
