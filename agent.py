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
        print("✅ Session loaded!")
        return session
    raise SystemExit("❌ LEETCODE_SESSION not found!")

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
    print("📅 Fetching Daily Challenge...")
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
    data = resp.json()
    return data["data"]["activeDailyCodingChallengeQuestion"]

def get_community_solutions(session, slug):
    """Fetch top community solutions for the problem"""
    print("🔍 Fetching community solutions...")
    query = """
    query communitySolutions($questionSlug: String!, $skip: Int!, $first: Int!, $query: String, $orderBy: TopicSortingOption, $languageTags: [String!]) {
        questionSolutions(
            filters: {questionSlug: $questionSlug, skip: $skip, first: $first, query: $query, orderBy: $orderBy, languageTags: $languageTags}
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
        data = resp.json()
        solutions = data.get("data", {}).get("questionSolutions", {}).get("solutions", [])
        for sol in solutions:
            if sol.get("langSlug") == "python3" and sol.get("content"):
                # Extract code from content
                content = sol["content"]
                code_match = re.search(r'```python3?\n(.*?)```', content, re.DOTALL)
                if code_match:
                    print(f"✅ Found community solution: {sol['title']}")
                    return code_match.group(1).strip()
    return None

def get_solution_from_gemini(title, description, tags, attempt=1):
    print(f"🤖 Gemini solving (attempt {attempt})...")
    
    tags_str = ", ".join(tags) if tags else "unknown"
    
    prompt = f"""You are a world-class competitive programmer. 
Solve this LeetCode problem with a CORRECT and COMPLETE Python3 solution.

Problem: {title}
Topic Tags: {tags_str}

Description:
{description}

CRITICAL RULES:
1. Return ONLY raw Python3 code — no markdown, no backticks, no explanation
2. Include ALL necessary imports at the top
3. The solution must handle ALL edge cases
4. Use the most reliable algorithm for this problem type
5. Make sure variable names and logic are correct

{"HINT: Previous attempt had a runtime error. Try a completely different approach." if attempt > 1 else ""}
{"HINT: Use a simpler, more straightforward approach this time." if attempt > 2 else ""}
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
    if resp.status_code != 200:
        print(f"❌ Submit failed: {resp.status_code}")
        return None

    submission_id = resp.json().get("submission_id")
    print(f"✅ Submitted! ID: {submission_id} — waiting for result...")

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
                status = check_data.get("status_msg", state)
                print(f"❌ {status}")
                return status
    return None

def run_agent():
    session = create_session()
    if not check_login(session):
        print("⚠️ Not logged in! Refresh LEETCODE_SESSION.")
        raise SystemExit(1)

    # Get today's daily challenge
    daily = get_daily_challenge(session)
    question = daily["question"]
    title = question["title"]
    slug = question["titleSlug"]
    question_id = question["questionId"]
    difficulty = question["difficulty"]
    tags = [t["name"] for t in question.get("topicTags", [])]
    content = re.sub('<[^<]+?>', '', question["content"])
    link = "https://leetcode.com" + daily["link"]

    print(f"\n📝 Today's Daily: {title} [{difficulty}]")
    print(f"🔗 {link}")
    print(f"🏷️ Tags: {', '.join(tags)}\n")

    # Step 1: Try community solution first
    community_code = get_community_solutions(session, slug)
    if community_code:
        print("--- Community Solution ---")
        print(community_code[:300])
        print("-------------------------\n")
        result = submit_and_check(session, slug, question_id, community_code)
        if result == "Accepted":
            print(f"\n🔥 STREAK MAINTAINED! Accepted via community solution!")
            return

    # Step 2: Try Gemini up to 4 times
    for attempt in range(1, 5):
        solution = get_solution_from_gemini(title, content, tags, attempt)
        print(f"--- Gemini Solution (attempt {attempt}) ---")
        print(solution[:300])
        print("------------------------------------------\n")

        result = submit_and_check(session, slug, question_id, solution)

        if result == "Accepted":
            print(f"\n🔥 STREAK MAINTAINED! Accepted on attempt {attempt}!")
            return
        elif result:
            print(f"⚠️ Attempt {attempt}/4 failed — retrying...\n")
            time.sleep(5)

    print("\n⚠️ Could not get Accepted — check LeetCode manually")
    print("💡 Tip: Refresh LEETCODE_SESSION cookie if this keeps happening")

if __name__ == "__main__":
    run_agent()
