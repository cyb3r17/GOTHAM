import re
from datetime import datetime, timedelta
from typing import Any, Dict, List

try:
    from dateutil import parser as _date_parser  # type: ignore
except Exception:
    _date_parser = None


def _parse_date(s: Any) -> str:
    if not s:
        return ""
    if isinstance(s, (int, float)):
        try:
            return datetime.fromtimestamp(float(s)).isoformat()
        except Exception:
            return str(s)
    s_str = str(s).strip()
    # Remove parenthetical comments like "(~1 hour ago at time of check)" before parsing
    s_clean = re.sub(r"\(.*?\)", "", s_str).strip()

    # Handle relative times like "~3 hours ago" or "3 hours ago"
    rel_match = re.search(r"~?\s*(\d+)\s*(hour|hours|hr|hrs)\b", s_clean, re.I)
    if not rel_match:
        rel_match = re.search(r"~?\s*(\d+)\s*(minute|minutes|min|mins)\b", s_clean, re.I)
    if rel_match:
        try:
            qty = int(rel_match.group(1))
            unit = rel_match.group(2).lower()
            now = datetime.utcnow()
            if unit.startswith("hour") or unit.startswith("hr"):
                ts = now - timedelta(hours=qty)
            else:
                ts = now - timedelta(minutes=qty)
            return ts.isoformat()
        except Exception:
            pass

    if _date_parser:
        try:
            return _date_parser.parse(s_clean).isoformat()
        except Exception:
            pass
    fmts = ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%d %b %Y"]
    for f in fmts:
        try:
            return datetime.strptime(s_clean, f).isoformat()
        except Exception:
            continue
    return s_str


