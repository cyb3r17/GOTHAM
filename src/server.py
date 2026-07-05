from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
import sqlite3, hashlib, os, json, subprocess, tempfile, shutil, glob, re, csv, io, base64
import threading, uuid
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from urllib.parse import urlparse
from dotenv import load_dotenv
from ddgs import DDGS
from fpdf import FPDF
from google import genai
from PIL import Image
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

GECKODRIVER = os.path.join(os.path.dirname(__file__), '../.venv/bin/geckodriver')
CASES_DIR   = os.path.join(os.path.dirname(__file__), '../cases')
os.makedirs(CASES_DIR, exist_ok=True)

def case_dir(inv_id, sub=None):
    """Return (and create) the case folder, optionally a subfolder."""
    path = os.path.join(CASES_DIR, str(inv_id))
    if sub:
        path = os.path.join(path, sub)
    os.makedirs(path, exist_ok=True)
    return path

OSINT_API   = 'http://172.16.128.144:8000'
SHODAN_KEY  = os.environ.get('SHODAN_KEY', '')

_gemini_client = None
_gemini_lock   = threading.Lock()

def get_gemini():
    global _gemini_client
    with _gemini_lock:
        if _gemini_client is None:
            api_key = os.environ.get('GEMINI')
            if not api_key:
                return None
            _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = 'gotham-dev-key-change-in-prod'

_tasks = {}  # task_id -> {status, done, inv_id, count, error, username}

DB = os.path.join(os.path.dirname(__file__), '../gotham.db')

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS investigations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            owner      TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id     TEXT PRIMARY KEY,
            inv_id INTEGER NOT NULL,
            label  TEXT NOT NULL,
            type   TEXT NOT NULL,
            props  TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS edges (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            inv_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            label  TEXT
        );
        CREATE TABLE IF NOT EXISTS file_hashes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            inv_id     INTEGER NOT NULL,
            filename   TEXT NOT NULL,
            sha256     TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    db.commit()
    db.close()


def store_hash(inv_id, filename, data_bytes, sub=None):
    """Write data_bytes into the case folder, SHA-256 hash it, persist to DB. Returns hex digest."""
    digest = hashlib.sha256(data_bytes).hexdigest()
    # Write file into case subfolder
    dest = os.path.join(case_dir(inv_id, sub), filename)
    with open(dest, 'wb') as _f:
        _f.write(data_bytes)
    # Write SHA-256 sidecar
    with open(dest + '.sha256', 'w') as _hf:
        _hf.write(f'{digest}  {filename}\n')
    # Persist to DB
    db = get_db()
    db.execute('INSERT INTO file_hashes (inv_id, filename, sha256) VALUES (?,?,?)',
               (inv_id, filename, digest))
    db.commit()
    db.close()
    return digest

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return dec

# ── Maigret runner ────────────────────────────────────

VENV_PYTHON = os.path.join(os.path.dirname(__file__), '../.venv/bin/python')


_native_lib_path_cache = None

def _native_lib_path():
    """Collect 64-bit native lib dirs needed by compiled Python extensions on NixOS."""
    global _native_lib_path_cache
    if _native_lib_path_cache is not None:
        return _native_lib_path_cache

    existing = os.environ.get('LD_LIBRARY_PATH', '')
    dirs = set()
    try:
        result = subprocess.run(
            ['find', '/nix/store', '-maxdepth', '5', '(',
             '-name', 'libstdc++.so.6',
             '-o', '-name', 'libz.so.1',
             '-o', '-name', 'libzstd.so.1', ')'],
            capture_output=True, text=True, timeout=20
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip paths from fhsenv sandboxes (onlyoffice, arduino, etc.)
            if 'fhsenv' in line:
                continue
            # Skip 32-bit ELF files (byte 4 of ELF header: 1=32-bit, 2=64-bit)
            try:
                with open(line, 'rb') as fh:
                    if fh.read(5)[4] != 2:
                        continue
            except Exception:
                continue
            dirs.add(os.path.dirname(line))
    except Exception:
        pass

    all_paths = ':'.join(sorted(dirs, key=len))
    _native_lib_path_cache = f'{all_paths}:{existing}' if existing else all_paths
    return _native_lib_path_cache

def run_maigret(usernames):
    """Run maigret against a list of usernames, merge all JSON results."""
    if isinstance(usernames, str):
        usernames = [usernames]
    outdir = tempfile.mkdtemp(prefix='gotham_')
    try:
        env = os.environ.copy()
        env['LD_LIBRARY_PATH'] = _native_lib_path()
        result = subprocess.run(
            [VENV_PYTHON, '-m', 'maigret'] + usernames +
            ['--json', 'simple', '--folderoutput', outdir,
             '--no-progressbar',
             '--timeout', '5', '--retries', '1',
             '--cloudflare-bypass'],
            capture_output=True, text=True, timeout=120, env=env
        )
        merged = {}
        for fname in os.listdir(outdir):
            if fname.endswith('.json'):
                with open(os.path.join(outdir, fname)) as f:
                    merged.update(json.load(f))
        return merged
    except FileNotFoundError:
        return {'_error': 'maigret not found — run: pip install maigret'}
    except subprocess.TimeoutExpired:
        return {'_error': 'maigret timed out'}
    except Exception as e:
        return {'_error': str(e)}
    finally:
        shutil.rmtree(outdir, ignore_errors=True)

SHERLOCK_DIR = os.path.join(os.path.dirname(__file__), '../sherlock')


def run_sherlock(username):
    """Run sherlock against a username, return dict of {site_name: url}."""
    outdir = tempfile.mkdtemp(prefix='gotham_sherlock_')
    try:
        env = os.environ.copy()
        env['LD_LIBRARY_PATH'] = _native_lib_path()
        subprocess.run(
            [VENV_PYTHON, '-m', 'sherlock_project', username,
             '--local', '--csv', '--print-found',
             '--timeout', '10',
             '--folderoutput', outdir],
            capture_output=True, text=True, timeout=180, env=env,
            cwd=SHERLOCK_DIR
        )
        found = {}
        csv_path = os.path.join(outdir, f'{username}.csv')
        if os.path.exists(csv_path):
            with open(csv_path, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    if str(row.get('exists', '')).lower() == 'claimed':
                        found[row['name']] = row.get('url_user', '')
        return found
    except subprocess.TimeoutExpired:
        return {'_error': 'sherlock timed out'}
    except Exception as e:
        return {'_error': str(e)}
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def add_sherlock_nodes(inv_id, username, sherlock_data):
    """Merge sherlock-found platforms into an existing graph (no clear)."""
    if not isinstance(sherlock_data, dict) or '_error' in sherlock_data:
        return 0
    db = get_db()
    uid = _nid('u', username)
    count = 0
    for site_name, url in sherlock_data.items():
        if site_name.lower() in _PLATFORM_BLACKLIST:
            continue
        if _is_blacklisted_url(url):
            continue
        plat_id = _nid('p', site_name)
        existing = db.execute('SELECT id FROM nodes WHERE id=?', (plat_id,)).fetchone()
        if existing:
            continue  # already added by maigret
        db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                   (plat_id, inv_id, site_name, 'platform',
                    json.dumps({'url': url, 'source': 'sherlock'})))
        if not db.execute('SELECT 1 FROM edges WHERE inv_id=? AND source=? AND target=?',
                          (inv_id, uid, plat_id)).fetchone():
            db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                       (inv_id, uid, plat_id, 'found on'))
        count += 1
    db.commit()
    db.close()
    return count


# ── External OSINT providers ──────────────────────────

_JSON_HDR = {'Content-Type': 'application/json'}


def _argus_post(path, payload, timeout=30):
    """POST JSON to Argus API, return unwrapped results list."""
    try:
        r = requests.post(
            f'{OSINT_API}{path}',
            headers=_JSON_HDR,
            data=json.dumps(payload),
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        # All Argus endpoints return ServiceResponse: {results:[...], provenance:{}, errors:[]}
        results = data.get('results', data) if isinstance(data, dict) else data
        if not isinstance(results, list):
            results = [results] if results else []
        print(f'[API] {path} → {len(results)} results', flush=True)
        return results
    except Exception as e:
        print(f'[API] {path} error: {e}', flush=True)
        return []


def _argus_post_file(path, file_bytes, filename='image.jpg', mime='image/jpeg', params=None):
    """POST multipart file to Argus API, return unwrapped results list."""
    try:
        r = requests.post(
            f'{OSINT_API}{path}',
            params=params or {},
            files={'file': (filename, file_bytes, mime)},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        if not isinstance(results, list):
            results = [results] if results else []
        print(f'[API] {path} → {len(results)} results', flush=True)
        return results
    except Exception as e:
        print(f'[API] {path} error: {e}', flush=True)
        return []


def run_holehe(email):
    return _argus_post('/providers/holehe/search', {'email': email})

def run_moriarty(phone):
    results = _argus_post('/providers/moriarty/lookup', {'phone': phone})
    # Moriarty returns a list of enrichment objects; merge into one dict for the phone node
    merged = {}
    for item in results:
        if isinstance(item, dict):
            merged.update(item)
    return merged

def run_whatsapp(phone):
    results = _argus_post('/providers/whatsapp/check', {'number': phone})
    return results[0] if results and isinstance(results[0], dict) else {}

def run_telegram_channel(username):
    results = _argus_post('/providers/telegram/fetch', {'channels': [username]})
    # Results is a list of channel objects; key by channel name
    out = {}
    for item in results:
        if isinstance(item, dict):
            ch = item.get('channel') or item.get('name') or username
            out[ch] = item
    return out

def run_yandex_image(image_bytes):
    return _argus_post_file('/providers/yandeximage/search', image_bytes, params={'top_n': 5})

def run_face_search(image_bytes):
    return _argus_post_file('/face/search', image_bytes, params={'limit': 5})

def run_image_search(image_bytes):
    return _argus_post_file('/image/search', image_bytes, params={'limit': 5})


def add_holehe_nodes(inv_id, username, email, holehe_data):
    """Add holehe platform hits as nodes connected to the email node."""
    if not holehe_data:
        return 0
    db  = get_db()
    uid = _nid('u', username)
    em_id = _nid('e', email)
    # Ensure email node exists
    if not db.execute('SELECT 1 FROM nodes WHERE id=? AND inv_id=?', (em_id, inv_id)).fetchone():
        db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                   (em_id, inv_id, email, 'email', json.dumps({'source': 'input'})))
        db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                   (inv_id, uid, em_id, 'has email'))
    count = 0
    for site in holehe_data:
        if not isinstance(site, dict):
            continue
        name = (site.get('name') or site.get('platform') or site.get('site')
                or site.get('domain') or site.get('website') or '')
        if not name:
            continue
        registered = site.get('exists') or site.get('registered') or site.get('found')
        if not registered:
            continue
        url = site.get('url') or site.get('link') or ''
        if _is_blacklisted_url(url):
            continue
        # Build clean props — skip None/empty values
        extra = {k: v for k, v in site.items()
                 if k not in ('name', 'platform', 'site', 'domain', 'website', 'url', 'link',
                              'exists', 'registered', 'found', 'email')
                 and v is not None and str(v).strip() not in ('', 'None')}
        props = {'url': url, 'source': 'holehe', 'email': email, **extra}
        plat_id = _nid('p', f'holehe_{name}')
        if not db.execute('SELECT 1 FROM nodes WHERE id=? AND inv_id=?', (plat_id, inv_id)).fetchone():
            db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                       (plat_id, inv_id, name, 'platform', json.dumps(props)))
            db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                       (inv_id, em_id, plat_id, 'registered on'))
            count += 1
    db.commit()
    db.close()
    return count


