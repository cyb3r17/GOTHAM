#!/usr/bin/env python3
"""Generate GOTHAM platform documentation PDF."""
import sys
sys.path.insert(0, 'src')

from fpdf import FPDF
import datetime

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=20)

BG    = (255, 255, 255)
TEXT  = (18,  18,  24)
MUTED = (105, 105, 115)
HEAD  = (20,  20,  28)
CYAN  = (15,  130, 140)
GREEN = (30,  130,  70)
PURP  = (100,  70, 190)
ORNG  = (185,  95,  20)
RED   = (165,  50,  50)
RULE  = (210, 210, 218)

def set_bg():
    pdf.set_fill_color(*BG)
    pdf.rect(0, 0, 210, 297, 'F')

def rule(color=RULE):
    pdf.set_draw_color(*color)
    pdf.line(14, pdf.get_y(), 196, pdf.get_y())

def s(text):
    return (str(text)
        .replace('\u2014','--').replace('\u2013','-')
        .replace('\u2018',"'").replace('\u2019',"'")
        .replace('\u201c','"').replace('\u201d','"')
        .replace('\u2026','...').replace('\u00b7','·')
        .encode('latin-1', errors='replace').decode('latin-1'))

def h1(text):
    pdf.set_font('Helvetica','B',22)
    pdf.set_text_color(*HEAD)
    pdf.cell(0, 12, s(text), ln=True)

def h2(text, color=HEAD):
    pdf.ln(4)
    pdf.set_font('Helvetica','B',13)
    pdf.set_text_color(*color)
    pdf.cell(0, 8, s(text), ln=True)
    pdf.set_draw_color(*color)
    pdf.line(14, pdf.get_y(), 80, pdf.get_y())
    pdf.ln(3)

def h3(text, color=MUTED):
    pdf.ln(2)
    pdf.set_font('Helvetica','B',9)
    pdf.set_text_color(*color)
    pdf.cell(0, 5, s(text.upper()), ln=True)

def body(text, color=TEXT, size=9):
    pdf.set_x(14)
    pdf.set_font('Helvetica','',size)
    pdf.set_text_color(*color)
    pdf.multi_cell(182, 5, s(text.lstrip('\n')))

def bullet(text, color=TEXT):
    pdf.set_font('Helvetica','',9)
    pdf.set_text_color(*color)
    pdf.set_x(18)
    pdf.multi_cell(178, 5, s(f'- {text}'))

def tag(text, color):
    pdf.set_font('Helvetica','B',7)
    pdf.set_text_color(*color)
    r,g,b = color
    pdf.set_fill_color(min(255,r+210), min(255,g+210), min(255,b+210))
    w = pdf.get_string_width(text) + 8
    pdf.cell(w, 5, s(text.upper()), fill=True, ln=False)
    pdf.cell(4, 5, '', ln=False)

def kv(key, val, kcolor=MUTED, vcolor=TEXT):
    pdf.set_x(14)
    pdf.set_font('Helvetica','B',7)
    pdf.set_text_color(*kcolor)
    pdf.cell(40, 4.5, s(key.upper()+':'), ln=False)
    pdf.set_font('Helvetica','',8)
    pdf.set_text_color(*vcolor)
    pdf.multi_cell(0, 4.5, s(str(val)))

# ══════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════
pdf.add_page()
set_bg()

pdf.set_y(55)
pdf.set_font('Helvetica','B',7)
pdf.set_text_color(*MUTED)
pdf.cell(0, 5, 'TECHNICAL DOCUMENTATION  --  INTERNAL USE', align='C', ln=True)
pdf.ln(2)
rule()
pdf.ln(20)

pdf.set_font('Helvetica','B',56)
pdf.set_text_color(*HEAD)
pdf.cell(0, 18, 'GOTHAM', align='C', ln=True)
pdf.ln(3)
pdf.set_font('Helvetica','',11)
pdf.set_text_color(*MUTED)
pdf.cell(0, 6, 'Open-Source Intelligence Platform', align='C', ln=True)
pdf.ln(30)
rule((60,100,80))
pdf.ln(14)

