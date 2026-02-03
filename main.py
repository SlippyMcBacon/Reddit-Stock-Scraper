from collections import Counter
import requests
import feedparser
import re
import time
from datetime import datetime, timedelta, timezone

COMMENTS_PER_POST = 30
REQUEST_DELAY = 0.5  # seconds (important)

HEADERS = {
    "User-Agent": "reddit-rss-comment-fetcher/1.0"
}


def get_comments(inpost_id, limit):
    url = f"https://www.reddit.com/comments/{inpost_id}.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception:
        return []

    data = r.json()
    incomments = []

    for child in data[1]["data"]["children"]:
        if child["kind"] == "t1":
            body = child["data"].get("body")
            if body:
                incomments.append(body)
        if len(incomments) >= limit:
            break

    return incomments

subs = ["wallstreetbets", "stocks", "valueinvesting", "daytrading", "10xpennystocks", "theraceto10million", "walllstreetbets", "smallstreetbets", "options", "shortsqueeze", "pennystock", "stockstobuytoday"]
one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

blacklist = ["OFF", "CEO", "ATM", "LLC", "IPO", "YOLO", "SEC", "WSB", "USD", "THE", "CAD"]

rows = []
ctr = Counter()
for sub in subs:
    print(sub)
    feed = feedparser.parse(f"https://www.reddit.com/r/{sub}/new/.rss")
    for entry in feed.entries:
        sSet = set()
        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if published < one_week_ago:
            continue

        # Extract post ID from URL
        match = re.search(r"/comments/([a-z0-9]+)/", entry.link)
        if not match:
            continue
        post_id = match.group(1)

        # Fetch comments
        comments = get_comments(post_id, COMMENTS_PER_POST)
        time.sleep(REQUEST_DELAY)

        #rows.append({
        #    "subreddit": sub,
        #    "title": entry.title,
        #    "published": published.strftime("%m-%d-%y %H:%M"),
        #    "summary": entry.summary
        #})

        result = []
        sift = "".join(comments)
        sift = entry.summary + sift
        for char in sift:
            if char.isalpha():
                result.append(char)
            else:
                result.append(" ")
        text = "".join(result)
        text = text.split(" ")
        #print("")
        for word in text:

            # word = ''.join(filter(str.isalpha, word))
            if word.isupper() and 2 < len(word) <= 4 and word not in blacklist:
                #print(word)
                sSet.add(word)
        #print(sSet)
        rows += sSet
ctr = Counter(rows)
for elm in ctr.most_common(10):
    print(elm)