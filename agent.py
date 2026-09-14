import os
import re
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# ENV
# =========================================================
LEETCODE_USERNAME = os.getenv("LEETCODE_USERNAME")
LEETCODE_PASSWORD = os.getenv("LEETCODE_PASSWORD")
LEETCODE_SESSION = os.getenv("LEETCODE_SESSION")

# AI provider keys
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
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# =========================================================
# HTTP
# =========================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com/",
    "Origin": "https://leetcode.com",
}

REQUEST_TIMEOUT = 45
MAX_OUTPUT_TOKENS = 4096

# =========================================================
# AI PROVIDERS
#
# All providers below use an OpenAI-compatible chat endpoint.
# A provider is used only when its key/config exists.
# =========================================================
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
    {
        "name": "Together AI",
        "key": TOGETHER_API_KEY,
        "url": "https://api.together.xyz/v1/chat/completions",
        "model": "openai/gpt-oss-120b",
    },
]

# =========================================================
# LEETCODE SESSION
# =========================================================
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

# =========================================================
# QUESTIONS
# =========================================================
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

    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["data"]["activeDailyCodingChallengeQuestion"]


def get_easy_problems(session, count=3):
    """Fetch first N unsolved Easy problems."""
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

    variables = {
        "categorySlug": "",
        "limit": 100,
        "skip": 0,
        "filters": {"difficulty": "EASY"},
    }

    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": variables},
        timeout=15,
    )
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

    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": {"titleSlug": slug}},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["data"]["question"]

# =========================================================
# COMMUNITY SOLUTION
# =========================================================
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


