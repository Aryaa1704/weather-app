import os
import re
import time
import json
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

LEETCODE_USERNAME = os.getenv("LEETCODE_USERNAME")
LEETCODE_PASSWORD = os.getenv("LEETCODE_PASSWORD")
LEETCODE_SESSION = os.getenv("LEETCODE_SESSION")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
HF_TOKEN = os.getenv("HF_TOKEN")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com/",
    "Origin": "https://leetcode.com",
}

REQUEST_TIMEOUT = 45
MAX_OUTPUT_TOKENS = 4096

AI_PROVIDERS = [
    {
        "name": "Gemini",
        "key": GEMINI_API_KEY,
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-3.8-flash",
    },
    {
        "name": "Groq",
        "key": GROQ_API_KEY,
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "openai/gpt-oss-120b",
    },
    {
        "name": "NVIDIA NIM",
        "key": NVIDIA_API_KEY,
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": "openai/gpt-oss-120b",
    },
    {
        "name": "Cerebras",
        "key": CEREBRAS_API_KEY,
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "model": "gpt-oss-120b",
    },
    {
        "name": "SambaNova",
        "key": SAMBANOVA_API_KEY,
        "url": "https://api.sambanova.ai/v1/chat/completions",
        "model": "gpt-oss-120b",
    },
    {
        "name": "Mistral AI",
        "key": MISTRAL_API_KEY,
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-small-latest",
    },
    {
        "name": "OpenRouter",
        "key": OPENROUTER_API_KEY,
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "openrouter/free",
    },
    {
        "name": "Cloudflare Workers AI",
        "key": CLOUDFLARE_API_TOKEN,
        "url": (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions"
            if CLOUDFLARE_ACCOUNT_ID
            else None
        ),
        "model": "@cf/openai/gpt-oss-120b",
    },
    {
        "name": "Hugging Face",
        "key": HF_TOKEN,
        "url": "https://router.huggingface.co/v1/chat/completions",
        "model": "openai/gpt-oss-120b:fastest",
    },
]


def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    if LEETCODE_SESSION:
        print("🍪 Using LEETCODE_SESSION cookie...")
        session.cookies.set("LEETCODE_SESSION", LEETCODE_SESSION, domain="leetcode.com")
        session.get("https://leetcode.com/", timeout=15)
        csrf = session.cookies.get("csrftoken", "")
        session.headers.update({"X-CSRFToken": csrf})
        return session
    raise SystemExit("❌ LEETCODE_SESSION not found!")


def check_login(session):
    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": "{ userStatus { username isSignedIn } }"},
        timeout=10,
    )
    data = resp.json().get("data", {}).get("userStatus", {})
    username = data.get("username", "")
    signed_in = data.get("isSignedIn", False)
    print(f"👤 User: {username} | Signed in: {signed_in}")
    if not signed_in:
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
    resp.raise_for_status()
    return resp.json()["data"]["activeDailyCodingChallengeQuestion"]


def get_easy_problems(session, count=3):
    query = """
    query problemsetQuestionList(
        $categorySlug: String,
        $limit: Int,
        $skip: Int,
        $filters: QuestionListFilterInput
    ) {
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
    variables = {"categorySlug": "", "limit": 100, "skip": 0, "filters": {"difficulty": "EASY"}}
    resp = session.post("https://leetcode.com/graphql", json={"query": query, "variables": variables}, timeout=15)
    resp.raise_for_status()
    questions = resp.json()["data"]["problemsetQuestionList"]["questions"]
    unsolved = [q for q in questions if q.get("status") != "ac"]
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
    resp = session.post("https://leetcode.com/graphql", json={"query": query, "variables": {"titleSlug": slug}}, timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]["question"]


def extract_python_code(text):
    if not text:
        return None
    patterns = [
        r"```python3\s*(.*?)```",
        r"```python\s*(.*?)```",
        r"```py\s*(.*?)```",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def build_prompt(title, content, tags):
    tags_str = ", ".join(tags) if tags else ""
    return f"""You are a world-class competitive programmer.
Solve this LeetCode problem with a CORRECT Python3 solution.

Problem: {title}
Tags: {tags_str}

Description:
{content}

