from collections import Counter
import requests
import json
import feedparser
import re
import time
import random
import os
from datetime import datetime, timedelta, timezone
from typing import List

COMMENTS_PER_POST = 50
BASE_DELAY = 2.0  # base seconds between requests
MAX_RETRIES = 5
TIMEOUT = 10

HEADERS = {
    "User-Agent": "reddit-rss-comment-fetcher/1.1 (contact: yourname@example.com)"
}

RANK_FILE = "previous_rankings.json"


def load_previous_rankings():
    if not os.path.exists(RANK_FILE):
        return {}
    try:
        with open(RANK_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_current_rankings(rankings):
    try:
        with open(RANK_FILE, "w") as f:
            json.dump(rankings, f)
    except Exception as e:
        print(f"[Warn] Failed to save rankings: {e}")

# ---- Requests session with retry/backoff ----
session = requests.Session()
session.headers.update(HEADERS)

def send_pushover(message: str, title: str = "Stock Tracker"):
    user_key = os.getenv("PUSHOVER_USER_KEY")
    api_token = os.getenv("PUSHOVER_API_TOKEN")

    if not user_key or not api_token:
        print("[Warn] Pushover credentials not set.")
        return

    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": api_token,
                "user": user_key,
                "title": title,
                "message": message,
            },
            timeout=10,
        )
        print("[Info] Pushover notification sent.")
    except Exception as e:
        print(f"[Warn] Failed to send notification: {e}")

def sleep_with_jitter(base=BASE_DELAY):
    time.sleep(base + random.uniform(0.0, 0.6))

