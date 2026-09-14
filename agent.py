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
        return session
    raise SystemExit("❌ LEETCODE_SESSION not found!")

def check_login(session):
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": "{ userStatus { username isSignedIn } }"},
        timeout=10
    )
    data = resp.json().get("data", {}).get("userStatus", {})
    username = data.get('username', '')
    signed_in = data.get('isSignedIn', False)
    print(f"👤 User: {username} | Signed in: {signed_in}")
    if not signed_in:
        # This will trigger the email alert via GitHub Actions failure
        raise SystemExit("❌ Cookie expired! Email alert will be sent.")
    return True

def get_daily_challenge(session):
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
                topicTags { name }
            }
        }
    }
    """
    resp = session.post("https://leetcode.com/graphql", json={"query": query}, timeout=15)
    return resp.json()["data"]["activeDailyCodingChallengeQuestion"]

def get_easy_problems(session, count=3):
    """Fetch unsolved easy problems"""
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
                topicTags { name }
            }
        }
    }
    """
    variables = {
        "categorySlug": "",
        "limit": 100,
        "skip": 0,
        "filters": {"difficulty": "EASY"}
    }
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": variables},
        timeout=15
    )
    questions = resp.json()["data"]["problemsetQuestionList"]["questions"]
    # Return first N unsolved
    unsolved = [q for q in questions if q["status"] != "ac"]
    return unsolved[:count]

def get_problem_content(session, slug):
    query = """
    query questionContent($titleSlug: String!) {
        question(titleSlug: $titleSlug) {
            questionId
            title
            content
            topicTags { name }
        }
    }
    """
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": {"titleSlug": slug}},
        timeout=15
    )
    return resp.json()["data"]["question"]

def get_community_solutions(session, slug):
    query = """
    query communitySolutions($questionSlug: String!, $skip: Int!, $first: Int!, $orderBy: TopicSortingOption, $languageTags: [String!]) {
        questionSolutions(
            filters: {questionSlug: $questionSlug, skip: $skip, first: $first, orderBy: $orderBy, languageTags: $languageTags}
        ) {
            solutions {
                id
                title
                content
                langSlug
            }
        }
    }
    """
    variables = {
        "questionSlug": slug,
        "skip": 0,
        "first": 5,
        "orderBy": "hot",
        "languageTags": ["python3"]
    }
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": variables},
        timeout=15
    )
    if resp.status_code == 200:
        solutions = resp.json().get("data", {}).get("questionSolutions", {}).get("solutions", [])
        for sol in solutions:
            if sol.get("langSlug") == "python3" and sol.get("content"):
                code_match = re.search(r'```python3?\n(.*?)```', sol["content"], re.DOTALL)
                if code_match:
                    return code_match.group(1).strip()
    return None

def get_solution_from_gemini(title, content, tags, attempt=1):
    tags_str = ", ".join(tags) if tags else ""
    prompt = f"""You are a world-class competitive programmer.
Solve this LeetCode problem with a CORRECT Python3 solution.

Problem: {title}
Tags: {tags_str}

Description:
{content}

RULES:
- Return ONLY raw Python3 code
- No markdown, no backticks, no explanation
- Include all necessary imports
- Handle all edge cases
{"- Previous attempt failed. Try a completely different approach." if attempt > 1 else ""}
{"- Use the simplest brute force approach — correctness over efficiency." if attempt > 2 else ""}
"""
    response = model.generate_content(prompt)
    code = response.text.strip()
    code = re.sub(r'^```python3?\n?', '', code)
    code = re.sub(r'^```\n?', '', code)
    code = re.sub(r'\n?```$', '', code)
    return code.strip()