RULES:
- Return ONLY raw Python3 code.
- No markdown.
- No backticks.
- No explanation.
- Include all necessary imports.
- Match the exact LeetCode function/class signature required by the problem.
- Handle edge cases.
- Prefer a correct efficient solution suitable for LeetCode constraints.
"""


def clean_ai_code(text):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```python3?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip() or None


def extract_response_text(payload):
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)
    return None


def call_ai_provider(provider, prompt):
    name = provider["name"]
    api_key = provider.get("key")
    url = provider.get("url")
    model = provider.get("model")

    if not api_key:
        print(f"⏭️ {name}: API key not configured")
        return None
    if not url:
        print(f"⏭️ {name}: configuration incomplete")
        return None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if name == "OpenRouter":
        headers["HTTP-Referer"] = "https://github.com/"
        headers["X-Title"] = "LeetCode Daily Agent"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only the complete raw Python3 LeetCode solution."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": False,
    }

    try:
        print(f"🤖 Trying {name} ({model})...")
        resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            body = resp.text[:500].replace("\n", " ")
            print(f"❌ {name} failed: HTTP {resp.status_code} | {body}")
            return None
        data = resp.json()
        text = extract_response_text(data)
        code = clean_ai_code(text)
        if not code:
            print(f"❌ {name}: empty/invalid response")
            return None
        print(f"✅ {name}: solution generated")
        return code
    except requests.Timeout:
        print(f"⏱️ {name}: timeout")
    except requests.RequestException as e:
        print(f"❌ {name}: network error: {e}")
    except Exception as e:
        print(f"❌ {name}: unexpected error: {e}")
    return None


def get_solution_from_ai(title, content, tags):
    prompt = build_prompt(title, content, tags)
    print("\n🔄 AI FALLBACK CHAIN START")
    configured = 0
    for provider in AI_PROVIDERS:
        if provider.get("key") and provider.get("url"):
            configured += 1
            solution = call_ai_provider(provider, prompt)
            if solution:
                return solution, provider["name"]
    if configured == 0:
        print("❌ No AI provider is configured.")
    else:
        print("❌ All configured AI providers failed.")
    return None, None


def submit_via_playwright(slug, question_id, solution):
    """Submit using Playwright browser to bypass Cloudflare."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
            )
            context.add_cookies([{
                "name": "LEETCODE_SESSION",
                "value": LEETCODE_SESSION,
                "domain": "leetcode.com",
                "path": "/"
            }])

            page = context.new_page()
            page.goto(f"https://leetcode.com/problems/{slug}/", wait_until="networkidle", timeout=30000)
            time.sleep(3)

            csrf = ""
            for cookie in context.cookies():
                if cookie["name"] == "csrftoken":
                    csrf = cookie["value"]
                    break

            result = page.evaluate(f"""
                async () => {{
                    const solution = {json.dumps(solution)};
                    const resp = await fetch('/problems/{slug}/submit/', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'X-CSRFToken': '{csrf}',
                            'Referer': 'https://leetcode.com/problems/{slug}/'
                        }},
                        body: JSON.stringify({{
                            lang: 'python3',
                            question_id: '{question_id}',
                            typed_code: solution
                        }})
                    }});
                    return await resp.json();
                }}
            """)

            browser.close()
            submission_id = result.get("submission_id")
            return submission_id

    except Exception as e:
        print(f"❌ Playwright submit error: {e}")
        return None


def check_submission(session, submission_id):
    for _ in range(20):
        time.sleep(3)
        try:
            check = session.get(
                f"https://leetcode.com/submissions/detail/{submission_id}/check/",
                timeout=10,
            )
        except requests.RequestException:
            continue
        if check.status_code != 200:
            continue
        try:
            check_data = check.json()
        except ValueError:
            continue
        state = check_data.get("state", "")
        if state == "SUCCESS":
            status = check_data.get("status_msg", "Unknown")
            print(f"🎯 Result: {status}")
            return status
        if state in ["FAILURE", "RUNTIME_ERROR", "COMPILE_ERROR", "WRONG_ANSWER"]:
            status = check_data.get("status_msg", state)
            print(f"❌ {status}")
            return status
    print("⏱️ Submission timeout")
    return "SUBMISSION_TIMEOUT"


