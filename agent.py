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
LEETCODE_SESSION = os.getenv("LEETCODE_SESSION")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3.6-flash")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com/",
    "Origin": "https://leetcode.com",
}

def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)

    if LEETCODE_SESSION:
        print("🍪 Using LEETCODE_SESSION cookie...")
        session.cookies.set("LEETCODE_SESSION", LEETCODE_SESSION, domain="leetcode.com")
        resp = session.get("https://leetcode.com/", timeout=15)
        csrf = session.cookies.get("csrftoken", "")
        session.headers.update({"X-CSRFToken": csrf})
        print(f"✅ Session loaded!")
        return session

    raise SystemExit("❌ LEETCODE_SESSION not found in secrets!")

def check_login(session):
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": "{ userStatus { username isSignedIn } }"},
        timeout=10
    )
    data = resp.json().get("data", {}).get("userStatus", {})
    print(f"👤 User: {data.get('username')} | Signed in: {data.get('isSignedIn')}")
    return data.get("isSignedIn", False)

def get_easy_problem(session):
    """Fetch a random easy problem that hasn't been solved yet"""
    print("🎯 Finding an easy problem...")
    query = """
    query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
        problemsetQuestionList: questionList(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
            filters: $filters
        ) {
            questions: data {
                questionId
                title
                titleSlug
                difficulty
                status
            }
        }
    }
    """
    variables = {
        "categorySlug": "",
        "limit": 50,
        "skip": 0,
        "filters": {"difficulty": "EASY"}
    }
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": variables},
        timeout=15
    )
    data = resp.json()
    questions = data["data"]["problemsetQuestionList"]["questions"]

    # Pick first unsolved easy problem
    for q in questions:
        if q["status"] != "ac":  # not already accepted
            print(f"✅ Found: {q['title']} [Easy]")
            return q

    # Fallback — just return first one
    print(f"✅ Using: {questions[0]['title']} [Easy]")
    return questions[0]

def get_problem_content(session, slug):
    """Get full problem description"""
    query = """
    query questionContent($titleSlug: String!) {
        question(titleSlug: $titleSlug) {
            questionId
            title
            content
            difficulty
        }
    }
    """
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": {"titleSlug": slug}},
        timeout=15
    )
    return resp.json()["data"]["question"]

def get_solution_from_gemini(title, description, attempt=1):
    print(f"🤖 Getting solution from Gemini (attempt {attempt})...")
    prompt = f"""You are an expert competitive programmer.
Solve this LeetCode problem. Return ONLY the Python3 solution code.
No explanation, no markdown, no backticks — just raw code.
Make sure the solution is complete, correct, and handles all edge cases.

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
        for i in range(15):
            time.sleep(3)
            check = session.get(
                f"https://leetcode.com/submissions/detail/{submission_id}/check/",
                timeout=10
            )
            if check.status_code == 200:
                check_data = check.json()
                state = check_data.get("state", "")
                if state == "SUCCESS":
                    status = check_data.get("status_msg", "Unknown")
                    print(f"🎉 Result: {status}")
                    return status
                elif state in ["FAILURE", "RUNTIME_ERROR", "COMPILE_ERROR"]:
                    status = check_data.get("status_msg", state)
                    print(f"❌ {status}")
                    return status
    else:
        print(f"❌ Submit failed: {resp.text[:300]}")
    return None

def run_agent():
    session = create_session()
    logged_in = check_login(session)

    if not logged_in:
        print("⚠️ Not logged in! Refresh LEETCODE_SESSION in GitHub Secrets.")
        raise SystemExit(1)

    # Get an easy problem
    easy_q = get_easy_problem(session)
    slug = easy_q["titleSlug"]
    question_id = easy_q["questionId"]
    title = easy_q["title"]

    # Get full content
    content_data = get_problem_content(session, slug)
    content = re.sub('<[^<]+?>', '', content_data["content"])

    print(f"\n📝 Solving: {title} [Easy]")
    print(f"🔗 https://leetcode.com/problems/{slug}/\n")

    # Try up to 3 times to get accepted
    for attempt in range(1, 4):
        solution = get_solution_from_gemini(title, content, attempt)
        print("--- Solution ---")
        print(solution[:300])
        print("----------------\n")

        result = submit_solution(session, slug, question_id, solution)

        if result == "Accepted":
            print(f"\n✅ ACCEPTED on attempt {attempt}! Streak maintained 🔥")
            return
        elif result:
            print(f"⚠️ Attempt {attempt} failed ({result}), retrying with different solution...")
            time.sleep(5)
        else:
            print("⚠️ Could not get result, trying again...")

    print("\n⚠️ Could not get accepted after 3 attempts — check LeetCode manually")

if __name__ == "__main__":
    run_agent()
