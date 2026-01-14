import praw
from datetime import datetime, timedelta, timezone

# =====================
# CONFIG
# =====================
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
USER_AGENT = "weekly-reddit-scraper by u/YOUR_USERNAME"

SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "stockmarket"
]

POST_LIMIT_PER_SUB = 500  # upper bound (Reddit sorting limits apply)

# =====================
# REDDIT CLIENT
# =====================
reddit = praw.Reddit(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    user_agent=USER_AGENT
)

# =====================
# DATE FILTER
# =====================
now = datetime.now(timezone.utc)
one_week_ago = now - timedelta(days=7)

# =====================
# COLLECT POSTS
# =====================
rows = []

for subreddit_name in SUBREDDITS:
    subreddit = reddit.subreddit(subreddit_name)

    for post in subreddit.new(limit=POST_LIMIT_PER_SUB):
        created = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)

        if created < one_week_ago:
            break  # posts are sorted newest → oldest

        rows.append({
            "subreddit": subreddit_name,
            "post_id": post.id,
            "title": post.title,
            "body": post.selftext,
            "score": post.score,
            "num_comments": post.num_comments,
            "flair": post.link_flair_text,
            "flair_css": post.link_flair_css_class,
            "created_utc": created.isoformat(),
            "url": post.url
        })

print(f"Collected {len(df)} posts from last 7 days.")


if __name__ == "__main__":
    print("hi")