def add_phone_nodes(inv_id, username, phone, moriarty_data, whatsapp_data):
    """Add phone node enriched with Moriarty + WhatsApp data."""
    db  = get_db()
    uid = _nid('u', username)
    ph_id = _nid('ph', phone)
    props = {'number': phone, 'source': 'input'}
    # Merge Moriarty data
    if isinstance(moriarty_data, dict):
        for k, v in moriarty_data.items():
            if k not in ('error', '_error') and v not in (None, '', 'None'):
                props[k] = v
    # Merge WhatsApp data
    wa = whatsapp_data if isinstance(whatsapp_data, dict) else {}
    props['whatsapp'] = str(wa.get('registered') or wa.get('exists') or wa.get('found') or False)
    db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
               (ph_id, inv_id, phone, 'phone', json.dumps(props)))
    db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
               (inv_id, uid, ph_id, 'has phone'))
    db.commit()
    db.close()
    return 1


def add_telegram_nodes(inv_id, username, tg_data):
    """Add a Telegram platform node if the channel exists."""
    if not tg_data:
        return 0
    # Response might be {channel: {messages: [...], info: {...}}} or similar
    channels = tg_data if isinstance(tg_data, dict) else {}
    if not channels:
        return 0
    db  = get_db()
    uid = _nid('u', username)
    count = 0
    for ch_name, ch_data in channels.items():
        if not isinstance(ch_data, dict):
            continue
        info = ch_data.get('info') or ch_data.get('channel') or {}
        if not info and not ch_data.get('messages'):
            continue  # empty channel = not found
        title = (info.get('title') or info.get('name') or ch_name) if isinstance(info, dict) else ch_name
        url   = f'https://t.me/{ch_name}'
        msgs  = ch_data.get('messages', [])
        props = {'url': url, 'source': 'telegram', 'messages': str(len(msgs))}
        if isinstance(info, dict):
            for k in ('description', 'members', 'username'):
                if info.get(k):
                    props[k] = str(info[k])
        plat_id = _nid('p', f'tg_{ch_name}')
        db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                   (plat_id, inv_id, title, 'platform',
                    json.dumps(props)))
        db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                   (inv_id, uid, plat_id, 'found on'))
        count += 1
    db.commit()
    db.close()
    return count


def run_yandex_on_avatars(inv_id, username):
    """Find avatar URLs in platform nodes, run Yandex reverse image search."""
    _IMG_KEYS = {'image', 'avatar', 'avatar_url', 'photo', 'picture', 'profile_image', 'profile_picture'}
    db = get_db()
    nodes = db.execute(
        "SELECT props FROM nodes WHERE inv_id=? AND type='platform'", (inv_id,)
    ).fetchall()
    db.close()

    avatar_urls = []
    for n in nodes:
        props = json.loads(n['props'])
        for k, v in props.items():
            if k.lower() in _IMG_KEYS and isinstance(v, str) and v.startswith('http'):
                avatar_urls.append(v)
                break

    if not avatar_urls:
        return 0

    # Use first unique avatar found
    avatar_url = avatar_urls[0]
    try:
        img_bytes = requests.get(avatar_url, timeout=10).content
    except Exception:
        return 0

    # Run all three image intelligence providers in parallel
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_yandex = ex.submit(run_yandex_image, img_bytes)
        f_face   = ex.submit(run_face_search,  img_bytes)
        f_img    = ex.submit(run_image_search, img_bytes)
        yandex_matches = f_yandex.result()
        face_matches   = f_face.result()
        img_matches    = f_img.result()

    db  = get_db()
    uid = _nid('u', username)
    count = 0

    def _insert_image_match(m, source):
        nonlocal count
        if not isinstance(m, dict):
            return
        url   = m.get('url') or m.get('link') or m.get('source_url') or m.get('page_url') or ''
        title = m.get('title') or m.get('description') or m.get('name') or url[:60]
        score = m.get('score') or m.get('similarity') or m.get('distance') or ''
        if not url or _is_blacklisted_url(url):
            return
        try:
            domain = urlparse(url).netloc.lower().lstrip('www.')
        except Exception:
            return
        nid = _nid(f'imgmatch_{source}', domain)
        if db.execute('SELECT 1 FROM nodes WHERE id=? AND inv_id=?', (nid, inv_id)).fetchone():
            return
        props = {'url': url, 'source': source, 'domain': domain}
        if score:
            props['score'] = str(score)
        db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                   (nid, inv_id, title[:80], 'image_match', json.dumps(props)))
        db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                   (inv_id, uid, nid, 'image found on'))
        count += 1

    for m in yandex_matches: _insert_image_match(m, 'yandex')
    for m in face_matches:   _insert_image_match(m, 'face_search')
    for m in img_matches:    _insert_image_match(m, 'image_search')

    db.commit()
    db.close()
    return count


# ── Dorking ───────────────────────────────────────────

_DORK_QUERIES = [
    # Username directly in URL — most reliable, catches profiles on any platform
    ('profile',    'inurl:{username}'),
    # Single-site queries only — DDG only enforces quoted username on the first site in an OR chain
    ('code',       '"{username}" site:github.com'),
    ('paste',      '"{username}" site:pastebin.com'),
    ('social',     '"{username}" site:reddit.com'),
    ('identity',   '"{username}" site:keybase.io'),
    ('writing',    '"{username}" site:medium.com'),
    ('gaming',     '"{username}" site:steamcommunity.com'),
]

# Platforms permanently banned from appearing anywhere in the graph
_PLATFORM_BLACKLIST = {
    'figma', 'xing', 'mastodon.cloud',
}

def _is_blacklisted_url(url: str) -> bool:
    """Return True if the URL should be permanently excluded."""
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower().lstrip('www.')
    except Exception:
        host = url.lower()
    if host.endswith('.ru') or '.ru/' in url.lower():
        return True
    return False

_DORK_SKIP_DOMAINS = {
    'twitter.com', 'x.com', 'instagram.com', 'facebook.com', 'tiktok.com',
    'youtube.com', 'linkedin.com', 'twitch.tv', 'discord.com', 'telegram.org',
    'snapchat.com', 'figma.com', 'xing.com', 'mastodon.cloud',
}


def run_dorks(username):
    import time
    seen_domains = set()
    results = []
    needle = username.lower()
    try:
        ddgs = DDGS()
        for category, query_tpl in _DORK_QUERIES:
            query = query_tpl.format(username=username)
            try:
                hits = list(ddgs.text(query, max_results=8))
                print(f'[DORK] {category}: {len(hits)} raw hits', flush=True)
                for r in hits:
                    url = r.get('href') or r.get('link', '')
                    if not url:
                        continue
                    domain = urlparse(url).netloc.lower().lstrip('www.')
                    if (domain in _DORK_SKIP_DOMAINS or domain in seen_domains
                            or domain.endswith('.ru') or _is_blacklisted_url(url)):
                        continue
                    title   = r.get('title', '')
                    snippet = r.get('body', '')
                    haystack = (url + title + snippet).lower()
                    if needle not in haystack:
                        print(f'[DORK]   skip (no needle): {url[:80]}', flush=True)
                        continue
                    # For profile inurl: queries, username must be a complete URL path segment
                    # (prevents inurl:kaz matching lesswrong.com/posts/kazlauskas)
                    if category == 'profile':
                        try:
                            segments = [s.lstrip('@') for s in urlparse(url).path.lower().split('/') if s]
                            if needle not in segments:
                                print(f'[DORK]   skip (not segment): {url[:80]}', flush=True)
                                continue
                        except Exception:
                            continue
                    entry = {
                        'title':    title[:120],
                        'url':      url,
                        'snippet':  snippet[:300],
                        'query':    query,
                        'domain':   domain,
                        'category': category,
                    }
                    seen_domains.add(domain)
                    results.append(entry)
                    if len(results) >= 35:
                        return results
            except Exception as e:
                print(f'[DORK] {category} ERROR: {e}', flush=True)
            time.sleep(0.8)
    except Exception as e:
        print(f'[DORK] outer ERROR: {e}', flush=True)
    print(f'[DORK] total kept: {len(results)}', flush=True)
    return results