def get_community_solutions(session, slug):
    query = """
    query communitySolutions(
        $questionSlug: String!,
        $skip: Int!,
        $first: Int!,
        $orderBy: TopicSortingOption,
        $languageTags: [String!]
    ) {
        questionSolutions(
            filters: {
                questionSlug: $questionSlug,
                skip: $skip,
                first: $first,
                orderBy: $orderBy,
                languageTags: $languageTags
            }
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
        "languageTags": ["python3"],
    }

    try:
        resp = session.post(
            "https://leetcode.com/graphql",
            json={"query": query, "variables": variables},
            timeout=15,
        )

        if resp.status_code != 200:
            print(f"⚠️ Community API failed: HTTP {resp.status_code}")
            return None

        payload = resp.json()
        solutions = (
            payload.get("data", {})
            .get("questionSolutions", {})
            .get("solutions", [])
        )

        for sol in solutions:
            if sol.get("langSlug") != "python3":
                continue

            code = extract_python_code(sol.get("content", ""))
            if code:
                return code

    except Exception as e:
        print(f"⚠️ Community solution fetch failed: {e}")

    return None

# =========================================================
# AI PROMPT / RESPONSE CLEANUP
# =========================================================
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

    # Remove fenced markdown if a provider ignores the instruction.
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

    # Some APIs may return structured content chunks.
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)

    return None

# =========================================================
# AI PROVIDER CALL
# =========================================================
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Provider-specific headers that are harmless/useful.
    if name == "OpenRouter":
        headers["HTTP-Referer"] = "https://github.com/"
        headers["X-Title"] = "LeetCode Daily Agent"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Return only the complete raw Python3 LeetCode solution.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.1,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": False,
    }

    try:
        print(f"🤖 Trying {name} ({model})...")
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

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
    except ValueError as e:
        print(f"❌ {name}: invalid JSON response: {e}")
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

# =========================================================
# SUBMIT
# =========================================================
def submit_and_check(session, slug, question_id, solution):
    csrf = session.cookies.get("csrftoken", "")
    session.headers.update({
        "X-CSRFToken": csrf,
        "Referer": f"https://leetcode.com/problems/{slug}/",
    })

    try:
        resp = session.post(
            f"https://leetcode.com/problems/{slug}/submit/",
            json={
                "lang": "python3",
                "question_id": str(question_id),
                "typed_code": solution,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"❌ Submit request error: {e}")
        return "SUBMISSION_ERROR"

    if resp.status_code != 200:
        body = resp.text[:1000]
        print(f"❌ Submit failed: {resp.status_code}")
        print(f"Response: {body}")
        print(f"CSRF present: {bool(csrf)}")
        print(f"Cookies: {list(session.cookies.keys())}")

        # Current GitHub Actions issue: LeetCode/Cloudflare challenge.
        if resp.status_code == 403 and (
            "just a moment" in resp.text.lower()
            or "cloudflare" in resp.text.lower()
            or "challenges.cloudflare.com" in resp.text.lower()
        ):
            print("🛑 LeetCode submission blocked by Cloudflare challenge.")
            print("🛑 Stopping this problem to avoid wasting AI API calls.")
            return "SUBMISSION_BLOCKED"

        return "SUBMISSION_ERROR"

    try:
        submission_id = resp.json().get("submission_id")
    except ValueError:
        print("❌ Submit returned non-JSON response.")
        return "SUBMISSION_ERROR"

    print(f"📤 Submitted! ID: {submission_id}")

    if not submission_id:
        return "SUBMISSION_ERROR"

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

        if state in [
            "FAILURE",
            "RUNTIME_ERROR",
            "COMPILE_ERROR",
            "WRONG_ANSWER",
        ]:
            status = check_data.get("status_msg", state)
            print(f"❌ {status}")
            return status

    print("⏱️ Submission timeout")
    return "SUBMISSION_TIMEOUT"

# =========================================================
# SOLVE ONE PROBLEM
# =========================================================
def solve_problem(session, title, slug, question_id, content, tags, label=""):
    print(f"\n{'=' * 60}")
    print(f"📝 {label}: {title}")
    print(f"🔗 https://leetcode.com/problems/{slug}/")
    print(f"{'=' * 60}")

    # -----------------------------------------------------
    # 1. COMMUNITY FIRST
    # -----------------------------------------------------
    print("👥 Checking community solution...")
    community = get_community_solutions(session, slug)

    if community:
        print("🔍 Trying community solution...")
        result = submit_and_check(session, slug, question_id, community)

        if result == "Accepted":
            print("🎉 Accepted via community solution!")
            return True

        if result == "SUBMISSION_BLOCKED":
            return False

        print("↪️ Community solution did not pass. Moving to AI fallback.")
    else:
        print("ℹ️ No usable Python community solution found.")

    # -----------------------------------------------------
    # 2. AI PROVIDER FALLBACK CHAIN
    # -----------------------------------------------------
    solution, provider_name = get_solution_from_ai(title, content, tags)

    if not solution:
        print(f"⚠️ Could not generate a solution: {title}")
        return False

    # First generated solution from the first working provider.
    # If it is rejected by LeetCode, we do NOT call the same provider again.
    # We continue to the next provider only for a normal judge rejection.
    result = submit_and_check(session, slug, question_id, solution)

    if result == "Accepted":
        print(f"🎉 Accepted via {provider_name}!")
        return True

    if result == "SUBMISSION_BLOCKED":
        return False

    # If the generated solution is wrong, try the remaining providers once.
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

# =========================================================
# MAIN AGENT
# =========================================================
def run_agent():
    print("🚀 LeetCode Agent Starting...")
    print("🎯 Target: 4 questions/day = 1 Daily + 3 Easy")
    print("🔁 Flow: Community → AI providers → next provider → FAILED")

    session = create_session()
    check_login(session)

    results = []

    # -----------------------------------------------------
    # PROBLEM 1: DAILY CHALLENGE
    # -----------------------------------------------------
    print("\n🔥 DAILY CHALLENGE (Streak)")
    daily = get_daily_challenge(session)
    q = daily["question"]

    content = re.sub(r"<[^<]+?>", " ", q["content"])
    content = re.sub(r"\s+", " ", content).strip()
    tags = [t["name"] for t in q.get("topicTags", [])]

    print(f"Problem: {q['title']} [{q['difficulty']}]")

    daily_ok = solve_problem(
        session,
        q["title"],
        q["titleSlug"],
        q["questionId"],
        content,
        tags,
        label="Daily Challenge",
    )

    results.append(("🔥 Daily Challenge", q["title"], q["difficulty"], daily_ok))
    time.sleep(10)

    # -----------------------------------------------------
    # PROBLEMS 2-4: 3 EASY PRACTICE QUESTIONS
    # -----------------------------------------------------
    print("\n📚 EASY PRACTICE PROBLEMS (3)")
    easy_problems = get_easy_problems(session, count=3)

    for i, eq in enumerate(easy_problems, 1):
        data = get_problem_content(session, eq["titleSlug"])
        easy_content = re.sub(r"<[^<]+?>", " ", data["content"])
        easy_content = re.sub(r"\s+", " ", easy_content).strip()
        easy_tags = [t["name"] for t in data.get("topicTags", [])]

        ok = solve_problem(
            session,
            eq["title"],
            eq["titleSlug"],
            eq["questionId"],
            easy_content,
            easy_tags,
            label=f"Easy #{i}",
        )

        results.append((f"📗 Easy #{i}", eq["title"], "Easy", ok))
        time.sleep(10)

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------
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
