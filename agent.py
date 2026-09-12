import os
import re
import time
import requests
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

LEETCODE_USERNAME = os.getenv("LEETCODE_USERNAME")
LEETCODE_PASSWORD = os.getenv("LEETCODE_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LEETCODE_SESSION = os.getenv("LEETCODE_SESSION")  # optional cookie

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com/",
    "Origin": "https://leetcode.com",
}

def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)

    # If LEETCODE_SESSION cookie provided, use it directly
    if LEETCODE_SESSION:
        print("🍪 Using LEETCODE_SESSION cookie...")
        session.cookies.set("LEETCODE_SESSION", LEETCODE_SESSION, domain="leetcode.com")
        # Get CSRF token
        resp = session.get("https://leetcode.com/", timeout=15)
        csrf = session.cookies.get("csrftoken", "")
        session.headers.update({"X-CSRFToken": csrf})
        print(f"✅ Session loaded! CSRF: {csrf[:10]}...")
        return session

    # Fallback: try normal login
    print("🔐 Trying password login...")
    resp = session.get("https://leetcode.com/", timeout=15)
    csrf = session.cookies.get("csrftoken", "")
    session.headers.update({
        "X-CSRFToken": csrf,
        "Referer": "https://leetcode.com/accounts/login/",
    })
    resp = session.post(
        "https://leetcode.com/accounts/login/",
        data={"login": LEETCODE_USERNAME, "password": LEETCODE_PASSWORD},
        timeout=15,
        allow_redirects=True
    )
    print(f"📄 Login status: {resp.status_code}")

    # Update CSRF after login
    csrf = session.cookies.get("csrftoken", "")
    session.headers.update({"X-CSRFToken": csrf})
    return session

def check_login(session):
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": "{ userStatus { username isSignedIn } }"},
        timeout=10
    )
    data = resp.json().get("data", {}).get("userStatus", {})
    print(f"👤 User: {data.get('username')} | Signed in: {data.get('isSignedIn')}")
    return data.get("isSignedIn", False)

def get_daily_challenge(session):
    print("📅 Fetching daily challenge...")
    query = """
    {
        activeDailyCodingChallengeQuestion {
            date
            link
            question {
                title
                titleSlug
                content
                difficulty
                questionId
            }
        }
    }
    """
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query},
        timeout=15
    )
    data = resp.json()
    return data["data"]["activeDailyCodingChallengeQuestion"]

def get_solution_from_gemini(title, description):
    print("🤖 Getting solution from Gemini...")
    prompt = f"""You are an expert competitive programmer.
Solve this LeetCode problem. Return ONLY the Python3 solution code.
No explanation, no markdown, no backticks — just raw code.

Problem: {title}

Description:
{description}
"""
    response = model.generate_content(prompt)
    code = response.text.strip()
    code = re.sub(r'^```python\n?', '', code)
    code = re.sub(r'^```\n?', '', code)
    code = re.sub(r'\n?```$', '', code)
    return code.strip()

def submit_solution(session, slug, question_id, solution):
    print(f"🚀 Submitting: {slug}")
    csrf = session.cookies.get("csrftoken", "")
    session.headers.update({
        "X-CSRFToken": csrf,
        "Referer": f"https://leetcode.com/problems/{slug}/",
    })
    payload = {
        "lang": "python3",
        "question_id": str(question_id),
        "typed_code": solution,
    }
    resp = session.post(
        f"https://leetcode.com/problems/{slug}/submit/",
        json=payload,
        timeout=15
    )
    print(f"📤 Submit status: {resp.status_code}")

    if resp.status_code == 200:
        submission_id = resp.json().get("submission_id")
        print(f"✅ Submission ID: {submission_id}")
        print("⏳ Waiting for result...")
        for i in range(10):
            time.sleep(3)
            check = session.get(
                f"https://leetcode.com/submissions/detail/{submission_id}/check/",
                timeout=10
            )
            if check.status_code == 200:
                check_data = check.json()
                state = check_data.get("state", "")
                print(f"   State [{i+1}]: {state}")
                if state == "SUCCESS":
                    status = check_data.get("status_msg", "Unknown")
                    print(f"🎉 Result: {status}")
                    return check_data
                elif state in ["FAILURE", "RUNTIME_ERROR", "COMPILE_ERROR"]:
                    print(f"❌ {state}: {check_data.get('status_msg')}")
                    return check_data
    else:
        print(f"❌ Submit failed: {resp.text[:300]}")
    return None

def run_agent():
    session = create_session()
    logged_in = check_login(session)

    if not logged_in:
        print("⚠️ Not logged in! Add LEETCODE_SESSION cookie to GitHub Secrets.")
        print("   How to get it: Login to leetcode.com → F12 → Application → Cookies → LEETCODE_SESSION")
        raise SystemExit(1)

    daily = get_daily_challenge(session)
    question = daily["question"]
    title = question["title"]
    slug = question["titleSlug"]
    question_id = question["questionId"]
    difficulty = question["difficulty"]
    content = re.sub('<[^<]+?>', '', question["content"])

    print(f"\n📝 Today: {title} [{difficulty}]")
    print(f"🔗 https://leetcode.com{daily['link']}\n")

    solution = get_solution_from_gemini(title, content)
    print("--- Solution ---")
    print(solution[:400])
    print("----------------\n")

    result = submit_solution(session, slug, question_id, solution)
    if result:
        print("✅ Done! Streak maintained 🔥")
    else:
        print("⚠️ Check LeetCode manually")

if __name__ == "__main__":
    run_agent()