def add_dork_nodes(inv_id, username, dork_results):
    if not dork_results:
        return 0
    db  = get_db()
    uid = _nid('u', username)

    # IDs are scoped with inv_id so they don't collide across investigations
    hub_id = _nid(f'dh_{inv_id}', username)
    if not db.execute('SELECT 1 FROM nodes WHERE id=? AND inv_id=?', (hub_id, inv_id)).fetchone():
        db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                   (hub_id, inv_id, 'Dork Intelligence', 'dork_hub',
                    json.dumps({'username': username})))
        db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                   (inv_id, uid, hub_id, 'dork cluster'))

    count = 0
    for r in dork_results:
        nid = _nid(f'd_{inv_id}', r['domain'])
        if db.execute('SELECT 1 FROM nodes WHERE id=? AND inv_id=?', (nid, inv_id)).fetchone():
            continue
        db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                   (nid, inv_id, r['title'], 'dork',
                    json.dumps({'url': r['url'], 'snippet': r['snippet'],
                                'query': r['query'], 'domain': r['domain'],
                                'category': r['category']})))
        db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                   (inv_id, hub_id, nid, r['category']))
        count += 1

    db.commit()
    db.close()
    return count




_CLASSIFY_PROMPT = """\
You are an OSINT analyst reviewing a profile page screenshot.

Platform: {platform}
URL: {url}
Searched username: {username}

Examine the screenshot and determine whether this is a genuine, active account for the username "{username}".

Respond with ONLY a JSON object — no markdown, no explanation — in this exact format:
{{"active": true, "confidence": "high", "reason": "Profile exists with recent activity", "category": "active_profile"}}

Rules:
- active: true if a real user profile for this username exists and is visible
- active: false if it is a login wall, error page, empty/deleted account, wrong user, or unrelated page
- confidence: "high" | "medium" | "low"
- category: one of "active_profile" | "login_wall" | "error_page" | "wrong_user" | "empty_profile" | "unrelated"
- reason: one sentence, plain text
"""

BROWSER_POOL_SIZE = 3

def _make_driver():
    opts = FirefoxOptions()
    opts.add_argument('--headless')
    opts.add_argument('--width=1280')
    opts.add_argument('--height=800')
    svc = FirefoxService(executable_path=GECKODRIVER, log_output='/dev/null')
    d = webdriver.Firefox(service=svc, options=opts)
    d.set_page_load_timeout(10)
    return d


def _classify_screenshot(gclient, platform, url, username, png_bytes):
    """Send screenshot to Gemini, return classification dict."""
    try:
        img = Image.open(io.BytesIO(png_bytes))
        prompt = _CLASSIFY_PROMPT.format(platform=platform, url=url, username=username)
        resp = gclient.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img],
        )
        text = resp.text.strip().lstrip('`').rstrip('`')
        if text.startswith('json'):
            text = text[4:].strip()
        return json.loads(text)
    except Exception:
        return {'active': True, 'confidence': 'low', 'reason': 'classification failed', 'category': 'unknown'}


def ai_screen_nodes(inv_id, username):
    """Screenshot platform URLs via a reusable browser pool, ask Gemini, remove duds."""
    gclient = get_gemini()  # may be None — screenshots still taken regardless

    db = get_db()
    nodes = db.execute(
        "SELECT id, label, props FROM nodes WHERE inv_id=? AND type='platform' LIMIT 25",
        (inv_id,)
    ).fetchall()
    db.close()

    if not nodes:
        return 0

    import queue as _queue
    pool = _queue.Queue()

    drivers = []
    for _ in range(min(BROWSER_POOL_SIZE, len(nodes))):
        try:
            d = _make_driver()
            drivers.append(d)
            pool.put(d)
        except Exception:
            pass

    if not drivers:
        return 0

    to_remove = []

    def check(node):
        props = json.loads(node['props'])
        url   = props.get('url', '')
        if not url or not url.startswith('http'):
            return None
        driver = pool.get()
        try:
            driver.get(url)
            import time as _time; _time.sleep(2.5)  # let JS render before capture
            png = driver.get_screenshot_as_png()
        except Exception:
            png = None
        finally:
            pool.put(driver)
        if png is None:
            return None
        # Always persist screenshot for PDF regardless of Gemini
        try:
            _fname = f'{node["id"]}.png'
            store_hash(inv_id, _fname, png, sub='screenshots')
        except Exception:
            pass
        if not gclient:
            return None
        result = _classify_screenshot(gclient, node['label'], url, username, png)
        if not result.get('active', True) and result.get('confidence') in ('high', 'medium'):
            return node['id']
        return None

    try:
        with ThreadPoolExecutor(max_workers=BROWSER_POOL_SIZE) as ex:
            for nid in ex.map(check, nodes):
                if nid:
                    to_remove.append(nid)
    finally:
        for d in drivers:
            try:
                d.quit()
            except Exception:
                pass

    if to_remove:
        db = get_db()
        for nid in to_remove:
            db.execute('DELETE FROM nodes WHERE id=?', (nid,))
            db.execute('DELETE FROM edges WHERE inv_id=? AND (source=? OR target=?)',
                       (inv_id, nid, nid))
        db.commit()
        db.close()

    return len(to_remove)


_VERIFY_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
}

def _url_exists(url, timeout=5):
    """Return False only if the URL definitively 404s. All other outcomes keep the node."""
    if not url or not url.startswith('http'):
        return True
    try:
        r = requests.head(url, timeout=timeout, headers=_VERIFY_HEADERS,
                          allow_redirects=True)
        if r.status_code == 405:
            r = requests.get(url, timeout=timeout, headers=_VERIFY_HEADERS, stream=True)
            r.close()
        return r.status_code != 404
    except Exception:
        return True  # timeout / connection error → keep node


def verify_nodes(inv_id):
    """Send HTTP checks to all platform URLs; remove nodes that 404."""
    db = get_db()
    nodes = db.execute(
        "SELECT id, props FROM nodes WHERE inv_id=? AND type='platform'",
        (inv_id,)
    ).fetchall()
    db.close()

    to_remove = []

    def check(node):
        props = json.loads(node['props'])
        url = props.get('url', '')
        if not url:
            return None
        return node['id'] if not _url_exists(url) else None

    with ThreadPoolExecutor(max_workers=40) as ex:
        futures = [ex.submit(check, n) for n in nodes]
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                to_remove.append(result)

    if to_remove:
        db = get_db()
        for nid in to_remove:
            db.execute('DELETE FROM nodes WHERE id=?', (nid,))
            db.execute('DELETE FROM edges WHERE inv_id=? AND (source=? OR target=?)',
                       (inv_id, nid, nid))
        db.commit()
        db.close()

    return len(to_remove)


FOFA_EMAIL = os.environ.get('FOFA_EMAIL', '')
FOFA_KEY   = os.environ.get('FOFA_KEY', '')

_cam_tasks = {}

# ── Camera sweep helpers ───────────────────────────────

def _insecam_cameras(country_code=None, city=None, max_pages=3):
    """Scrape Insecam camera index by country code or city name."""
    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0'}
    pages = []
    if city:
        for p in range(1, max_pages + 1):
            pages.append(f'https://www.insecam.org/en/bycity/{city}/?page={p}')
    else:
        cc = (country_code or 'US').upper()
        for p in range(1, max_pages + 1):
            pages.append(f'https://www.insecam.org/en/bycountry/{cc}/?page={p}')

    # Also search tag pages that cover webcams globally
    if city:
        pages.append(f'https://www.insecam.org/en/bytag/{city}/?page=1')

    # Patterns: Insecam embeds camera IPs as img src="http://IP:PORT/..."
    ip_src  = re.compile(r'src=["\']?(http://(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::(\d+))?(/[^"\'>\s]*)?)["\']?')
    seen    = set()
    cameras = []

    for url in pages:
        try:
            r = requests.get(url, headers=headers, timeout=12, verify=False)
            if r.status_code != 200:
                continue
            for m in ip_src.finditer(r.text):
                stream_url = m.group(1)
                ip         = m.group(2)
                port       = int(m.group(3) or 80)
                key        = f'{ip}:{port}'
                if key in seen:
                    continue
                seen.add(key)
                cameras.append({'ip': ip, 'port': port, 'stream_url': stream_url, 'source': 'insecam'})
            print(f'[CAMERA] insecam {url} → {len(cameras)} total', flush=True)
        except Exception as e:
            print(f'[CAMERA] insecam scrape error: {e}', flush=True)

    return cameras


def _fofa_cameras(query_str, max_results=50):
    """Query FOFA API for camera results (requires FOFA_EMAIL + FOFA_KEY env vars)."""
    if not FOFA_EMAIL or not FOFA_KEY:
        return []
    try:
        q_b64 = base64.b64encode(query_str.encode()).decode()
        url   = (f'https://fofa.info/api/v1/search/all?email={FOFA_EMAIL}'
                 f'&key={FOFA_KEY}&qbase64={q_b64}&size={max_results}&fields=ip,port,city,country')
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        cameras = []
        for row in data.get('results', []):
            ip, port, city, country = (row + ['', '', '', ''])[:4]
            cameras.append({'ip': ip, 'port': int(port or 80),
                            'city': city, 'country': country, 'source': 'fofa'})
        print(f'[CAMERA] FOFA → {len(cameras)} cameras', flush=True)
        return cameras
    except Exception as e:
        print(f'[CAMERA] FOFA error: {e}', flush=True)
        return []