pdf.set_font('Helvetica','B',7)
pdf.set_text_color(*MUTED)
pdf.cell(0, 5, 'PLATFORM OVERVIEW', ln=True)
pdf.set_font('Helvetica','',10)
pdf.set_text_color(*TEXT)
pdf.multi_cell(0, 6, s(
    'Gotham is a multi-source OSINT (Open-Source Intelligence) platform designed for '
    'identity investigation and digital footprint mapping. Given one or more identifiers '
    '-- a username, email address, or phone number -- Gotham orchestrates a parallel '
    'pipeline of intelligence providers, builds a force-directed identity graph, verifies '
    'results with AI, and produces a tamper-evident PDF report with cryptographic hashes '
    'of all collected evidence.'
))

pdf.ln(12)
stats = [
    ('Sources', '10+'), ('Node Types', '12'), ('API Providers', '6'),
    ('Report Pages', '7+'), ('Evidence Hashing', 'SHA-256'),
]
col_w = 36
pdf.set_x(14)
for _, v in stats:
    pdf.set_font('Helvetica','B',18); pdf.set_text_color(*GREEN)
    pdf.cell(col_w, 9, v, ln=False)
pdf.ln(9)
pdf.set_x(14)
for k, _ in stats:
    pdf.set_font('Helvetica','B',6); pdf.set_text_color(*MUTED)
    pdf.cell(col_w, 5, k.upper(), ln=False)
pdf.ln(12)
rule()
pdf.ln(6)
pdf.set_font('Helvetica','',8); pdf.set_text_color(*MUTED)
pdf.cell(0, 5, s(f'Generated  {datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC'), ln=True)


# ══════════════════════════════════════════════════════════════
# PAGE 2 — ARCHITECTURE
# ══════════════════════════════════════════════════════════════
pdf.add_page(); set_bg(); pdf.set_y(16)
h1('System Architecture')
rule(); pdf.ln(6)

h2('Technology Stack', PURP)
body(
    'Gotham is a Python Flask web application with an SQLite database, served on port 5000. '
    'The frontend uses HTMX for partial-page updates, D3.js v7 for the force-directed graph, '
    'and vanilla CSS with JetBrains Mono / Inter fonts. There is no JavaScript framework -- '
    'all state is server-side.'
)
pdf.ln(3)
for row in [
    ('Backend',       'Python 3 / Flask'),
    ('Database',      'SQLite (single file, gotham.db)'),
    ('Frontend',      'HTMX 2.0.4 + D3.js v7 + CSS'),
    ('AI Screening',  'Google Gemini 2.5 Flash (vision)'),
    ('Browser Pool',  'Selenium Firefox (Geckodriver) -- headless, 3 workers'),
    ('OSINT Gateway', 'Argus Gateway on 172.16.128.144:8000 (internal)'),
    ('PDF Export',    'fpdf2'),
    ('Image Search',  'PIL / Pillow for image handling'),
]:
    kv(row[0], row[1])

h2('Database Schema', HEAD)
body('Four core tables + one integrity table:')
pdf.ln(2)
for tbl, desc in [
    ('users',        'username, bcrypt-style SHA-256 password hash'),
    ('investigations','id, name, owner (username), created_at'),
    ('nodes',        'id (scoped string), inv_id, label, type, props (JSON blob)'),
    ('edges',        'inv_id, source node id, target node id, relationship label'),
    ('file_hashes',  'inv_id, filename, sha256 digest, created_at -- evidence integrity log'),
]:
    pdf.set_x(14); pdf.set_font('Helvetica','B',8); pdf.set_text_color(*CYAN)
    pdf.cell(38, 4.5, s(tbl), ln=False)
    pdf.set_font('Helvetica','',8); pdf.set_text_color(*TEXT)
    pdf.multi_cell(0, 4.5, s(desc))