def submit_and_check(session, slug, question_id, solution):
    csrf = session.cookies.get("csrftoken", "")
    session.headers.update({
        "X-CSRFToken": csrf,
        "Referer": f"https://leetcode.com/problems/{slug}/",
    })
    resp = session.post(
        f"https://leetcode.com/problems/{slug}/submit/",
        json={"lang": "python3", "question_id": str(question_id), "typed_code": solution},
        timeout=15
    )
    if resp.status_code != 200:
    print(f"❌ Submit failed: {resp.status_code}")
    print(f"Response: {resp.text[:1000]}")
    print(f"CSRF present: {bool(csrf)}")
    print(f"Cookies: {list(session.cookies.keys())}")
    return None
    submission_id = resp.json().get("submission_id")
    print(f"📤 Submitted! ID: {submission_id}")

    for i in range(20):
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
                print(f"🎯 Result: {status}")
                return status
            elif state in ["FAILURE", "RUNTIME_ERROR", "COMPILE_ERROR", "WRONG_ANSWER"]:
                print(f"❌ {check_data.get('status_msg', state)}")
                return check_data.get("status_msg", state)
    return None

def solve_problem(session, title, slug, question_id, content, tags, label=""):
    print(f"\n{'='*50}")
    print(f"📝 {label}: {title}")
    print(f"🔗 https://leetcode.com/problems/{slug}/")
    print(f"{'='*50}")

    # Try community solution first
    community = get_community_solutions(session, slug)
    if community:
        print("🔍 Trying community solution...")
        result = submit_and_check(session, slug, question_id, community)
        if result == "Accepted":
            print(f"🎉 Accepted via community solution!")
            return True
        time.sleep(5)

    # Try Gemini up to 4 times
    for attempt in range(1, 5):
        print(f"🤖 Gemini attempt {attempt}/4...")
        solution = get_solution_from_gemini(title, content, tags, attempt)
        result = submit_and_check(session, slug, question_id, solution)
        if result == "Accepted":
            print(f"🎉 Accepted on attempt {attempt}!")
            return True
        time.sleep(5)

    print(f"⚠️ Could not solve: {title}")
    return False

def run_agent():
    print("🚀 LeetCode Agent Starting...")
    session = create_session()
    check_login(session)  # Will exit with error if cookie expired

    results = []

    # ── PROBLEM 1: Daily Challenge (Streak ke liye) ──
    print("\n🔥 DAILY CHALLENGE (Streak)")
    daily = get_daily_challenge(session)
    q = daily["question"]
    content = re.sub('<[^<]+?>', '', q["content"])
    tags = [t["name"] for t in q.get("topicTags", [])]
    print(f"Problem: {q['title']} [{q['difficulty']}]")

    daily_ok = solve_problem(
        session, q["title"], q["titleSlug"],
        q["questionId"], content, tags,
        label="Daily Challenge"
    )
    results.append(("🔥 Daily Challenge", q["title"], q["difficulty"], daily_ok))
    time.sleep(10)

    # ── PROBLEMS 2-4: Easy Practice ──
    print("\n📚 EASY PRACTICE PROBLEMS (3)")
    easy_problems = get_easy_problems(session, count=3)

    for i, eq in enumerate(easy_problems, 1):
        data = get_problem_content(session, eq["titleSlug"])
        easy_content = re.sub('<[^<]+?>', '', data["content"])
        easy_tags = [t["name"] for t in data.get("topicTags", [])]

        ok = solve_problem(
            session, eq["title"], eq["titleSlug"],
            eq["questionId"], easy_content, easy_tags,
            label=f"Easy #{i}"
        )
        results.append((f"📗 Easy #{i}", eq["title"], "Easy", ok))
        time.sleep(10)

    # ── SUMMARY ──
    print("\n" + "="*50)
    print("📊 FINAL SUMMARY")
    print("="*50)
    total_solved = 0
    for label, title, diff, success in results:
        status = "✅ Accepted" if success else "❌ Failed"
        print(f"{status} | {label}: {title} [{diff}]")
        if success:
            total_solved += 1

    print(f"\n🎯 Solved: {total_solved}/4")
    if results[0][3]:
        print("🔥 STREAK MAINTAINED!")
    else:
        print("⚠️ Daily challenge failed — streak at risk!")

if __name__ == "__main__":
    run_agent()