def _get_camera_snapshot(ip, port, stream_url=None, timeout=5):
    """Try to pull a JPEG frame from a camera. Returns (bytes, url) or (None, None)."""
    headers  = {'User-Agent': 'Mozilla/5.0'}
    base     = f'http://{ip}:{port}'
    candidates = []
    if stream_url:
        candidates.append(stream_url)
    candidates += [
        f'{base}/snapshot.jpg', f'{base}/jpg/image.jpg', f'{base}/image.jpg',
        f'{base}/snap.jpg',     f'{base}/video.jpg',      f'{base}/cgi-bin/snapshot.cgi',
        f'{base}/cgi-bin/currentpicture.cgi', f'{base}/mjpg/snapshot.cgi',
        f'{base}/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2', f'{base}/',
    ]
    for url in candidates:
        try:
            r = requests.get(url, timeout=timeout, headers=headers)
            ct      = r.headers.get('content-type', '')
            content = r.content
            # Accept JPEG magic bytes OR image content-type
            if len(content) > 2000 and ('image' in ct or content[:3] == b'\xff\xd8\xff'):
                return content, url
        except Exception:
            continue
    return None, None


def _detect_faces(img_bytes):
    """Call Argus /face/detect. Returns list of face objects."""
    try:
        r = requests.post(f'{OSINT_API}/face/detect',
                          files={'file': ('frame.jpg', img_bytes, 'image/jpeg')}, timeout=20)
        r.raise_for_status()
        return r.json().get('results', [])
    except Exception as e:
        print(f'[CAMERA] face/detect error: {e}', flush=True)
        return []


def _face_search(img_bytes):
    """Call Argus /face/search. Returns matched identity results."""
    return _argus_post_file('/face/search', img_bytes, 'frame.jpg')


def _compare_faces(ref_bytes, cam_bytes):
    """Compare reference face to camera frame via Argus /face/compare. Returns float or None."""
    try:
        payload = {
            'image_a': base64.b64encode(ref_bytes).decode(),
            'image_b': base64.b64encode(cam_bytes).decode(),
        }
        r = requests.post(f'{OSINT_API}/face/compare', headers=_JSON_HDR,
                          data=json.dumps(payload), timeout=20)
        r.raise_for_status()
        results = r.json().get('results', [])
        if results:
            return results[0].get('similarity') or results[0].get('score')
    except Exception as e:
        print(f'[CAMERA] face/compare error: {e}', flush=True)
    return None


def _get_subject_avatar(inv_id):
    """Download the first usable avatar image from the investigation's platform nodes."""
    db    = get_db()
    nodes = db.execute("SELECT props FROM nodes WHERE inv_id=? AND type='platform'",
                       (inv_id,)).fetchall()
    db.close()
    img_keys = {'image','avatar','avatar_url','photo','picture','profile_image','profile_picture'}
    for n in nodes:
        for k, v in json.loads(n['props']).items():
            if k.lower() in img_keys and v and str(v).startswith('http'):
                try:
                    r = requests.get(str(v), timeout=8)
                    if r.status_code == 200 and len(r.content) > 500:
                        print(f'[CAMERA] subject avatar from {v}', flush=True)
                        return r.content
                except Exception:
                    continue
    return None


def add_camera_nodes(inv_id, sweep_results):
    """Insert camera nodes + face-hit nodes into the investigation graph."""
    db    = get_db()
    count = 0
    for cam in sweep_results:
        ip, port = cam['ip'], cam['port']
        cam_id   = _nid('cam', f'{ip}_{port}')
        cam_props = {k: v for k, v in {
            'ip':             ip,
            'port':           port,
            'url':            cam.get('stream_url', f'http://{ip}:{port}/'),
            'source':         cam.get('source', 'insecam'),
            'city':           cam.get('city', ''),
            'country':        cam.get('country', ''),
            'faces_detected': cam.get('faces_detected', 0),
        }.items() if v or v == 0}

        if not db.execute('SELECT 1 FROM nodes WHERE id=? AND inv_id=?',
                          (cam_id, inv_id)).fetchone():
            db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                       (cam_id, inv_id, f'{ip}:{port}', 'camera', json.dumps(cam_props)))
            count += 1

        # Each face search match → image_match node linked to camera
        for idx, match in enumerate(cam.get('face_matches', [])):
            label = (match.get('name') or match.get('title') or
                     match.get('url') or f'face_match_{idx}')[:80]
            fid   = _nid(f'cf_{cam_id}', str(idx))
            face_props = {'source': 'camera_face', 'camera': f'{ip}:{port}',
                          **{k: v for k, v in match.items()
                             if str(v).strip() not in ('', 'None')}}
            if not db.execute('SELECT 1 FROM nodes WHERE id=? AND inv_id=?',
                              (fid, inv_id)).fetchone():
                db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                           (fid, inv_id, label, 'image_match', json.dumps(face_props)))
                db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                           (inv_id, cam_id, fid, 'face found'))
                count += 1

        # If subject similarity is high, link camera directly to anchor username node
        sim = cam.get('subject_similarity')
        if sim and float(sim) > 0.55:
            anchor = db.execute(
                "SELECT id FROM nodes WHERE inv_id=? AND type='username' LIMIT 1",
                (inv_id,)).fetchone()
            if anchor:
                db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                           (inv_id, anchor['id'], cam_id,
                            f'seen on camera ({float(sim):.0%})'))

    db.commit()
    db.close()
    return count


def _run_camera_sweep_task(task_id, inv_id, location, owner):
    t = _cam_tasks[task_id]
    try:
        # ── Parse location ──────────────────────────────
        # Accepts: "IN" | "Bangalore" | "Bangalore,IN" | "Bangalore, India"
        country_code, city = None, None
        parts = [p.strip() for p in location.split(',')]
        if len(parts) >= 2:
            city         = parts[0]
            last         = parts[-1].strip()
            country_code = last.upper() if len(last) == 2 and last.isalpha() else None
        elif len(parts[0]) == 2 and parts[0].isalpha():
            country_code = parts[0].upper()
        else:
            city = parts[0]

        # ── Step 1: discover cameras ────────────────────
        t['status'] = f'Searching Insecam ({location})...'
        cameras = _insecam_cameras(country_code=country_code, city=city)

        # FOFA supplement (if key present)
        if not cameras or len(cameras) < 5:
            t['status'] = 'Trying FOFA...'
            fofa_q = f'camera=true'
            if city:
                fofa_q += f' && city="{city}"'
            if country_code:
                fofa_q += f' && country="{country_code}"'
            cameras += _fofa_cameras(fofa_q)

        print(f'[CAMERA] Total discovered: {len(cameras)}', flush=True)
        if not cameras:
            t.update({'done': True, 'count': 0,
                      'status': 'No cameras found for this location'})
            return

        # ── Step 2: get subject reference face ──────────
        t['status'] = 'Loading subject reference face...'
        ref_bytes = _get_subject_avatar(inv_id)

        # ── Step 3: snapshot + detect + match ───────────
        results = []
        limit   = min(len(cameras), 25)
        for i, cam in enumerate(cameras[:limit]):
            ip, port = cam['ip'], cam['port']
            t['status'] = f'Scanning {i+1}/{limit}: {ip}:{port}'

            img_bytes, snap_url = _get_camera_snapshot(ip, port, cam.get('stream_url'))

            if snap_url:
                cam['stream_url'] = snap_url

            face_matches       = []
            subject_similarity = None

            if img_bytes:
                try:
                    store_hash(inv_id, f'cam_{ip}_{port}.jpg', img_bytes, sub='cameras')
                except Exception:
                    pass
                faces = _detect_faces(img_bytes)
                cam['faces_detected'] = len(faces)
                print(f'[CAMERA] {ip}:{port} → {len(faces)} face(s)', flush=True)
                if faces:
                    face_matches = _face_search(img_bytes)
                    if ref_bytes:
                        subject_similarity = _compare_faces(ref_bytes, img_bytes)
                        if subject_similarity:
                            print(f'[CAMERA] {ip}:{port} sim={subject_similarity:.3f}', flush=True)
            else:
                cam['faces_detected'] = 0
                print(f'[CAMERA] {ip}:{port} → no frame, showing anyway', flush=True)

            cam['face_matches']       = face_matches
            cam['subject_similarity'] = subject_similarity
            results.append(cam)

        # ── Step 4: write to graph ──────────────────────
        t['status'] = 'Adding nodes to investigation graph...'
        count = add_camera_nodes(inv_id, results)
        t.update({'done': True, 'count': count, 'results': results})

    except Exception as e:
        import traceback; traceback.print_exc()
        t.update({'done': True, 'error': str(e)})


def _nid(prefix, value):
    return f'{prefix}_{re.sub(r"[^a-z0-9]", "_", str(value).lower())[:60]}'