h2('Case Folder Structure', HEAD)
body(
    'Every investigation gets a dedicated folder under cases/{inv_id}/ containing '
    'sub-folders for screenshots, camera frames, and PDF reports. Each artefact file '
    'is accompanied by a .sha256 sidecar in shasum-compatible format.'
)
pdf.ln(2)
for line in [
    'cases/{inv_id}/screenshots/{node_id}.png  -- platform profile screenshots',
    'cases/{inv_id}/screenshots/{node_id}.png.sha256',
    'cases/{inv_id}/cameras/cam_{ip}_{port}.jpg  -- camera sweep frames',
    'cases/{inv_id}/reports/gotham_{name}_{id}.pdf  -- exported report',
    'cases/{inv_id}/reports/gotham_{name}_{id}.pdf.sha256',
]:
    pdf.set_x(18); pdf.set_font('Courier','',7); pdf.set_text_color(*MUTED)
    pdf.cell(0, 4, s(line), ln=True)


# ══════════════════════════════════════════════════════════════
# PAGE 3 — INVESTIGATION PIPELINE
# ══════════════════════════════════════════════════════════════
pdf.add_page(); set_bg(); pdf.set_y(16)
h1('Investigation Pipeline')
rule(); pdf.ln(6)

body(
    'An investigation is triggered by submitting at least one identifier: username, '
    'email address, or phone number. All applicable providers are dispatched in parallel '
    'via a ThreadPoolExecutor (8 workers). Results are merged into a unified graph of '
    'typed nodes and labelled edges, then verified and AI-screened before the user sees them.'
)

h2('Stage 1 -- Parallel Provider Scan', GREEN)
providers = [
    ('Maigret',     'username', 'Queries 500+ social platforms. Returns profile URLs, bio data, follower counts, avatars, and site rank.'),
    ('Sherlock',    'username', 'Secondary username search across 400+ platforms. Results merged with Maigret, duplicates deduplicated by node ID.'),
    ('DuckDuckGo Dorks', 'username', 'Seven single-site dork queries: profile (inurl), GitHub, Pastebin, Reddit, Keybase, Medium, Steam. Results filtered by URL path segment to prevent substring false positives.'),
    ('Holehe',      'email',    'Checks 200+ platforms for email registration via the Argus Gateway. Returns platform name, method (login/reset/register), rate-limit flags.'),
    ('Moriarty',    'phone',    'Phone number enrichment: carrier, line type, region, CNAM lookup.'),
    ('WhatsApp',    'phone',    'Checks if phone number is registered on WhatsApp, returns profile metadata.'),
    ('Telegram',    'username', 'Channel/user lookup. Returns subscriber count, description, linked URLs.'),
]
for name, req, desc in providers:
    pdf.set_x(14)
    pdf.set_font('Helvetica','B',9); pdf.set_text_color(*HEAD)
    pdf.cell(55, 5, s(name), ln=False)
    pdf.set_font('Helvetica','B',7); pdf.set_text_color(*CYAN)
    pdf.cell(30, 5, s(f'[{req}]'), ln=False)
    pdf.ln(5)
    pdf.set_x(18); pdf.set_font('Helvetica','',8); pdf.set_text_color(*MUTED)
    pdf.multi_cell(178, 4.5, s(desc))
    pdf.ln(1)

h2('Stage 2 -- URL Verification', HEAD)
body(
    'Every platform URL returned by Maigret and Sherlock is verified with an HTTP HEAD '
    'request (5s timeout). URLs returning 404 or connection errors are removed from the '
    'investigation before the graph is built. Blacklisted domains (.ru TLD, Figma, Xing, '
    'Mastodon.cloud) are discarded at discovery time.'
)

h2('Stage 3 -- AI Visual Screening', HEAD)
body(
    'Verified platform URLs are screenshotted using a pool of 3 headless Firefox browsers '
    '(Selenium + Geckodriver). Each screenshot is sent to Gemini 2.5 Flash with a prompt '
    'asking whether the account belongs to the queried username. Accounts classified as '
    'inactive or mismatched with high/medium confidence are removed. Screenshots are always '
    'persisted to the case folder regardless of the AI decision.'
)

h2('Stage 4 -- Reverse Image Intelligence', HEAD)
body(
    'Avatar images from confirmed platform nodes are downloaded and sent to three '
    'parallel Argus Gateway endpoints: Yandex Reverse Image Search, Face Search '
    '(facial recognition database lookup), and general Image Similarity Search. '
    'Results are added as image_match nodes connected to the investigation anchor.'
)


