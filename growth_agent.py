import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()
USERNAME = os.getenv("LEETCODE_USERNAME")
SESSION_COOKIE = os.getenv("LEETCODE_SESSION")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HEADERS = {"User-Agent": "Mozilla/5.0 LeetCodeGrowthAgent/1.0", "Referer": "https://leetcode.com/", "Content-Type": "application/json"}
GRAPHQL = "https://leetcode.com/graphql"
TIMEOUT = 25


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    if SESSION_COOKIE:
        s.cookies.set("LEETCODE_SESSION", SESSION_COOKIE, domain=".leetcode.com", path="/")
    return s


def gql(s, query, variables=None):
    r = s.post(GRAPHQL, json={"query": query, "variables": variables or {}}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"])[:400])
    return data.get("data") or {}


def telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram skipped: configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": message, "disable_web_page_preview": True}, timeout=TIMEOUT)
    r.raise_for_status()


def summary(message):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    print(message)


def get_profile(s, username):
    query = """
    query growthProfile($username: String!) {
      matchedUser(username: $username) {
        username
        profile { ranking reputation }
        submitStats { acSubmissionNum { difficulty count submissions } }
        badges { id name shortName displayName icon }
      }
      userContestRankingInfo(username: $username) {
        attendedContestsCount rating globalRanking topPercentage
      }
    }
    """
    data = gql(s, query, {"username": username})
    user = data.get("matchedUser")
    if not user:
        raise RuntimeError("LeetCode public profile not found or unavailable.")
    return user, data.get("userContestRankingInfo")


def get_calendar(s, username):
    query = """
    query growthCalendar($username: String!, $year: Int!) {
      userCalendar(username: $username, year: $year) { streak totalActiveDays submissionCalendar }
    }
    """
    try:
        return gql(s, query, {"username": username, "year": datetime.now(timezone.utc).year}).get("userCalendar") or {}
    except Exception as exc:
        print(f"Calendar unavailable: {exc}")
        return {}


def get_contest_reminders():
    r = requests.get("https://leetcode.com/contest/api/list/", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    contests = payload if isinstance(payload, list) else payload.get("contests", [])
    now = datetime.now(timezone.utc)
    result = []
    ist = timezone(timedelta(hours=5, minutes=30))
    for contest in contests:
        try:
            start = int(contest.get("start_time") or contest.get("startTime"))
            start_dt = datetime.fromtimestamp(start, timezone.utc)
            if timedelta(0) <= start_dt - now <= timedelta(hours=48):
                title = contest.get("title") or contest.get("title_slug") or "LeetCode contest"
                result.append(
                    f"🏁 {title}\nStarts: {start_dt.astimezone(ist).strftime('%d %b %Y, %I:%M %p IST')}\n"
                    "Register manually: https://leetcode.com/contest/"
                )
        except (TypeError, ValueError, OSError):
            continue
    return result


def recent_accepted(s, username):
    query = """
    query recentAccepted($username: String!) {
      recentAcSubmissionList(username: $username, limit: 20) { id title titleSlug timestamp lang }
    }
    """
    items = gql(s, query, {"username": username}).get("recentAcSubmissionList") or []
    return next((x for x in items if x.get("id") and x.get("titleSlug") and x.get("lang") in ("python3", "python")), None)


def make_community_draft(s, username):
    item = recent_accepted(s, username)
    if not item:
        print("No recent accepted Python submission; draft skipped.")
        return None
    detail_query = """
    query submissionCode($submissionId: Int!) {
      submissionDetails(submissionId: $submissionId) { code }
    }
    """
    code = (gql(s, detail_query, {"submissionId": int(item["id"])}).get("submissionDetails") or {}).get("code", "")
    if not code:
        print("Submission code unavailable; draft skipped.")
        return None

    from agent import AI_PROVIDERS
    prompt = f"""Write an original, technically accurate LeetCode community solution article in Markdown.
Include intuition, algorithm steps, correctness reasoning, a short dry run, and time/space complexity.
Do not invent constraints or performance claims. Preserve the accepted code exactly.
Problem: {item['title']}
URL: https://leetcode.com/problems/{item['titleSlug']}/
Accepted Python code:
{code}
Return only the article Markdown."""
    for provider in AI_PROVIDERS:
        if not provider.get("key") or not provider.get("url"):
            continue
        try:
            r = requests.post(provider["url"],
                headers={"Authorization": f"Bearer {provider['key']}", "Content-Type": "application/json"},
                json={"model": provider["model"], "messages": [
                    {"role": "system", "content": "You write precise LeetCode solution explanations."},
                    {"role": "user", "content": prompt}],
                    "temperature": 0.2, "max_tokens": 3000}, timeout=TIMEOUT)
            if r.status_code != 200:
                print(f"{provider['name']} returned HTTP {r.status_code}")
                continue
            article = r.json()["choices"][0]["message"]["content"]
            if isinstance(article, list):
                article = "".join(x.get("text", "") for x in article if isinstance(x, dict))
            if not isinstance(article, str) or len(article.strip()) < 100:
                continue
            folder = Path("community_drafts")
            folder.mkdir(exist_ok=True)
            path = folder / f"{item['titleSlug']}.md"
            path.write_text(
                f"<!-- REVIEW REQUIRED: verify before manually publishing. -->\n# {item['title']}\n\n"
                f"Problem: https://leetcode.com/problems/{item['titleSlug']}/\n\n"
                + article.strip() + "\n", encoding="utf-8")
            return str(path)
        except Exception as exc:
            print(f"{provider['name']} draft generation failed: {exc}")
    return None


def main():
    if not USERNAME:
        raise SystemExit("Set LEETCODE_USERNAME.")
    s = session()
    user, contest = get_profile(s, USERNAME)
    calendar = get_calendar(s, USERNAME)
    stats = {x.get("difficulty"): x.get("count", 0) for x in (user.get("submitStats") or {}).get("acSubmissionNum", [])}
    profile = user.get("profile") or {}
    badges = user.get("badges") or []
    lines = [
        "## LeetCode profile snapshot",
        f"- Username: {user.get('username')}",
        f"- Solved: {stats.get('All', 0)} total | Easy {stats.get('Easy', 0)} | Medium {stats.get('Medium', 0)} | Hard {stats.get('Hard', 0)}",
        f"- Global rank: {profile.get('ranking', 'N/A')}",
        f"- Reputation: {profile.get('reputation', 'N/A')}",
        f"- Current streak: {calendar.get('streak', 'N/A')}",
        f"- Active days this year: {calendar.get('totalActiveDays', 'N/A')}",
        f"- Badges returned by API: {len(badges)}",
    ]
    if contest:
        lines += [f"- Contests attended: {contest.get('attendedContestsCount', 'N/A')}",
                  f"- Contest rating: {round(contest.get('rating') or 0, 2)}",
                  f"- Contest global rank: {contest.get('globalRanking', 'N/A')}"]
    if badges:
        lines += ["", "### Badges"] + [f"- {b.get('displayName') or b.get('name') or b.get('shortName')}" for b in badges[:20]]
    summary("\n".join(lines))

    reminders = get_contest_reminders()
    for message in reminders:
        telegram("Upcoming LeetCode contest\n" + message + "\nContest solving/submission remains manual.")
        summary("### Contest reminder\n" + message.replace("\n", "  \n"))
    if not reminders:
        summary("No contest starting in the next 48 hours.")

    draft = make_community_draft(s, USERNAME)
    if draft:
        summary(f"### Community draft created\n{draft}\nReview, edit, and publish manually.")
    telegram(f"LeetCode Growth Agent: {USERNAME}\nSolved: {stats.get('All', 'N/A')} | Badges: {len(badges)}\nContest rating: {(contest or {}).get('rating', 'N/A')}\nCommunity draft: {'ready' if draft else 'not generated'}")


if __name__ == "__main__":
    main()