def build_graph(inv_id, username, maigret_data):
    db = get_db()
    db.execute('DELETE FROM nodes WHERE inv_id=?', (inv_id,))
    db.execute('DELETE FROM edges WHERE inv_id=?', (inv_id,))

    def upsert_node(nid, label, ntype, props):
        db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                   (nid, inv_id, label, ntype, json.dumps(props)))

    def upsert_edge(src, tgt, label):
        if not db.execute('SELECT 1 FROM edges WHERE inv_id=? AND source=? AND target=? AND label=?',
                          (inv_id, src, tgt, label)).fetchone():
            db.execute('INSERT INTO edges (inv_id,source,target,label) VALUES (?,?,?,?)',
                       (inv_id, src, tgt, label))

    uid = _nid('u', username)
    upsert_node(uid, username, 'username', {})

    count = 0
    for site_name, site_data in maigret_data.items():
        if site_name.startswith('_') or not isinstance(site_data, dict):
            continue

        if site_name.lower() in _PLATFORM_BLACKLIST:
            continue

        status_obj = site_data.get('status', {})
        status = status_obj.get('status', '') if isinstance(status_obj, dict) else str(status_obj)
        if str(status).lower() not in ('claimed', 'found'):
            continue

        url  = site_data.get('url_user') or (status_obj.get('url', '') if isinstance(status_obj, dict) else '')
        if _is_blacklisted_url(url):
            continue
        rank = site_data.get('rank', 0)
        tags = status_obj.get('tags', []) if isinstance(status_obj, dict) else []
        ids  = {k: v for k, v in (status_obj.get('ids', {}) if isinstance(status_obj, dict) else {}).items()
                if not k.startswith('_')}

        props = {'url': url, 'rank': rank}
        if tags:
            props['tags'] = ', '.join(tags)
        props.update(ids)

        # Determine which username this result belongs to
        result_user = site_data.get('username', username)
        src_id = uid if result_user == username else _nid('u', result_user)
        if src_id != uid:
            upsert_node(src_id, result_user, 'username', {'variation': True})
            upsert_edge(uid, src_id, 'has username')

        plat_id = _nid('p', site_name)
        upsert_node(plat_id, site_name, 'platform', props)
        upsert_edge(src_id, plat_id, 'found on')
        count += 1

        # Alternate usernames on the same platform
        for linked_user in (site_data.get('ids_usernames') or {}):
            if linked_user in (username, result_user):
                continue
            lu_id = _nid('u', linked_user)
            upsert_node(lu_id, linked_user, 'username', {'source': site_name})
            upsert_edge(src_id, lu_id, 'has username')

        # Domains linked from this platform's profile page
        seen = set()
        for link_url in (site_data.get('ids_links') or []):
            if not isinstance(link_url, str) or not link_url.startswith('http'):
                continue
            try:
                netloc = urlparse(link_url).netloc
            except Exception:
                netloc = link_url[:50]
            if not netloc or netloc in seen:
                continue
            seen.add(netloc)
            dom_id = _nid('d', netloc)
            upsert_node(dom_id, netloc, 'domain', {'url': link_url})
            upsert_edge(plat_id, dom_id, 'links to')

        # Emails extracted by this platform
        for v in ids.values():
            vs = str(v)
            if '@' in vs and '.' in vs and len(vs) < 100:
                em_id = _nid('e', vs)
                upsert_node(em_id, vs, 'email', {'source': site_name})
                upsert_edge(plat_id, em_id, 'has email')

        # Location extracted by this platform
        country = ids.get('country_code') or ids.get('country')
        if country and isinstance(country, str) and len(country) <= 50:
            loc_id = _nid('loc', country)
            upsert_node(loc_id, country, 'location', {'type': 'country'})
            upsert_edge(plat_id, loc_id, 'located in')

        city = ids.get('city') or ids.get('locale')
        if city and isinstance(city, str) and len(city) <= 80 and city != country:
            city_id = _nid('loc', city)
            upsert_node(city_id, city, 'location', {'type': 'city'})
            upsert_edge(plat_id, city_id, 'visited')

    db.commit()
    db.close()
    return count

# ── Auth ──────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', user=session.get('user'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username'].strip()
        p = request.form['password']
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE username=? AND password=?',
                         (u, hash_pw(p))).fetchone()
        db.close()
        if row:
            session['user'] = u
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form['username'].strip()
        p = request.form['password']
        try:
            db = get_db()
            db.execute('INSERT INTO users (username,password) VALUES (?,?)', (u, hash_pw(p)))
            db.commit()
            db.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already taken.')
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ── Dashboard ─────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    invs = db.execute(
        'SELECT * FROM investigations WHERE owner=? ORDER BY created_at DESC',
        (session['user'],)
    ).fetchall()
    db.close()
    return render_template('dashboard.html', user=session['user'], investigations=invs)

# ── HTMX: run investigation ───────────────────────────

@app.route('/api/investigate', methods=['POST'])
@login_required
def investigate():
    username = request.form.get('username', '').strip()
    email    = request.form.get('email', '').strip()
    phone    = request.form.get('phone', '').strip()
    if not username and not email and not phone:
        return '<span class="status-err">Enter at least a username, email, or phone.</span>', 400

    # Investigation name: prefer username, else email, else phone
    inv_name = username or email or phone

    # Anchor node label for providers that need a name (holehe/phone-only flows)
    anchor = username or email or phone

    db = get_db()
    db.execute('INSERT INTO investigations (name,owner) VALUES (?,?)',
               (inv_name, session['user']))
    db.commit()
    inv_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.close()

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        'status': 'Starting...', 'stage': 0,
        'done': False, 'inv_id': inv_id,
        'count': 0, 'error': None, 'username': anchor,
        'owner': session['user'],
    }

    def run():
        t = _tasks[task_id]
        try:
            t['status'] = 'Scanning OSINT providers'
            t['stage'] = 1

            with ThreadPoolExecutor(max_workers=8) as ex:
                f_maigret  = ex.submit(run_maigret,          username) if username else None
                f_sherlock = ex.submit(run_sherlock,          username) if username else None
                f_dorks    = ex.submit(run_dorks,             username) if username else None
                f_telegram = ex.submit(run_telegram_channel, username) if username else None
                f_holehe   = ex.submit(run_holehe,  email) if email else None
                f_moriarty = ex.submit(run_moriarty, phone) if phone else None
                f_whatsapp = ex.submit(run_whatsapp, phone) if phone else None

                data          = f_maigret.result()  if f_maigret  else {}
                sherlock_data = f_sherlock.result() if f_sherlock else {}
                dork_results  = f_dorks.result()    if f_dorks    else []
                tg_data       = f_telegram.result() if f_telegram else {}
                holehe_data   = f_holehe.result()   if f_holehe   else []
                moriarty_data = f_moriarty.result() if f_moriarty else {}
                whatsapp_data = f_whatsapp.result() if f_whatsapp else {}

            # Always ensure an anchor node exists in the graph
            db = get_db()
            anchor_id = _nid('u', anchor)
            if not db.execute('SELECT 1 FROM nodes WHERE id=? AND inv_id=?', (anchor_id, inv_id)).fetchone():
                db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)',
                           (anchor_id, inv_id, anchor, 'username', '{}'))
                db.commit()
            db.close()

            error = data.get('_error') if isinstance(data, dict) else None
            count = build_graph(inv_id, username, data) if username and not error else 0
            if error:
                t['error'] = error
            count += add_sherlock_nodes(inv_id, username, sherlock_data) if username else 0
            count += add_dork_nodes(inv_id, username, dork_results)      if username else 0
            count += add_telegram_nodes(inv_id, username, tg_data)       if username else 0
            if email:
                count += add_holehe_nodes(inv_id, anchor, email, holehe_data)
            if phone:
                count += add_phone_nodes(inv_id, anchor, phone, moriarty_data, whatsapp_data)

            t['status'] = f'Verifying {count} URLs'
            t['stage'] = 2
            removed = verify_nodes(inv_id)
            count = max(0, count - removed)

            t['status'] = f'AI screening {count} profiles'
            t['stage'] = 3
            ai_removed = ai_screen_nodes(inv_id, username)
            count = max(0, count - ai_removed)

            t['status'] = 'Reverse image search'
            img_found = run_yandex_on_avatars(inv_id, username)
            count += img_found

            t.update({'done': True, 'count': count, 'stage': 4})
        except Exception as e:
            t.update({'done': True, 'error': str(e), 'stage': 3})

    threading.Thread(target=run, daemon=True).start()
    return render_template('partials/run_polling.html',
                           task_id=task_id, username=username)


@app.route('/api/status/<task_id>')
@login_required
def task_status(task_id):
    task = _tasks.get(task_id)
    if not task:
        return '<span class="status-err">Task not found.</span>', 404

    if not task['done']:
        return render_template('partials/run_polling.html',
                               task_id=task_id,
                               username=task['username'],
                               status=task['status'],
                               stage=task['stage'])

    # Done — build final response
    inv_id   = task['inv_id']
    count    = task['count']
    error    = task['error']
    username = task['username']
    owner    = task['owner']
    del _tasks[task_id]

    db = get_db()
    invs = db.execute(
        'SELECT * FROM investigations WHERE owner=? ORDER BY created_at DESC',
        (owner,)
    ).fetchall()
    db.close()
    inv_list_html = render_template('partials/inv_list.html',
                                    investigations=invs, active_id=inv_id)

    resp = make_response(render_template(
        'partials/run_status.html',
        username=username, count=count, error=error,
        inv_list_html=inv_list_html, inv_id=inv_id,
    ))
    resp.headers['HX-Trigger'] = json.dumps({'graphLoad': inv_id})
    return resp

# ── Camera sweep endpoints ────────────────────────────

@app.route('/cameras')
@login_required
def cameras_page():
    db   = get_db()
    invs = db.execute('SELECT * FROM investigations WHERE owner=? ORDER BY created_at DESC',
                      (session['user'],)).fetchall()
    db.close()
    return render_template('cameras.html', investigations=invs)


@app.route('/api/camera-sweep', methods=['POST'])
@login_required
def camera_sweep():
    location = request.form.get('location', '').strip()
    inv_id   = request.form.get('inv_id', '').strip()
    if not location:
        return '<span class="status-err">Enter a location.</span>', 400

    # Auto-create investigation if none selected
    if not inv_id:
        db = get_db()
        db.execute('INSERT INTO investigations (name,owner) VALUES (?,?)',
                   (f'Camera sweep: {location}', session['user']))
        db.commit()
        inv_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.close()
    else:
        inv_id = int(inv_id)

    task_id = str(uuid.uuid4())
    _cam_tasks[task_id] = {
        'done': False, 'status': 'Starting...', 'inv_id': inv_id,
        'count': 0, 'error': None, 'owner': session['user'], 'location': location,
        'results': [],
    }
    threading.Thread(
        target=_run_camera_sweep_task,
        args=(task_id, inv_id, location, session['user']),
        daemon=True
    ).start()
    return render_template('partials/camera_polling.html', task_id=task_id, location=location)