# ══════════════════════════════════════════════════════════════
# PAGE 4 -- GRAPH & NODE TYPES
# ══════════════════════════════════════════════════════════════
pdf.add_page(); set_bg(); pdf.set_y(16)
h1('Identity Graph')
rule(); pdf.ln(6)

body(
    'All findings are stored as a typed node graph in SQLite and rendered in the browser '
    'as a D3.js force-directed graph. Nodes repel each other, edges pull related nodes '
    'together, and node size scales with connection degree. The graph supports pan, zoom, '
    'drag, hover highlighting, and click-to-inspect.'
)

h2('Node Types', HEAD)
node_types = [
    ('username',    '#f1f5f9', 'The investigation anchor. Created from the input identifier.'),
    ('platform',    '#a78bfa', 'A social/professional profile found by Maigret or Sherlock. Props include URL, rank, tags, source tool, avatar, bio, follower counts.'),
    ('email',       '#fbbf24', 'Email address, either provided as input or extracted from platform profiles.'),
    ('phone',       '#f472b6', 'Phone number with Moriarty enrichment (carrier, region, CNAM) and WhatsApp status.'),
    ('location',    '#4ade80', 'Geographic location extracted from profile data.'),
    ('ip',          '#f87171', 'IP address found in profile metadata.'),
    ('domain',      '#34d399', 'Domain extracted from profile URLs or email addresses.'),
    ('dork_hub',    '#fb923c', 'Dork category hub node (e.g. "paste", "code"). Groups dork results by category.'),
    ('dork',        '#fb923c', 'Individual DuckDuckGo search result. Props: URL, snippet, query used, category.'),
    ('image_match', '#22d3ee', 'Reverse image search or face recognition match. Props: source (yandex/face/image), URL, similarity score, title.'),
    ('camera',      '#10b981', 'Open IP camera found during a Camera Sweep. Props: IP, port, city, country, source (insecam/fofa), faces_detected count.'),
]
for ntype, color, desc in node_types:
    hex_r = int(color[1:3],16); hex_g = int(color[3:5],16); hex_b = int(color[5:7],16)
    pdf.set_x(14)
    pdf.set_fill_color(min(255,hex_r+195), min(255,hex_g+195), min(255,hex_b+195))
    pdf.set_font('Helvetica','B',8); pdf.set_text_color(hex_r, hex_g, hex_b)
    pdf.cell(30, 5, s(ntype.upper()), fill=True, ln=False)
    pdf.cell(4, 5, '', ln=False)
    pdf.set_font('Helvetica','',8); pdf.set_text_color(*TEXT)
    pdf.multi_cell(0, 5, s(desc))

h2('Graph Interactions', HEAD)
for item in [
    'Click a node -- opens the detail panel on the right with all props and connections',
    'Click a connection in the detail panel -- navigates to that node and centres the graph',
    'Drag -- pin a node to a fixed position',
    'Scroll / pinch -- zoom in/out',
    'Click canvas background -- deselects current node',
    'Zoom controls (+/-/fit) -- bottom-right corner buttons',
    'PDF button -- appears when a case is active, downloads the report',
]:
    bullet(item)


# ══════════════════════════════════════════════════════════════
# PAGE 5 -- ARGUS GATEWAY INTEGRATION
# ══════════════════════════════════════════════════════════════
pdf.add_page(); set_bg(); pdf.set_y(16)
h1('Argus Gateway Integration')
rule(); pdf.ln(6)

body(
    'The Argus Gateway is an internal microservice at 172.16.128.144:8000 exposing multiple '
    'OSINT and AI providers under a unified REST API. All endpoints return a ServiceResponse '
    'envelope: {results: [...], provenance: {}, errors: []}. Gotham\'s _argus_post() and '
    '_argus_post_file() helpers automatically unwrap the results list.'
)

