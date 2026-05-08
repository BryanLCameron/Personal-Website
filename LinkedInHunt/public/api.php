<?php
/**
 * JobTrack — API backend (PHP)
 * Works on any Hostinger shared hosting — no setup, no terminal, no services.
 *
 * Uses the Adzuna Jobs API (free, 1,000 searches/month, no credit card).
 * Sign up at: https://developer.adzuna.com/signup
 *
 * GET api.php?title=...&county=...&state=...&criteria=...
 */

// ── Config — paste your Adzuna credentials here ───────────────────────────
define('ADZUNA_APP_ID',  '03dccdb7');   // from developer.adzuna.com
define('ADZUNA_APP_KEY', 'c2f2214d15d6ce9420f3049254c8c5b5');  // from developer.adzuna.com

// ── Headers ───────────────────────────────────────────────────────────────
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

// ── Input ─────────────────────────────────────────────────────────────────
$title    = trim($_GET['title']    ?? '');
$county   = trim($_GET['county']   ?? '');
$state    = trim($_GET['state']    ?? '');
$criteria = trim($_GET['criteria'] ?? '');
$results  = min((int)($_GET['results'] ?? 20), 50);

if (!$title || !$county || !$state) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing required parameters: title, county, and state are all required.']);
    exit;
}

if (ADZUNA_APP_ID === 'YOUR_APP_ID_HERE' || ADZUNA_APP_KEY === 'YOUR_APP_KEY_HERE') {
    http_response_code(500);
    echo json_encode(['error' => 'API credentials not configured. Open api.php and add your Adzuna App ID and App Key from developer.adzuna.com.']);
    exit;
}

// ── Build Adzuna request ──────────────────────────────────────────────────
// Adzuna searches by "what" (keywords) and "where" (location string).
// Combining county + state gives good local results.
$location = "$county, $state";
$where    = urlencode("$county $state");   // e.g. "Orange County California"
$what     = urlencode($title);             // e.g. "Software Engineer"
$perPage  = min($results, 50);

$url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
     . "?app_id="          . ADZUNA_APP_ID
     . "&app_key="         . ADZUNA_APP_KEY
     . "&results_per_page=" . $perPage
     . "&what="             . $what
     . "&where="            . $where
     . "&sort_by=date"
     . "&content-type=application/json";

// ── Fetch ─────────────────────────────────────────────────────────────────
$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL            => $url,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 20,
    CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
]);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$curlErr  = curl_error($ch);
curl_close($ch);

if ($curlErr) {
    http_response_code(500);
    echo json_encode(['error' => 'Could not reach the job search API. Please try again.']);
    exit;
}

if ($httpCode === 401 || $httpCode === 403) {
    http_response_code(401);
    echo json_encode(['error' => 'Invalid Adzuna credentials. Check ADZUNA_APP_ID and ADZUNA_APP_KEY in api.php.']);
    exit;
}

if ($httpCode === 429) {
    http_response_code(429);
    echo json_encode(['error' => 'Monthly search limit reached. Adzuna free tier allows 1,000 searches/month.']);
    exit;
}

$data = json_decode($response, true);
if (!$data || !isset($data['results']) || !is_array($data['results'])) {
    http_response_code(502);
    echo json_encode(['error' => 'Unexpected response from the job API. Please try again shortly.']);
    exit;
}

// ── Normalize Adzuna results to our standard shape ────────────────────────
$jobs = [];
foreach ($data['results'] as $job) {
    $applyLink = $job['redirect_url'] ?? '';
    $jobTitle  = $job['title']        ?? '';
    if (!$applyLink || !$jobTitle) continue;

    // Adzuna puts location in job['location']['display_name']
    $loc = $job['location']['display_name'] ?? $location;

    // Contract type mapping
    $contractType = $job['contract_type'] ?? null;
    $empType = match($contractType) {
        'permanent'  => 'FULLTIME',
        'contract'   => 'CONTRACTOR',
        'part_time'  => 'PARTTIME',
        'temporary'  => 'TEMPORARY',
        default      => null,
    };

    $jobs[] = [
        'id'             => (string)($job['id'] ?? ''),
        'title'          => $jobTitle,
        'company'        => $job['company']['display_name'] ?? '',
        'logo'           => null,   // Adzuna doesn't return logos
        'website'        => null,
        'location'       => $loc,
        'isRemote'       => str_contains(strtolower($jobTitle . ' ' . ($job['description'] ?? '')), 'remote'),
        'employmentType' => $empType,
        'applyLink'      => $applyLink,
        'description'    => truncateText($job['description'] ?? '', 300),
        'salary'         => formatSalary($job),
        'postedAt'       => $job['created'] ?? null,
        'matchScore'     => null,
        'matchKeywords'  => [],
    ];
}