@app.route('/api/camera-status/<task_id>')
@login_required
def camera_status(task_id):
    t = _cam_tasks.get(task_id)
    if not t:
        return '<span class="status-err">Task not found.</span>', 404
    if not t['done']:
        return render_template('partials/camera_polling.html',
                               task_id=task_id, location=t['location'],
                               status=t.get('status', ''))
    results = t.get('results', [])
    count   = t['count']
    error   = t['error']
    inv_id  = t['inv_id']
    del _cam_tasks[task_id]
    if error:
        return f'<span class="status-err">Error: {error}</span>'
    # status strip gets the summary; results grid swapped out-of-band into #cam-results
    grid_html = render_template('partials/camera_results.html',
                                results=results, count=count, inv_id=inv_id)
    summary   = (f'<span class="status-ok">&#x2713; Sweep complete &mdash; '
                 f'{count} nodes added</span>'
                 f'<div id="cam-results" hx-swap-oob="true">{grid_html}</div>')
    return summary


# ── HTMX: node detail ─────────────────────────────────

@app.route('/api/node/<node_id>')
@login_required
def node_detail(node_id):
    db = get_db()
    node = db.execute('SELECT * FROM nodes WHERE id=?', (node_id,)).fetchone()
    connections = db.execute('''
        SELECT e.label AS rel,
               n.id    AS conn_id,
               n.label AS conn_label,
               n.type  AS conn_type
        FROM edges e
        JOIN nodes n ON n.id = CASE WHEN e.source=? THEN e.target ELSE e.source END
        WHERE e.source=? OR e.target=?
    ''', (node_id, node_id, node_id)).fetchall()
    db.close()
    if not node:
        return '<p>Not found</p>', 404
    props = json.loads(node['props'])
    return render_template('partials/node_detail.html',
                           node=node, props=props, connections=connections)

# ── JSON API for D3 ───────────────────────────────────

@app.route('/api/graph/<int:inv_id>')
@login_required
def graph_data(inv_id):
    db = get_db()
    nodes = db.execute('SELECT * FROM nodes WHERE inv_id=?', (inv_id,)).fetchall()
    edges = db.execute('SELECT * FROM edges WHERE inv_id=?', (inv_id,)).fetchall()
    db.close()
    def _node_dict(n):
        d = {'id': n['id'], 'label': n['label'], 'type': n['type']}
        if n['type'] in ('dork', 'dork_hub'):
            props = json.loads(n['props'])
            if 'category' in props:
                d['category'] = props['category']
        return d

    return jsonify({
        'nodes': [_node_dict(n) for n in nodes],
        'links': [{'source': e['source'], 'target': e['target'], 'label': e['label']} for e in edges],
    })

# ── Graph image renderer ──────────────────────────────

def _render_graph_png(nodes_data, edges_data, width=1200, height=780):
    """Fruchterman-Reingold spring layout rendered to a PIL Image."""
    import math, random
    NODE_COLORS = {
        'username': (228,226,218), 'platform': (138,150,120),
        'email':    (184,162,104), 'location': (120,144,120),
        'ip':       (170,112,112), 'domain':   (104,144,160),
        'dork_hub': (168,136, 72), 'dork':     (168,136, 72),
    }
    NODE_R = {'username':14,'platform':8,'email':10,'location':8,
              'ip':8,'domain':8,'dork_hub':12,'dork':5}
    img = Image.new('RGB', (width, height), (8, 8, 8))
    if not nodes_data:
        return img
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    random.seed(42)
    PAD = 0.08
    # Limit to 70 nodes for performance — username nodes always included
    priority = sorted(nodes_data, key=lambda n: (n['type'] != 'username', n['type'] == 'dork'))
    vis_nodes = priority[:70]
    vis_ids   = {n['id'] for n in vis_nodes}
    vis_edges = [e for e in edges_data if e['source'] in vis_ids and e['target'] in vis_ids]
    pos = {n['id']: [random.uniform(PAD,1-PAD), random.uniform(PAD,1-PAD)] for n in vis_nodes}
    k = math.sqrt(1.0 / max(len(vis_nodes), 1))
    ids = list(pos.keys())
    for it in range(80):
        disp = {nid: [0.0, 0.0] for nid in pos}
        for i, v in enumerate(ids):
            for u in ids[i+1:]:
                dx=pos[v][0]-pos[u][0]; dy=pos[v][1]-pos[u][1]
                d=max(math.sqrt(dx*dx+dy*dy),0.001); f=k*k/d
                disp[v][0]+=dx/d*f; disp[v][1]+=dy/d*f
                disp[u][0]-=dx/d*f; disp[u][1]-=dy/d*f
        for e in vis_edges:
            s,t=e['source'],e['target']
            dx=pos[s][0]-pos[t][0]; dy=pos[s][1]-pos[t][1]
            d=max(math.sqrt(dx*dx+dy*dy),0.001); f=d*d/k
            disp[s][0]-=dx/d*f; disp[s][1]-=dy/d*f
            disp[t][0]+=dx/d*f; disp[t][1]+=dy/d*f
        temp=0.15*(1-it/80)
        for nid in pos:
            d=max(math.sqrt(disp[nid][0]**2+disp[nid][1]**2),0.001)
            pos[nid][0]=min(1-PAD,max(PAD,pos[nid][0]+disp[nid][0]/d*min(d,temp)))
            pos[nid][1]=min(1-PAD,max(PAD,pos[nid][1]+disp[nid][1]/d*min(d,temp)))
    px = {nid:(int(p[0]*width),int(p[1]*height)) for nid,p in pos.items()}
    nm = {n['id']:n for n in vis_nodes}
    for e in vis_edges:
        if e['source'] in px and e['target'] in px:
            draw.line([px[e['source']],px[e['target']]], fill=(38,38,32), width=1)
    for nid,(x,y) in px.items():
        n=nm.get(nid,{}); ntype=n.get('type','platform')
        r=NODE_R.get(ntype,8); c=NODE_COLORS.get(ntype,(180,178,170))
        draw.ellipse([(x-r,y-r),(x+r,y+r)], fill=c)
    return img

# ── PDF Report ────────────────────────────────────────