def safe_request(url, max_retries=5, base_delay=1.0):
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, application/rss+xml, application/xml;q=0.9,*/*;q=0.8",
                    "Connection": "keep-alive",
                },
                timeout=15,
            )

            # ✅ Success
            if response.status_code == 200:
                return response

            # 🔁 Rate limited
            elif response.status_code == 429:
                wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"[429] Rate limited. Sleeping {wait:.1f}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)

            # 🔁 Server errors (temporary)
            elif 500 <= response.status_code < 600:
                wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"[{response.status_code}] Server error. Sleeping {wait:.1f}s")
                time.sleep(wait)

            else:
                print(f"[Error] HTTP {response.status_code} for {url}")
                return None

        except requests.exceptions.ConnectionError as e:
            wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
            print(f"[ConnectionError] {e}. Retrying in {wait:.1f}s")
            time.sleep(wait)

        except requests.exceptions.Timeout:
            wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
            print(f"[Timeout] Retrying in {wait:.1f}s")
            time.sleep(wait)

        except requests.exceptions.RequestException as e:
            print(f"[Fatal Request Error] {e}")
            return None

    print(f"[Fail] Giving up on {url}")
    return None

def request_with_backoff(url: str):
    backoff = 1.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=TIMEOUT)
            # Handle rate limiting
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                print(f"[429] Rate limited. Sleeping {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                backoff = min(backoff * 2, 60)
                continue

            # Handle transient server errors
            if 500 <= r.status_code < 600:
                print(f"[{r.status_code}] Server error. Backing off {backoff:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            r.raise_for_status()
            return r
        except requests.RequestException as e:
            print(f"[Request error] {e}. Backing off {backoff:.1f}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

    return None

# ---- Comment fetcher ----
def get_comments(post_id: str, limit: int) -> List[str]:
    url = f"https://www.reddit.com/comments/{post_id}.json"
    r = request_with_backoff(url)
    if not r:
        return []

    try:
        data = r.json()
    except ValueError:
        # Not JSON (e.g., HTML error page)
        print(f"[Warn] Non-JSON response for post {post_id}")
        return []

    comments = []
    try:
        # Defensive traversal
        children = data[1].get("data", {}).get("children", [])
        for child in children:
            if child.get("kind") == "t1":
                body = child.get("data", {}).get("body")
                if body:
                    comments.append(body)
            if len(comments) >= limit:
                break
    except (IndexError, AttributeError, TypeError):
        print(f"[Warn] Unexpected JSON structure for post {post_id}")
        return []

    return comments

# ---- Config ----
subs = [
    "wallstreetbets",
    "stocks",
    "valueinvesting",
    "daytrading",
    "10xpennystocks",
    "theraceto10million",
    "walllstreetbets",
    "smallstreetbets",
    "options",
    "shortsqueeze",
    "pennystock",
    "stockstobuytoday",
]

one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

blacklist = {
    "OFF", "CEO", "ATM", "LLC", "IPO", "YOLO", "SEC", "WSB", "USD", "THE", "CAD",
    "THIS", "WILL", "HOLD", "MOON", "SEND", "LIVE", "POST", "EDIT", "LINK", "CPI",
    "EPS", "AND", "NOT", "ETF", "SPY", "USA", "FOR", "ONLY", "NYSE", "SPX", "ABOVE",
    "FDA", "GAAP", "AACR", "NFA", "NAV", "THESE", "IRA", "EPA", "ARE", "ABOVE", "COVID",
    "QQQ", "SPX", "IRS", "API", "ROI", "TSA", "MACD", "NYIAX", "OTCQB", "OTM"
}
# updated April 10th

rows = []
#send_pushover("NVDA(88)^ |NVDA(88)v |NVDA(88)- |NVDA(88)* |NVDA(88)^ |NVDA(88)v |NVDA(88)- |NVDA(88)* |NVDA(88)^")
for sub in subs:
    print(f"== {sub} ==")
    feed_url = f"https://www.reddit.com/r/{sub}/new/.rss"
    response = safe_request(feed_url)
    if not response:
        continue

    feed = feedparser.parse(response.content)

    for entry in feed.entries:
        # Guard: published_parsed may be missing
        if not hasattr(entry, "published_parsed") or not entry.published_parsed:
            continue

        try:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            continue

        if published < one_week_ago:
            continue

        # Extract post ID
        link = getattr(entry, "link", "")
        match = re.search(r"/comments/([a-z0-9]+)/", link)
        if not match:
            continue
        post_id = match.group(1)

        # Fetch comments (with backoff)
        comments = get_comments(post_id, COMMENTS_PER_POST)
        sleep_with_jitter()

        # Build text blob: summary + comments
        summary = getattr(entry, "summary", "") or ""
        sift = summary + "".join(comments)

        # Normalize to letters/spaces
        result_chars = []
        for char in sift:
            if char.isalpha():
                result_chars.append(char)
            else:
                result_chars.append(" ")

        text = "".join(result_chars).split()

        sSet = set()
        for word in text:
            # Your rule: uppercase, length 3–5, not blacklisted
            if word.isupper() and 2 < len(word) <= 5 and word not in blacklist:
                sSet.add(word)

        rows.extend(sSet)

# ---- Results ----
#ctr = Counter(rows)
#for sym, count in ctr.most_common(10):
    #print(sym, count)

ctr = Counter(rows)
top_results = ctr.most_common(9)

previous_data = load_previous_rankings()

current_data = {}
summary_parts = []

for rank, (sym, count) in enumerate(top_results, start=1):

    prev_entry = previous_data.get(sym)

    # ---- STREAK LOGIC ----
    if prev_entry:
        streak = prev_entry.get("streak", 1) + 1
        prev_rank = prev_entry.get("rank")

        if rank < prev_rank:
            indicator = "^"
        elif rank > prev_rank:
            indicator = "v"
        else:
            indicator = "-"
    else:
        streak = 1
        indicator = "+"

    current_data[sym] = {
        "rank": rank,
        "streak": streak
    }

    # 👇 Add streak BEFORE ticker
    summary_parts.append(f"{sym}({count}){streak}")

    print(f"{sym} {count} {indicator} streak={streak}")

# Build notification
notification_text = "" + " |".join(summary_parts)

send_pushover(notification_text)

save_current_rankings(current_data)