def submit_and_check(session, slug, question_id, solution):
    csrf = session.cookies.get("csrftoken", "")
    session.headers.update({
        "X-CSRFToken": csrf,
        "Referer": f"https://leetcode.com/problems/{slug}/",
    })

    try:
        resp = session.post(
            f"https://leetcode.com/problems/{slug}/submit/",
            json={"lang": "python3", "question_id": str(question_id), "typed_code": solution},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"❌ Submit request error: {e}")
        return "SUBMISSION_ERROR"

    if resp.status_code == 403 and (
        "just a moment" in resp.text.lower()
        or "cloudflare" in resp.text.lower()
        or "challenges.cloudflare.com" in resp.text.lower()
    ):
        print("🌐 Cloudflare detected — switching to Playwright...")
        submission_id = submit_via_playwright(slug, question_id, solution)
        if submission_id:
            print(f"📤 Submitted via Playwright! ID: {submission_id}")
            return check_submission(session, submission_id)
        else:
            print("🛑 Playwright submission also failed.")
            return "SUBMISSION_BLOCKED"

    if resp.status_code != 200:
        print(f"❌ Submit failed: {resp.status_code}")
        return "SUBMISSION_ERROR"

    try:
        submission_id = resp.json().get("submission_id")
    except ValueError:
        print("❌ Submit returned non-JSON response.")
        return "SUBMISSION_ERROR"

    print(f"📤 Submitted! ID: {submission_id}")
    if not submission_id:
        return "SUBMISSION_ERROR"

    return check_submission(session, submission_id)


def solve_problem(session, title, slug, question_id, content, tags, label=""):
    print(f"\n{'=' * 60}")
    print(f"📝 {label}: {title}")
    print(f"🔗 https://leetcode.com/problems/{slug}/")
    print(f"{'=' * 60}")

    solution, provider_name = get_solution_from_ai(title, content, tags)

    if not solution:
        print(f"⚠️ Could not generate a solution: {title}")
        return False

    result = submit_and_check(session, slug, question_id, solution)

    if result == "Accepted":
        print(f"🎉 Accepted via {provider_name}!")
        return True
    if result == "SUBMISSION_BLOCKED":
        return False

    prompt = build_prompt(title, content, tags)
    passed_provider = False

    for provider in AI_PROVIDERS:
        if provider["name"] == provider_name:
            passed_provider = True
            continue
        if not passed_provider:
            continue
        if not provider.get("key") or not provider.get("url"):
            continue

        solution = call_ai_provider(provider, prompt)
        if not solution:
            continue

        result = submit_and_check(session, slug, question_id, solution)
        if result == "Accepted":
            print(f"🎉 Accepted via {provider['name']}!")
            return True
        if result == "SUBMISSION_BLOCKED":
            return False

    print(f"⚠️ All available providers exhausted: {title}")
    return False


def run_agent():
    print("🚀 LeetCode Agent Starting...")
    print("🎯 Target: 4 questions/day = 1 Daily + 3 Easy")
    print("🔁 Flow: AI providers → Playwright fallback → FAILED")

    session = create_session()
    check_login(session)

    results = []

    print("\n🔥 DAILY CHALLENGE (Streak)")
    daily = get_daily_challenge(session)
    q = daily["question"]

    content = re.sub(r"<[^<]+?>", " ", q["content"] or "")
    content = re.sub(r"\s+", " ", content).strip()
    tags = [t["name"] for t in q.get("topicTags", [])]

    print(f"Problem: {q['title']} [{q['difficulty']}]")

    daily_ok = solve_problem(
        session, q["title"], q["titleSlug"], q["questionId"],
        content, tags, label="Daily Challenge",
    )
    results.append(("🔥 Daily Challenge", q["title"], q["difficulty"], daily_ok))
    time.sleep(10)

    print("\n📚 EASY PRACTICE PROBLEMS (3)")
    easy_problems = get_easy_problems(session, count=3)

    for i, eq in enumerate(easy_problems, 1):
        data = get_problem_content(session, eq["titleSlug"])
        easy_content = re.sub(r"<[^<]+?>", " ", data["content"] or "")
        easy_content = re.sub(r"\s+", " ", easy_content).strip()
        easy_tags = [t["name"] for t in data.get("topicTags", [])]

        ok = solve_problem(
            session, eq["title"], eq["titleSlug"], eq["questionId"],
            easy_content, easy_tags, label=f"Easy #{i}",
        )
        results.append((f"📗 Easy #{i}", eq["title"], "Easy", ok))
        time.sleep(10)

    print("\n" + "=" * 60)
    print("📊 FINAL SUMMARY")
    print("=" * 60)

    total_solved = 0
    for label, title, diff, success in results:
        status = "✅ Accepted" if success else "❌ Failed"
        print(f"{status} | {label}: {title} [{diff}]")
        if success:
            total_solved += 1

    print(f"\n🎯 Solved: {total_solved}/4")

    if results and results[0][3]:
        print("🔥 STREAK MAINTAINED!")
    else:
        print("⚠️ Daily challenge failed — streak at risk!")


if __name__ == "__main__":
    run_agent()