@app.route('/api/report/<int:inv_id>')
@login_required
def download_report(inv_id):
    db = get_db()
    inv = db.execute('SELECT * FROM investigations WHERE id=? AND owner=?',
                     (inv_id, session['user'])).fetchone()
    if not inv:
        db.close()
        return 'Not found', 404

    nodes = db.execute('SELECT * FROM nodes WHERE inv_id=?', (inv_id,)).fetchall()
    edges = db.execute('SELECT * FROM edges WHERE inv_id=?', (inv_id,)).fetchall()
    db.close()

    by_type = {}
    for n in nodes:
        by_type.setdefault(n['type'], []).append(n)

    platforms   = by_type.get('platform', [])
    usernames   = by_type.get('username', [])
    emails      = by_type.get('email', [])
    locations   = by_type.get('location', [])
    domains     = by_type.get('domain', [])
    ips         = by_type.get('ip', [])
    dorks         = by_type.get('dork', [])
    phones        = by_type.get('phone', [])
    image_matches = by_type.get('image_match', [])

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)

    # ── Helpers ──────────────────────────────────────────────────
    BG     = (255, 255, 255)
    TEXT   = (18,  18,  24)
    MUTED  = (105, 105, 115)
    OLIVE  = (80,  105,  60)
    GREEN  = (30,  130,  70)
    YELLOW = (155, 115,  15)
    ORANGE = (185,  95,  20)
    RED    = (165,  50,  50)
    TEAL   = (25,  135, 115)
    ACCENT = (200, 200, 208)
    WHITE  = TEXT   # alias so existing cell calls still work

    def set_bg():
        pdf.set_fill_color(*BG)
        pdf.rect(0, 0, 210, 297, 'F')

    def rule(y=None, color=ACCENT):
        if y is None:
            y = pdf.get_y()
        pdf.set_draw_color(*color)
        pdf.line(14, y, 196, y)

    def _safe(text):
        return (str(text)
            .replace('\u2014', '--').replace('\u2013', '-')
            .replace('\u2018', "'").replace('\u2019', "'")
            .replace('\u201c', '"').replace('\u201d', '"')
            .replace('\u2026', '...').replace('\u00b7', '·')
            .encode('latin-1', errors='replace').decode('latin-1'))

    def heading(text, size=8, color=MUTED, gap=5):
        pdf.set_font('Helvetica', 'B', size)
        pdf.set_text_color(*color)
        pdf.cell(0, gap, _safe(text).upper(), ln=True)

    def body(text, size=9, color=WHITE, gap=5):
        pdf.set_font('Helvetica', '', size)
        pdf.set_text_color(*color)
        pdf.multi_cell(0, gap, _safe(text))

    def tag(label, color):
        pdf.set_font('Helvetica', 'B', 7)
        pdf.set_text_color(*color)
        r, g, b = color
        pdf.set_fill_color(r//6, g//6, b//6)
        pdf.cell(pdf.get_string_width(label) + 6, 5, label.upper(), fill=True, ln=False)
        pdf.cell(3, 5, '', ln=False)

    # ══════════════════════════════════════════════════════════════
    # PAGE 1 — COVER
    # ══════════════════════════════════════════════════════════════
    pdf.add_page()
    set_bg()

    pdf.set_y(60)
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, 'SOCMINT INTELLIGENCE REPORT', align='C', ln=True)
    pdf.ln(2)
    rule(pdf.get_y())
    pdf.ln(20)

    pdf.set_font('Helvetica', 'B', 52)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 18, 'GOTHAM', align='C', ln=True)

    pdf.ln(4)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, 'Open-Source Intelligence Platform', align='C', ln=True)

    pdf.ln(28)
    rule(pdf.get_y(), OLIVE)
    pdf.ln(14)

    # Subject block
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, 'SUBJECT', ln=True)
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 10, inv['name'], ln=True)
    pdf.ln(6)

    # Stats row
    stats = [
        ('PLATFORMS',  str(len(platforms))),
        ('USERNAMES',  str(len(usernames))),
        ('EMAILS',     str(len(emails))),
        ('PHONES',     str(len(phones))),
        ('DORK HITS',  str(len(dorks))),
        ('IMG MATCH',  str(len(image_matches))),
    ]
    col_w = 30
    pdf.set_x(14)
    for label, val in stats:
        pdf.set_font('Helvetica', 'B', 18)
        pdf.set_text_color(*OLIVE)
        pdf.cell(col_w, 9, val, ln=False)
    pdf.ln(9)
    pdf.set_x(14)
    for label, val in stats:
        pdf.set_font('Helvetica', 'B', 6)
        pdf.set_text_color(*MUTED)
        pdf.cell(col_w, 5, label, ln=False)
    pdf.ln(12)
    rule(pdf.get_y(), ACCENT)
    pdf.ln(8)

    # Meta
    import datetime
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, f'Generated  {datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC    ·    Analyst  {session["user"]}', ln=True)

    # ══════════════════════════════════════════════════════════════
    # PAGE 2 — PLATFORM INTELLIGENCE
    # ══════════════════════════════════════════════════════════════
    if platforms:
        pdf.add_page()
        set_bg()
        pdf.set_y(16)
        heading('Platform Intelligence', 14, WHITE, 8)
        rule(); pdf.ln(6)

        _SKIP = {'url', 'rank', 'tags', 'source', 'snippet', 'query', 'domain', 'variation'}
        _IMG  = {'image','avatar','avatar_url','photo','picture','profile_image','profile_picture'}

        for plat in sorted(platforms, key=lambda n: json.loads(n['props']).get('rank', 99999999)):
            props    = json.loads(plat['props'])
            url      = props.get('url', '')
            tags     = props.get('tags', '')
            rank     = props.get('rank', '')
            source   = props.get('source', 'maigret')
            rank_str = '' if not rank or int(rank) > 9_000_000_000_000_000 else f'#{int(rank):,}'
            meta     = {k: v for k, v in props.items()
                        if k not in _SKIP and k.lower() not in _IMG
                        and str(v).strip() and str(v) != 'None'}

            # ── Platform header bar ──
            pdf.set_x(14)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*TEXT)
            pdf.cell(100, 6, _safe(plat['label']), ln=False)

            # rank + tags on the right
            pdf.set_font('Helvetica', '', 7)
            pdf.set_text_color(*MUTED)
            right = '  '.join(filter(None, [rank_str, _safe(tags[:30]), source.upper()]))
            pdf.cell(0, 6, right, align='R', ln=True)

            # URL
            if url:
                pdf.set_x(14)
                pdf.set_font('Helvetica', '', 7)
                pdf.set_text_color(*OLIVE)
                pdf.cell(0, 4, _safe(url[:110]), ln=True)

            # Metadata fields — two per row
            if meta:
                items = list(meta.items())
                for i in range(0, len(items), 2):
                    pdf.set_x(14)
                    for k, v in items[i:i+2]:
                        vs = _safe(str(v))
                        label_w = 28
                        pdf.set_font('Helvetica', 'B', 6)
                        pdf.set_text_color(*MUTED)
                        pdf.cell(label_w, 4, _safe(k.upper()[:14]) + ':', ln=False)
                        pdf.set_font('Helvetica', '', 7)
                        pdf.set_text_color(*TEXT)
                        pdf.cell(57, 4, vs[:28], ln=False)
                    pdf.ln(4)

            rule(pdf.get_y(), ACCENT)
            pdf.ln(2)

    # ── Platform screenshots ─────────────────────────────────────
    _shot_files = []
    _shots_dir = case_dir(inv_id, 'screenshots')
    for _plat in platforms:
        _sp = os.path.join(_shots_dir, f'{_plat["id"]}.png')
        if os.path.exists(_sp):
            _shot_files.append((_plat['label'], _sp))

    if _shot_files:
        _SW = 85
        _PER_PAGE = 8  # 2 cols × 4 rows
        for _page_idx in range(0, len(_shot_files), _PER_PAGE):
            _page_shots = _shot_files[_page_idx:_page_idx + _PER_PAGE]
            pdf.add_page()
            set_bg()
            pdf.set_y(16)
            _page_num = _page_idx // _PER_PAGE + 1
            _total_pages = (len(_shot_files) + _PER_PAGE - 1) // _PER_PAGE
            _title = 'Platform Screenshots' if _total_pages == 1 else f'Platform Screenshots ({_page_num}/{_total_pages})'
            heading(_title, 14, WHITE, 8)
            rule(); pdf.ln(4)
            for _i, (_sname, _sp) in enumerate(_page_shots):
                _scol = _i % 2
                _srow = _i // 2
                _sx = 14 + _scol * (_SW + 8)
                _sy = 36 + _srow * 72
                try:
                    pdf.image(_sp, x=_sx, y=_sy, w=_SW)
                except Exception:
                    continue
                pdf.set_xy(_sx, _sy + 56)
                pdf.set_font('Helvetica', 'B', 6)
                pdf.set_text_color(*MUTED)
                pdf.cell(_SW, 4, _safe(_sname[:32]), align='C', ln=False)

    # ══════════════════════════════════════════════════════════════
    # PAGE — IDENTITY & ARTIFACTS
    # ══════════════════════════════════════════════════════════════
    pdf.add_page()
    set_bg()
    pdf.set_y(16)
    heading('Identity & Artifacts', 14, WHITE, 8)
    rule(); pdf.ln(6)

    _ART_SKIP = {'source', 'variation'}

    def _artifact_props_row(props_dict):
        """Render all extra props in a compact 2-per-row grid."""
        items = [(k, v) for k, v in props_dict.items()
                 if k not in _ART_SKIP and str(v).strip() and str(v) != 'None']
        for i in range(0, len(items), 2):
            pdf.set_x(22)
            for k2, v2 in items[i:i+2]:
                pdf.set_font('Helvetica', 'B', 6)
                pdf.set_text_color(*MUTED)
                pdf.cell(22, 3.5, _safe(k2.upper()[:12]) + ':')
                pdf.set_font('Helvetica', '', 7)
                pdf.set_text_color(*WHITE)
                pdf.cell(58, 3.5, _safe(str(v2))[:30])
            pdf.ln(3.5)

    # Alternate usernames — pill grid
    if len(usernames) > 1:
        heading('Alternate Usernames', 8, MUTED, 4)
        pdf.ln(1)
        col, col_w, cols = 14, 58, 3
        for idx, u in enumerate(usernames):
            x = 14 + (idx % cols) * col_w
            pdf.set_xy(x, pdf.get_y())
            pdf.set_fill_color(230, 230, 235)
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(*TEXT)
            pdf.cell(col_w - 4, 6, _safe(u['label'])[:24], fill=True, ln=False)
            if (idx + 1) % cols == 0:
                pdf.ln(7)
        if len(usernames) % cols != 0:
            pdf.ln(7)
        pdf.ln(3)

    # Emails — label + all props
    if emails:
        heading('Email Addresses', 8, MUTED, 4)
        pdf.ln(1)
        for e in emails:
            props = json.loads(e['props'])
            pdf.set_x(14)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*YELLOW)
            pdf.cell(0, 5, _safe(e['label']), ln=True)
            src = props.get('source', '')
            if src:
                pdf.set_x(22)
                pdf.set_font('Helvetica', '', 6)
                pdf.set_text_color(*MUTED)
                pdf.cell(0, 3, f'SOURCE: {_safe(src)}', ln=True)
            extra = {k: v for k, v in props.items() if k != 'source' and str(v).strip() and str(v) != 'None'}
            if extra:
                _artifact_props_row(extra)
            pdf.ln(2)
        pdf.ln(2)

    # Locations — all props per entry
    if locations:
        heading('Locations', 8, MUTED, 4)
        pdf.ln(1)
        for loc in locations:
            props = json.loads(loc['props'])
            pdf.set_x(14)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*GREEN)
            pdf.cell(0, 5, _safe(loc['label']), ln=True)
            extra = {k: v for k, v in props.items() if str(v).strip() and str(v) != 'None'}
            if extra:
                _artifact_props_row(extra)
            pdf.ln(2)
        pdf.ln(2)

    # IP Addresses
    if ips:
        heading('IP Addresses', 8, MUTED, 4)
        pdf.ln(1)
        for ip in ips:
            props = json.loads(ip['props'])
            pdf.set_x(14)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*RED)
            pdf.cell(0, 5, _safe(ip['label']), ln=True)
            extra = {k: v for k, v in props.items() if str(v).strip() and str(v) != 'None'}
            if extra:
                _artifact_props_row(extra)
            pdf.ln(2)
        pdf.ln(2)

    # Phone Numbers — moriarty enrichment + WhatsApp
    if phones:
        heading('Phone Numbers', 8, MUTED, 4)
        pdf.ln(1)
        PINK = (244, 114, 182)
        for ph in phones:
            props = json.loads(ph['props'])
            pdf.set_x(14)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*PINK)
            pdf.cell(0, 5, _safe(ph['label']), ln=True)
            extra = {k: v for k, v in props.items() if str(v).strip() and str(v) != 'None'}
            if extra:
                _artifact_props_row(extra)
            pdf.ln(2)
        pdf.ln(2)

    # Domains — compact list: domain | url
    if domains:
        heading('Linked Domains', 8, MUTED, 4)
        pdf.ln(1)
        for d in domains[:40]:
            props = json.loads(d['props'])
            url   = _safe(props.get('url', ''))
            pdf.set_x(14)
            pdf.set_font('Helvetica', 'B', 7)
            pdf.set_text_color(*TEAL)
            pdf.cell(52, 3.5, _safe(d['label'])[:35], ln=False)
            pdf.set_font('Helvetica', '', 6)
            pdf.set_text_color(*MUTED)
            pdf.cell(0, 3.5, url[:85], ln=True)
        pdf.ln(3)

    # ══════════════════════════════════════════════════════════════
    # PAGE 4 — DORK INTELLIGENCE (if any)
    # ══════════════════════════════════════════════════════════════
    if dorks:
        pdf.add_page()
        set_bg()
        pdf.set_y(16)
        heading('Dork Intelligence', 14, WHITE, 8)
        rule(); pdf.ln(6)

        CAT_COLORS = {
            'paste': RED, 'code': (96, 165, 250), 'breach': ORANGE,
            'forum': (192, 132, 252), 'social': (34, 211, 238),
            'professional': (56, 189, 248), 'web': MUTED, 'general': WHITE,
        }

        # summary strip: count per category
        cat_counts = {}
        for d in dorks:
            c = json.loads(d['props']).get('category', 'general')
            cat_counts[c] = cat_counts.get(c, 0) + 1
        pdf.set_x(14)
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            col = CAT_COLORS.get(cat, WHITE)
            pdf.set_font('Helvetica', 'B', 7)
            pdf.set_text_color(*col)
            pdf.cell(14, 4, cat.upper()[:6], ln=False)
            pdf.set_text_color(*MUTED)
            pdf.set_font('Helvetica', '', 7)
            pdf.cell(10, 4, f'×{cnt}', ln=False)
        pdf.ln(6)
        rule(pdf.get_y(), ACCENT); pdf.ln(4)

        for idx, d in enumerate(dorks):
            props   = json.loads(d['props'])
            cat     = props.get('category', 'general')
            col     = CAT_COLORS.get(cat, WHITE)
            url     = _safe(props.get('url', ''))
            snippet = _safe(props.get('snippet', ''))
            query   = _safe(props.get('query', ''))
            label   = _safe(d['label'])

            # Category pill + title
            pdf.set_x(14)
            pdf.set_fill_color(*[min(255, c + 220) for c in col])
            pdf.set_font('Helvetica', 'B', 6)
            pdf.set_text_color(*col)
            pdf.cell(20, 4, cat.upper()[:10], fill=True, ln=False)
            pdf.set_x(36)
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(*WHITE)
            pdf.cell(0, 4, label[:80], ln=True)

            # URL
            if url:
                pdf.set_x(14)
                pdf.set_font('Helvetica', '', 7)
                pdf.set_text_color(56, 189, 248)
                pdf.cell(0, 3.5, url[:100], ln=True)

            # Query used
            if query:
                pdf.set_x(14)
                pdf.set_font('Helvetica', 'I', 6)
                pdf.set_text_color(*MUTED)
                pdf.cell(12, 3.5, 'QUERY:', ln=False)
                pdf.set_font('Helvetica', '', 6)
                pdf.set_text_color(200, 160, 80)
                pdf.cell(0, 3.5, query[:100], ln=True)

            # Snippet — up to 3 lines (~280 chars)
            if snippet:
                pdf.set_x(14)
                pdf.set_font('Helvetica', '', 7)
                pdf.set_text_color(140, 140, 150)
                pdf.multi_cell(182, 3.5, snippet[:280])

            # thin separator
            pdf.ln(1)
            rule(pdf.get_y(), (220, 220, 225))
            pdf.ln(3)

    # ══════════════════════════════════════════════════════════════
    # PAGE — IMAGE INTELLIGENCE (yandex / face / reverse image)
    # ══════════════════════════════════════════════════════════════
    if image_matches:
        pdf.add_page()
        set_bg()
        pdf.set_y(16)
        heading('Image Intelligence', 14, WHITE, 8)
        rule(); pdf.ln(6)

        CYAN = (34, 211, 238)
        SRC_COLORS = {'yandex': ORANGE, 'face': RED, 'image': CYAN}

        # Group by source provider
        by_src = {}
        for im in image_matches:
            src = json.loads(im['props']).get('source', 'image')
            by_src.setdefault(src, []).append(im)

        # Summary strip
        pdf.set_x(14)
        for src, items in sorted(by_src.items()):
            col = SRC_COLORS.get(src, WHITE)
            pdf.set_font('Helvetica', 'B', 7)
            pdf.set_text_color(*col)
            pdf.cell(18, 4, src.upper()[:8], ln=False)
            pdf.set_text_color(*MUTED)
            pdf.set_font('Helvetica', '', 7)
            pdf.cell(10, 4, f'×{len(items)}', ln=False)
        pdf.ln(6)
        rule(pdf.get_y(), ACCENT); pdf.ln(4)

        for im in image_matches:
            props  = json.loads(im['props'])
            src    = props.get('source', 'image')
            col    = SRC_COLORS.get(src, WHITE)
            url    = _safe(props.get('url', ''))
            domain = _safe(props.get('domain', im['label']))
            score  = props.get('score', props.get('similarity', ''))
            title  = _safe(props.get('title', im['label']))

            # Source pill + title
            pdf.set_x(14)
            pdf.set_fill_color(*[min(255, c + 210) for c in col])
            pdf.set_font('Helvetica', 'B', 6)
            pdf.set_text_color(*col)
            pdf.cell(18, 4, src.upper()[:8], fill=True, ln=False)
            pdf.set_x(34)
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(*WHITE)
            pdf.cell(0, 4, title[:90], ln=True)

            # Domain + score
            if domain or score:
                pdf.set_x(14)
                pdf.set_font('Helvetica', '', 7)
                pdf.set_text_color(*MUTED)
                parts = []
                if domain:
                    parts.append(domain[:50])
                if score:
                    parts.append(f'score: {score}')
                pdf.cell(0, 3.5, '  ·  '.join(parts), ln=True)

            # URL
            if url:
                pdf.set_x(14)
                pdf.set_font('Helvetica', '', 7)
                pdf.set_text_color(56, 189, 248)
                pdf.cell(0, 3.5, url[:100], ln=True)

            # Extra props
            _IMSKIP = {'url', 'source', 'domain', 'title', 'score', 'similarity'}
            extra = {k: v for k, v in props.items()
                     if k not in _IMSKIP and str(v).strip() and str(v) != 'None'}
            if extra:
                _artifact_props_row(extra)

            pdf.ln(1)
            rule(pdf.get_y(), (220, 220, 225))
            pdf.ln(3)

    # ══════════════════════════════════════════════════════════════
    # PAGE — EVIDENCE INTEGRITY
    # ══════════════════════════════════════════════════════════════
    db_h = get_db()
    _hashes = db_h.execute(
        'SELECT filename, sha256, created_at FROM file_hashes WHERE inv_id=? ORDER BY created_at',
        (inv_id,)
    ).fetchall()
    db_h.close()

    pdf.add_page()
    set_bg()
    pdf.set_y(16)
    heading('Evidence Integrity', 14, WHITE, 8)
    rule(); pdf.ln(4)

    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5,
        'All artefacts listed below were SHA-256 hashed at the moment of capture and stored '
        'in the investigation database. Any post-capture modification will produce a different '
        'hash, making tampering detectable.')
    pdf.ln(5)

    if _hashes:
        # Column headers
        pdf.set_x(14)
        pdf.set_font('Helvetica', 'B', 6)
        pdf.set_text_color(*MUTED)
        pdf.cell(62, 4, 'FILENAME', ln=False)
        pdf.cell(98, 4, 'SHA-256', ln=False)
        pdf.cell(0,  4, 'CAPTURED (UTC)', ln=True)
        rule(pdf.get_y(), ACCENT); pdf.ln(1)

        for _h in _hashes:
            pdf.set_x(14)
            pdf.set_font('Helvetica', '', 6)
            pdf.set_text_color(*WHITE)
            pdf.cell(62, 3.8, _safe(_h['filename'])[:38], ln=False)
            pdf.set_font('Courier', '', 5.5)
            pdf.set_text_color(80, 200, 160)
            pdf.cell(98, 3.8, _h['sha256'], ln=False)
            pdf.set_font('Helvetica', '', 6)
            pdf.set_text_color(*MUTED)
            pdf.cell(0, 3.8, _safe(str(_h['created_at']))[:19], ln=True)
    else:
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 5, 'No artefact hashes recorded for this investigation.', ln=True)

    # ══════════════════════════════════════════════════════════════
    # Final page — methodology
    # ══════════════════════════════════════════════════════════════
    pdf.add_page()
    set_bg()
    pdf.set_y(16)
    heading('Methodology', 14, WHITE, 8)
    rule(); pdf.ln(8)
    body(
        'This report was generated by Gotham SOCMINT using a multi-source open-source intelligence pipeline.\n\n'
        'Sources: Maigret (500+ platforms), Sherlock (400+ platforms), DuckDuckGo dork queries, '
        'Holehe (email breach check), Moriarty (phone enrichment), WhatsApp metadata, Telegram channel '
        'lookup, Yandex Reverse Image Search, facial recognition (face search), and general image search.\n\n'
        'Verification: All platform URLs underwent HTTP 404 verification followed by AI-assisted visual '
        'screening using Gemini 2.5 Flash. Screenshots of each profile page were analysed to confirm '
        'active user presence and remove false positives.\n\n'
        'Classification: Results are classified by node type — Platform, Email, Phone, Location, Domain, '
        'Dork Intelligence, and Image Intelligence — and connected via a force-directed identity graph.\n\n'
        'This report is produced from publicly available information only.',
        size=9, color=MUTED, gap=5
    )
    pdf.ln(8)
    rule(pdf.get_y(), OLIVE)
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, 'GOTHAM · SOCMINT INTELLIGENCE PLATFORM · FOR AUTHORISED USE ONLY', align='C', ln=True)

    pdf_bytes = bytes(pdf.output())
    _pdf_fname = f'gotham_{inv["name"]}_{inv_id}.pdf'
    store_hash(inv_id, _pdf_fname, pdf_bytes, sub='reports')

    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename="{_pdf_fname}"'
    return resp


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