def normalize_profile(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a noisy profile dict into the canonical app format.

    Canonical output keys:
      - username
      - display_name
      - bio
      - captions (list[str])
      - posting_times (list[str], ISO-ish)

    The function is defensive and tolerates many common noisy shapes.
    """
    if not isinstance(raw, dict):
        return {
            "username": "",
            "display_name": "",
            "bio": "",
            "captions": [],
            "posting_times": [],
        }

    # username / handle
    username = raw.get("username") or raw.get("handle") or raw.get("screen_name") or raw.get("user") or ""

    # display name
    display_name = raw.get("display_name") or raw.get("name") or raw.get("full_name") or ""

    # bio / description
    bio = raw.get("bio") or raw.get("description") or raw.get("about") or ""

    captions: List[str] = []
    posting_times: List[str] = []

    # Some inputs use `posts` list of objects
    posts = raw.get("posts") or raw.get("timeline") or raw.get("tweets") or raw.get("items") or []
    if isinstance(posts, list) and posts:
        for p in posts:
            if not isinstance(p, dict):
                continue
            text = p.get("caption") or p.get("text") or p.get("message") or ""
            if text:
                captions.append(text)
            # hashtags field inside post
            # ignore hashtag-like fields entirely per new policy
            # timestamp
            ts = p.get("timestamp") or p.get("time") or p.get("created_at")
            if ts:
                posting_times.append(_parse_date(ts))

    # top-level captions array
    top_caps = raw.get("captions") or raw.get("texts") or raw.get("messages")
    if isinstance(top_caps, list):
        for c in top_caps:
            if isinstance(c, str):
                captions.append(c)

    # top-level hashtags
    # ignore top-level hashtag/tag fields

    # posting_times top-level
    top_times = raw.get("posting_times") or raw.get("timestamps") or raw.get("dates")
    if isinstance(top_times, list):
        for t in top_times:
            posting_times.append(_parse_date(t))

    # If captions empty but there's a top-level caption-like string
    if not captions:
        possible = raw.get("caption") or raw.get("text") or raw.get("status")
        if isinstance(possible, str) and possible:
            captions.append(possible)

    # Always drop image and hashtag data — they are not used
    return {
        "username": username,
        "display_name": display_name,
        "bio": bio,
        "captions": captions,
        "posting_times": posting_times,
    }


def parse_plain_text_profile(text: str) -> Dict[str, Any]:
    """Parse a simple human-readable profile dump into a dict.

    Handles formats like:
      name: sachit (@sr71__)
      followers: 12
      posts: 2
      post1:
      --url: https://...
      --date: July 04, 2026 (~1 hour ago ...)
      --caption: (none - no caption text found on post)
      --description: Image/meme ...

    This is intentionally lenient and best-effort.
    """
    if not isinstance(text, str):
        return {}

    lines = [l.rstrip() for l in text.splitlines()]
    data: Dict[str, Any] = {}
    posts: List[Dict[str, Any]] = []
    cur_post: Dict[str, Any] | None = None

    key_re = re.compile(r"^\s*([A-Za-z0-9_ -]+?):\s*(.*)$")
    post_key_re = re.compile(r"^\s*post\s*\d+\s*:\s*$", re.I)
    dash_field_re = re.compile(r"^\s*--\s*([A-Za-z0-9_ -]+?)\s*:\s*(.*)$")

    for raw in lines:
        if not raw:
            # blank line separates posts
            if cur_post:
                posts.append(cur_post)
                cur_post = None
            continue

        if post_key_re.match(raw):
            if cur_post:
                posts.append(cur_post)
            cur_post = {}
            continue

        m_dash = dash_field_re.match(raw)
        if m_dash:
            k = m_dash.group(1).strip().lower()
            v = m_dash.group(2).strip()
            if cur_post is None:
                cur_post = {}
            cur_post[k] = v
            continue

        m = key_re.match(raw)
        if m:
            k = m.group(1).strip().lower()
            v = m.group(2).strip()
            # handle comma-separated lists (links)
            if k in ("links", "urls"):
                items = [i.strip() for i in re.split(r"[,;]", v) if i.strip()]
                data[k] = items
            else:
                data[k] = v
            continue

        # fallback: try to attach unknown lines as description to current post
        if cur_post is not None:
            cur_post.setdefault("description", "")
            cur_post["description"] += ("\n" + raw) if cur_post["description"] else raw

    if cur_post:
        posts.append(cur_post)

    # If the input contained no structured fields, treat the entire text as raw caption/bio
    if not data and not posts:
        raw_text = text.strip()
        if raw_text:
            return {
                "username": "",
                "display_name": "",
                "bio": "",
                "captions": [raw_text],
                "posting_times": [],
            }

    # Build canonical dict expected by normalize_profile
    out: Dict[str, Any] = {}
    # username / display_name
    name = data.get("name") or data.get("display_name") or ""
    # attempt to extract username in parentheses e.g. "sachit (@sr71__)"
    username = ""
    if name:
        m = re.search(r"\((@?[^)]+)\)", name)
        if m:
            username = m.group(1).lstrip('@')
        else:
            # if an explicit name field like "name: sachit (@sr71__)" absent, try 'name' raw
            username = data.get("name") or ""

    out["username"] = username or data.get("handle") or data.get("screen_name") or ""
    out["display_name"] = name or out["username"]
    out["bio"] = data.get("bio") or data.get("description") or ""

    # convert posts to expected posts list
    parsed_posts: List[Dict[str, Any]] = []
    for p in posts:
        caption = p.get("caption") or ""
        if caption and caption.lower().startswith("(none"):
            caption = ""
        description = p.get("description") or p.get("description") or ""
        if not caption and description:
            # use description as caption if caption missing
            caption = description
        timestamp = p.get("date") or p.get("timestamp") or p.get("time") or ""
        parsed_posts.append({
            "caption": caption,
            "hashtags": [],
            "timestamp": timestamp,
            "description": description,
            "url": p.get("url") or "",
        })

    out["posts"] = parsed_posts
    # links
    links = data.get("links") or data.get("urls") or []
    out["links"] = links
    # followers / following
    try:
        out["followers"] = int(data.get("followers", 0) or 0)
    except Exception:
        out["followers"] = 0
    try:
        out["following"] = int(data.get("following", 0) or 0)
    except Exception:
        out["following"] = 0

    # Return a dict that normalize_profile can handle
    return out