h2('Endpoints Used', CYAN)
endpoints = [
    ('/providers/holehe/search',    'POST JSON',      'Email registration check across 200+ platforms'),
    ('/providers/moriarty/lookup',  'POST JSON',      'Phone number carrier, region, CNAM enrichment'),
    ('/providers/whatsapp/check',   'POST JSON',      'WhatsApp registration and profile metadata'),
    ('/providers/yandeximage/search','POST multipart','Yandex reverse image search (top 10 results)'),
    ('/face/detect',                'POST multipart', 'Detect faces in an image, return bounding boxes + embeddings'),
    ('/face/search',                'POST multipart', 'Search facial recognition database for identity matches'),
    ('/face/compare',               'POST JSON',      'Compare two images for facial similarity (base64 encoded)'),
    ('/face/embed',                 'POST multipart', 'Generate face embedding vector for an image'),
    ('/image/search',               'POST multipart', 'General visual similarity search'),
    ('/analyze/face-pipeline',      'POST multipart', 'Full face analysis pipeline (returns text/plain report)'),
]
pdf.set_x(14)
pdf.set_font('Helvetica','B',7); pdf.set_text_color(*MUTED)
pdf.cell(70, 4, 'ENDPOINT', ln=False)
pdf.cell(30, 4, 'METHOD', ln=False)
pdf.cell(0,  4, 'DESCRIPTION', ln=True)
rule()
pdf.ln(1)
for ep, method, desc in endpoints:
    pdf.set_x(14)
    pdf.set_font('Courier','',7); pdf.set_text_color(*CYAN)
    pdf.cell(70, 4, s(ep), ln=False)
    pdf.set_font('Helvetica','',7); pdf.set_text_color(*MUTED)
    pdf.cell(30, 4, s(method), ln=False)
    pdf.set_font('Helvetica','',7); pdf.set_text_color(*TEXT)
    pdf.multi_cell(0, 4, s(desc))

h2('Telegram Channel Lookup', HEAD)
body(
    'Telegram lookup is implemented via the Argus Gateway Telegram provider. '
    'Given a username, it returns channel metadata: subscriber count, description, '
    'linked URLs, and post statistics. Results are added as platform nodes connected '
    'to the anchor username node.'
)

h2('Parallel Image Intelligence', HEAD)
body(
    'When platform nodes with avatar URLs are found, Gotham downloads each avatar '
    'and dispatches three concurrent requests to the Argus Gateway using a '
    'ThreadPoolExecutor: Yandex Reverse Image Search, Face Search, and Image '
    'Similarity Search. All three run simultaneously; results are merged and stored '
    'as image_match nodes.'
)


# ══════════════════════════════════════════════════════════════
# PAGE 6 -- CAMERA SWEEP
# ══════════════════════════════════════════════════════════════
pdf.add_page(); set_bg(); pdf.set_y(16)
h1('Camera Sweep')
rule(); pdf.ln(6)

body(
    'The Camera Sweep is a standalone intelligence module accessible at /cameras. '
    'Given a geographic location (city name, country code, or both), it discovers '
    'publicly accessible IP cameras, captures frames, runs facial detection, and '
    'optionally compares detected faces against the subject\'s known avatar. '
    'Results are written as camera and image_match nodes into a selected investigation, '
    'and all captured frames are stored in the case folder with SHA-256 hashes.'
)

h2('Discovery -- Insecam', GREEN)
body(
    'Insecam (insecam.org) is a public index of accessible IP cameras searchable by '
    'country code or city. Gotham scrapes up to 3 pages of results per query, extracting '
    'camera IP:port combinations from embedded stream image URLs in the page HTML. '
    'SSL verification is bypassed for this source (Insecam uses a self-signed certificate). '
    'Queries are made for both /en/bycountry/{CC}/ and /en/bycity/{city}/ paths, plus '
    'the /en/bytag/{city}/ fallback.'
)

h2('Discovery -- FOFA (Optional)', ORNG)
body(
    'If FOFA_EMAIL and FOFA_KEY environment variables are set, FOFA is queried as a '
    'supplement when Insecam returns fewer than 5 results. FOFA\'s API accepts base64-encoded '
    'query strings and returns IP, port, city, and country for each match. '
    'FOFA has a free tier (1 query/day, 100 results). Query used: camera=true && city="{city}".'
)

h2('Frame Capture', HEAD)
body(
    'For each discovered camera, Gotham tries up to 10 common snapshot URL patterns in order:'
)
for url in [
    '/snapshot.jpg', '/jpg/image.jpg', '/image.jpg', '/snap.jpg', '/video.jpg',
    '/cgi-bin/snapshot.cgi', '/cgi-bin/currentpicture.cgi', '/mjpg/snapshot.cgi',
    '/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2', '/ (root, accepts image/* content-type)',
]:
    pdf.set_x(18); pdf.set_font('Courier','',7); pdf.set_text_color(*MUTED)
    pdf.cell(0, 4, s(url), ln=True)
