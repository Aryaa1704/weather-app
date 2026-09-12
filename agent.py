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

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com/",
    "Origin": "https://leetcode.com",
}

def login():
    print("🔐 Logging in via API...")
    session = requests.Session()
    session.headers.update(HEADERS)

    # Get CSRF token
    resp = session.get("https://leetcode.com/", timeout=15)
    csrf = session.cookies.get("csrftoken", "")
    if not csrf:
        for c in session.cookies:
            if "csrf" in c.name.lower():
                csrf = c.value
                break

    print(f"🔑 CSRF token: {csrf[:10]}...")

    session.headers.update({
        "X-CSRFToken": csrf,
        "Referer": "https://leetcode.com/accounts/login/",
    })

    login_data = {
        "login": LEETCODE_USERNAME,
        "password": LEETCODE_PASSWORD,
    }

    resp = session.post(
        "https://leetcode.com/accounts/login/",
        data=login_data,
        timeout=15,
        allow_redirects=True
    )

    print(f"📄 Login status: {resp.status_code}")
    print(f"📄 Redirect URL: {resp.url}")

    # Check login success
    if "leetcode.com" in resp.url and resp.status_code == 200:
        user_check = session.get("https://leetcode.com/api/problems/all/", timeout=10)
        if user_check.status_code == 200:
            print("✅ Login successful!")
            return session
    
    # Try GraphQL login check
    check = session.post(
        "https://leetcode.com/graphql",
        json={"query": "{ userStatus { username isSignedIn } }"},
        timeout=10
    )
    if check.status_code == 200:
        data = check.json()
        user_data = data.get("data", {}).get("userStatus", {})
        if user_data.get("isSignedIn"):
            print(f"✅ Logged in as: {user_data.get('username')}")
            return session
        else:
            print(f"⚠️ Not signed in. Response: {data}")

    print("✅ Proceeding with session (cookies set)")
    return session

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
                exampleTestcases
                metaData
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
    daily = data["data"]["activeDailyCodingChallengeQuestion"]
    return daily

def get_solution_from_gemini(title, description):
    print("🤖 Getting solution from Gemini...")
    prompt = f"""You are an expert competitive programmer.
Solve this LeetCode problem. Return ONLY the Python3 solution code.
No explanation, no markdown, no backticks — just the raw code.

Problem: {title}

Description:
{description}
"""
    response = model.generate_content(prompt)
    code = response.text.strip()
    # Clean up if model added backticks anyway
    code = re.sub(r'^```python\n?', '', code)
    code = re.sub(r'^```\n?', '', code)
    code = re.sub(r'\n?```$', '', code)
    return code.strip()

def submit_solution(session, slug, question_id, solution, lang="python3"):
    print(f"🚀 Submitting solution for: {slug}")

    # Get CSRF token from cookies
    csrf = session.cookies.get("csrftoken", "")

    session.headers.update({
        "X-CSRFToken": csrf,
        "Referer": f"https://leetcode.com/problems/{slug}/",
    })

    payload = {
        "lang": lang,
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
        result = resp.json()
        submission_id = result.get("submission_id")
        print(f"✅ Submitted! Submission ID: {submission_id}")

        # Poll for result
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
                print(f"   State: {state}")
                if state == "SUCCESS":
                    status = check_data.get("status_msg", "Unknown")
                    print(f"🎉 Result: {status}")
                    if status == "Accepted":
                        print("🔥 Streak maintained!")
                    return check_data
                elif state in ["FAILURE", "RUNTIME_ERROR", "COMPILE_ERROR"]:
                    print(f"❌ Error: {check_data.get('status_msg')}")
                    return check_data
    else:
        print(f"❌ Submit failed: {resp.text[:500]}")

    return None

def run_agent():
    # Login
    session = login()

    # Get daily challenge
    daily = get_daily_challenge(session)
    question = daily["question"]
    title = question["title"]
    slug = question["titleSlug"]
    question_id = question["questionId"]
    difficulty = question["difficulty"]
    content = re.sub('<[^<]+?>', '', question["content"])
    link = "https://leetcode.com" + daily["link"]

    print(f"\n📝 Today's Problem: {title} [{difficulty}]")
    print(f"🔗 {link}\n")

    # Generate solution
    solution = get_solution_from_gemini(title, content)
    print("--- Solution ---")
    print(solution[:400])
    print("----------------\n")

    # Submit
    result = submit_solution(session, slug, question_id, solution)

    if result:
        print(f"\n✅ Agent finished!")
    else:
        print("\n⚠️ Could not confirm submission result — check LeetCode manually")

if __name__ == "__main__":
    run_agent()