// ── Score & sort against criteria ─────────────────────────────────────────
if ($criteria && count($jobs) > 0) {
    $keywords = extractKeywords($criteria);
    foreach ($jobs as &$job) {
        [$score, $matched]   = scoreJob($job, $keywords);
        $job['matchScore']    = $score;
        $job['matchKeywords'] = $matched;
    }
    unset($job);
    usort($jobs, fn($a, $b) => $b['matchScore'] - $a['matchScore']);
}

// ── Respond ───────────────────────────────────────────────────────────────
echo json_encode([
    'query'    => "$title in $location",
    'total'    => count($jobs),
    'criteria' => $criteria,
    'jobs'     => $jobs,
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);


// ── Helper functions ──────────────────────────────────────────────────────

function formatSalary(array $job): ?string
{
    // Adzuna uses salary_min / salary_max (annual figures)
    $lo = $job['salary_min'] ?? null;
    $hi = $job['salary_max'] ?? null;

    if (!$lo && !$hi) return null;

    $fmt = fn($n) => '$' . number_format((int)$n);

    if ($lo && $hi) return "{$fmt($lo)} – {$fmt($hi)}/yr";
    if ($lo)        return "From {$fmt($lo)}/yr";
    if ($hi)        return "Up to {$fmt($hi)}/yr";
    return null;
}

function truncateText(string $text, int $max): ?string
{
    if (!$text) return null;
    $text = preg_replace('/\s+/', ' ', trim(strip_tags($text)));
    if (mb_strlen($text) <= $max) return $text;
    return mb_substr($text, 0, $max) . '…';
}

function extractKeywords(string $criteria): array
{
    static $stopWords = [
        'a','an','the','and','or','but','in','on','at','to','for','of','with',
        'by','from','is','are','was','were','be','been','have','has','had','do',
        'does','did','will','would','could','should','may','might','i','me','my',
        'we','our','you','your','it','its','this','that','these','those','want',
        'looking','like','work','job','role','position','seeking','need','ideally',
        'prefer','experience','years','year','also','about','some','any','all',
        'new','good','great','strong','excellent','able','well',
    ];

    $text = strtolower($criteria);
    preg_match_all('/\b[a-z0-9][a-z0-9+#.\-]{1,}\b/', $text, $matches);
    $words = array_filter(
        array_unique($matches[0]),
        fn($w) => !in_array($w, $stopWords, true) && strlen($w) > 1
    );
    return array_values($words);
}

function scoreJob(array $job, array $keywords): array
{
    if (!$keywords) return [0, []];

    $title   = strtolower($job['title']          ?? '');
    $company = strtolower($job['company']         ?? '');
    $desc    = strtolower($job['description']     ?? '');
    $loc     = strtolower($job['location']        ?? '');
    $emp     = strtolower($job['employmentType']  ?? '');

    $maxPts  = count($keywords) * 6;
    $earned  = 0;
    $matched = [];

    foreach ($keywords as $kw) {
        $hit = false;
        if (str_contains($title,   $kw)) { $earned += 3; $hit = true; }
        if (str_contains($company, $kw)) { $earned += 2; $hit = true; }
        if (str_contains($desc,    $kw)) { $earned += 1; $hit = true; }
        if (str_contains($loc, $kw) || str_contains($emp, $kw)) {
            $earned += 1; $hit = true;
        }
        if ($hit) $matched[] = $kw;
    }

    $score = $maxPts > 0 ? min((int)round($earned / $maxPts * 100), 100) : 0;
    return [$score, $matched];
}