body('A response is accepted if it is larger than 2KB and either has an image/* content-type or starts with JPEG magic bytes (0xFF 0xD8 0xFF).')

h2('Face Detection & Matching', CYAN)
for step, desc in [
    ('1. Detect',  'Frame sent to Argus /face/detect. If no faces returned, camera is still added to the graph as a standalone camera node.'),
    ('2. Search',  'If faces are detected, the frame is sent to Argus /face/search to find identity matches in the facial recognition database.'),
    ('3. Compare', 'If the investigation has a subject with a known avatar (from platform nodes), the avatar is downloaded and compared to the camera frame via Argus /face/compare. Returns a 0.0-1.0 similarity score.'),
    ('4. Link',    'If subject similarity exceeds 0.55, a direct edge is added from the subject username node to the camera node, labelled "seen on camera (XX%)".'),
]:
    pdf.set_x(14); pdf.set_font('Helvetica','B',8); pdf.set_text_color(*CYAN)
    pdf.cell(20, 5, s(step), ln=False)
    pdf.set_font('Helvetica','',8); pdf.set_text_color(*TEXT)
    pdf.multi_cell(0, 5, s(desc))

h2('UI', HEAD)
body(
    'The Camera Sweep page is at /cameras (linked in the nav bar). It features a '
    'single control bar with a location field and an investigation selector dropdown '
    '(existing investigations or auto-create a new one). Results appear as a responsive '
    'grid of camera cards showing the live stream snapshot, IP:port, location, face count '
    'badge, subject match percentage, and individual face search results with confidence scores. '
    'Sweep progress is polled every 2 seconds via HTMX.'
)


# ══════════════════════════════════════════════════════════════
# PAGE 7 -- EVIDENCE INTEGRITY & PDF REPORTS
# ══════════════════════════════════════════════════════════════
pdf.add_page(); set_bg(); pdf.set_y(16)
h1('Evidence Integrity & PDF Reports')
rule(); pdf.ln(6)

h2('Cryptographic Hashing', GREEN)
body(
    'Every artefact generated by Gotham -- screenshots, camera frames, and PDF reports -- '
    'is SHA-256 hashed at the moment of creation. Hashes are stored in two places:'
)
for item in [
    'SQLite file_hashes table: inv_id, filename, sha256, created_at',
    '.sha256 sidecar file alongside the artefact (shasum-compatible format)',
]:
    bullet(item)
body(
    '\nThis dual storage means integrity can be verified independently of the database '
    'using the standard shasum -c command. Any post-capture modification produces a '
    'different hash, making tampering detectable.'
)

h2('PDF Report Structure', HEAD)
body('Reports are generated on-demand via the PDF button in the dashboard. Each report contains:')
pdf.ln(2)
pages = [
    ('Cover Page',            'Subject name, generation timestamp, analyst username, stats row (platform count, username count, email count, phone count, dork hits, image matches).'),
    ('Platform Intelligence', 'All confirmed platforms sorted by global site rank. Each entry shows the profile URL, tags, source tool, and all metadata fields in a compact 2-per-row grid.'),
    ('Platform Screenshots',  'Paginated 2x4 grid of profile screenshots (8 per page). Pages are labelled e.g. "Platform Screenshots (2/3)".'),
    ('Identity & Artifacts',  'Alternate usernames, email addresses (with Holehe source data), phone numbers (with Moriarty enrichment), locations, IP addresses, and linked domains.'),
    ('Dork Intelligence',     'Category summary strip, then each dork hit with category pill, title, URL, query used, and search snippet (up to 280 chars).'),
    ('Image Intelligence',    'Groups reverse image search and face recognition results by provider (yandex/face/image). Each match shows title, domain, similarity score, URL, and extra props.'),
    ('Evidence Integrity',    'Table of all SHA-256 hashes for artefacts collected in this investigation: filename, full hex digest, and UTC capture timestamp.'),
    ('Methodology',           'Description of all sources, verification steps, AI screening, and classification approach.'),
]
for page, desc in pages:
    pdf.set_x(14); pdf.set_font('Helvetica','B',8); pdf.set_text_color(*HEAD)
    pdf.cell(55, 5, s(page), ln=False)
    pdf.set_font('Helvetica','',8); pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5, s(desc))

h2('Email & Phone-Only Investigations', HEAD)
body(
    'Investigations do not require a username. An email-only investigation runs Holehe '
    'and reverse image search on any avatars found. A phone-only investigation runs '
    'Moriarty and WhatsApp. The PDF report adapts gracefully -- platform and screenshot '
    'pages are omitted if empty, and the cover page stats reflect only the data that exists.'
)


# ══════════════════════════════════════════════════════════════
# PAGE 8 -- USER INTERFACE
# ══════════════════════════════════════════════════════════════
pdf.add_page(); set_bg(); pdf.set_y(16)
h1('User Interface')
rule(); pdf.ln(6)

h2('Authentication', HEAD)
body(
    'Gotham has a simple username/password authentication system. Passwords are hashed '
    'with SHA-256. Sessions are Flask cookie-based. All API endpoints and pages require '
    'an active session (@login_required decorator).'
)

h2('Dashboard (/dashboard)', PURP)
body('Three-panel layout (fixed viewport, no scroll):')
for panel, desc in [
    ('Left panel (220px)',  'Investigation list with case search filter. Click any case to load its graph. Cases are ordered newest first.'),
    ('Center (flex: 1)',    'Search bar with Username / Email / Phone inputs (any one required). Force-directed D3 graph fills remaining space. Loading bar animates during scans. Status strip shows progress stages.'),
    ('Right panel (280px)', 'Node detail panel. Shows type badge, label, avatar (if available), Visit Profile button, site rank, categories, all metadata fields, and clickable connection list.'),
]:
    pdf.set_x(14); pdf.set_font('Helvetica','B',8); pdf.set_text_color(*PURP)
    pdf.cell(42, 5, s(panel), ln=False)
    pdf.set_font('Helvetica','',8); pdf.set_text_color(*TEXT)
    pdf.multi_cell(0, 5, s(desc))

h2('Case Search', HEAD)
body(
    'A search input above the investigation list filters cases in real time by name. '
    'The filter is preserved across investigation list refreshes (re-applied after '
    'HTMX swaps the list content following a new investigation).'
)

h2('Investigation Progress', HEAD)
body(
    'After submitting the search form, a background thread runs the full pipeline. '
    'The frontend polls /api/status/{task_id} every 2 seconds via HTMX, displaying '
    'the current stage (Scanning providers -> Verifying URLs -> AI screening -> '
    'Reverse image search). When complete, the investigation list is refreshed '
    'and the new graph loads automatically.'
)

h2('Camera Sweep (/cameras)', CYAN)
body(
    'Separate page linked in the nav bar. Control bar with location input and '
    'investigation selector. Results render as a camera card grid with live '
    'stream images, face detection badges, and subject similarity scores. '
    'All camera intelligence is written back to the selected investigation graph.'
)

h2('Known Constraints', RED)
for item in [
    'Insecam coverage varies significantly by region. Some cities/countries have no indexed cameras.',
    'Gemini AI screening requires a valid API key in src/.env (gemini = "key").',
    'Selenium pool uses Firefox -- Geckodriver must be present at .venv/bin/geckodriver.',
    'The Argus Gateway at 172.16.128.144:8000 must be reachable on the internal network.',
    'FOFA camera discovery requires free account registration to obtain API credentials.',
    'DDG dork results are rate-limited; frequent searches may return fewer results.',
    'html { zoom: 1.33 } CSS rule affects vh calculations -- addressed with calc(100vh / 1.33) where needed.',
]:
    bullet(item, RED)


# ══════════════════════════════════════════════════════════════
# FINAL -- QUICK REFERENCE
# ══════════════════════════════════════════════════════════════
pdf.add_page(); set_bg(); pdf.set_y(16)
h1('Quick Reference')
rule(); pdf.ln(6)

h2('Routes', HEAD)
for route, desc in [
    ('GET  /',                    'Landing page'),
    ('GET  /login',               'Login form'),
    ('GET  /register',            'Registration form'),
    ('GET  /dashboard',           'Main investigation dashboard'),
    ('GET  /cameras',             'Camera sweep page'),
    ('GET  /logout',              'Clear session'),
    ('POST /api/investigate',     'Start investigation (username/email/phone)'),
    ('GET  /api/status/{id}',     'Poll investigation task status'),
    ('POST /api/camera-sweep',    'Start camera sweep (location, inv_id)'),
    ('GET  /api/camera-status/{id}','Poll camera sweep status'),
    ('GET  /api/graph/{inv_id}',  'Get graph JSON for D3 rendering'),
    ('GET  /api/node/{node_id}',  'Get node detail HTML partial'),
    ('GET  /api/report/{inv_id}', 'Download PDF report'),
]:
    pdf.set_x(14)
    pdf.set_font('Courier','',7.5); pdf.set_text_color(*CYAN)
    pdf.cell(78, 4.5, s(route), ln=False)
    pdf.set_font('Helvetica','',8); pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4.5, s(desc))

h2('Environment Variables (.env)', HEAD)
for var, desc in [
    ('gemini',      'Google Gemini API key for AI visual screening'),
    ('SHODAN_KEY',  'Shodan API key (optional, not currently used)'),
    ('FOFA_EMAIL',  'FOFA account email (optional, camera sweep supplement)'),
    ('FOFA_KEY',    'FOFA API key (optional, camera sweep supplement)'),
]:
    pdf.set_x(14); pdf.set_font('Courier','B',8); pdf.set_text_color(*ORNG)
    pdf.cell(38, 4.5, s(var), ln=False)
    pdf.set_font('Helvetica','',8); pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4.5, s(desc))

h2('Node Type Reference', HEAD)
pdf.set_x(14); pdf.set_font('Helvetica','B',7); pdf.set_text_color(*MUTED)
pdf.cell(32,4,'TYPE',ln=False); pdf.cell(22,4,'COLOR',ln=False)
pdf.cell(20,4,'RADIUS',ln=False); pdf.cell(0,4,'SOURCE',ln=True)
rule(); pdf.ln(1)
for ntype, color, radius, source in [
    ('username',    '#f1f5f9', 13, 'Input / derived'),
    ('platform',    '#a78bfa',  8, 'Maigret, Sherlock, Holehe'),
    ('email',       '#fbbf24',  9, 'Input / extracted'),
    ('phone',       '#f472b6', 10, 'Input'),
    ('location',    '#4ade80',  8, 'Maigret profiles'),
    ('ip',          '#f87171',  8, 'Maigret profiles'),
    ('domain',      '#34d399',  8, 'Maigret profiles'),
    ('dork_hub',    '#fb923c', 11, 'DuckDuckGo dork engine'),
    ('dork',        '#fb923c',  6, 'DuckDuckGo dork engine'),
    ('image_match', '#22d3ee',  7, 'Yandex / face / image search'),
    ('camera',      '#10b981', 10, 'Insecam / FOFA camera sweep'),
]:
    pdf.set_x(14)
    pdf.set_font('Helvetica','B',8); pdf.set_text_color(*TEXT)
    pdf.cell(32,4,s(ntype),ln=False)
    pdf.set_font('Courier','',7); pdf.set_text_color(*MUTED)
    pdf.cell(22,4,s(color),ln=False)
    pdf.cell(20,4,s(str(radius)+'px'),ln=False)
    pdf.set_font('Helvetica','',7)
    pdf.multi_cell(0,4,s(source))

pdf.ln(10)
rule((60,100,80))
pdf.ln(6)
pdf.set_font('Helvetica','B',7); pdf.set_text_color(*MUTED)
pdf.cell(0, 5, 'GOTHAM  ·  SOCMINT INTELLIGENCE PLATFORM  ·  INTERNAL DOCUMENTATION', align='C', ln=True)

out = '/home/cyber/Desktop/dev/CIDECODE/GOTHAM/GOTHAM_DOCUMENTATION.pdf'
pdf.output(out)
print(f'Written: {out}')
