import os
import re
import time
import html
import random
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

# Stop the run after LeetCode returns a Cloudflare challenge.
CLOUDFLARE_BLOCKED = False

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
        "model": "deepseek-ai/deepseek-v4-flash",
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

# =========================================================
# LEETCODE SESSION
# =========================================================
def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)

    if not LEETCODE_SESSION:
        raise SystemExit("❌ LEETCODE_SESSION not found!")

    print("🍪 Using LEETCODE_SESSION cookie...")
    session.cookies.set(
        "LEETCODE_SESSION",
        LEETCODE_SESSION,
        domain=".leetcode.com",
        path="/",
    )

    try:
        response = session.get("https://leetcode.com/", timeout=REQUEST_TIMEOUT)
        csrf = session.cookies.get("csrftoken", "")
        if csrf:
            session.headers["X-CSRFToken"] = csrf
        if response.status_code >= 400:
            print(f"⚠️ LeetCode homepage returned HTTP {response.status_code}")
    except requests.RequestException as exc:
        print(f"⚠️ LeetCode session initialization warning: {exc}")

    return session


def check_login(session):
    try:
        resp = session.post(
            "https://leetcode.com/graphql",
            json={"query": "{ userStatus { username isSignedIn } }"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("userStatus", {})
        username = data.get("username", "")
        signed_in = bool(data.get("isSignedIn", False))
        print(f"👤 User: {username or '***'} | Signed in: {signed_in}")
        if not signed_in:
            raise SystemExit("❌ Cookie expired or login unavailable.")
        return True
    except requests.RequestException as exc:
        raise SystemExit(f"❌ LeetCode login check failed: {exc}")


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
                codeSnippets { lang langSlug code }
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


def get_practice_problems(session, count=3, exclude_slug=None):
    """Fetch a random set of unsolved problems across Easy, Medium and Hard."""
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
        # Empty filters means do not restrict difficulty.
        "filters": {},
    }

    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": variables},
        timeout=15,
    )
    resp.raise_for_status()

    payload = resp.json()
    questions = (
        payload.get("data", {})
        .get("problemsetQuestionList", {})
        .get("questions", [])
    )

    # Keep only valid, unsolved questions and exclude today's Daily Challenge.
    unsolved = [
        q for q in questions
        if q.get("titleSlug")
        and q.get("questionId")
        and q.get("status") != "ac"
        and q.get("titleSlug") != exclude_slug
        and q.get("difficulty") in {"Easy", "Medium", "Hard"}
    ]

    # Randomize the candidates so the agent is not stuck on the first
    # questions returned by LeetCode's default ordering.
    random.shuffle(unsolved)

    selected = unsolved[:count]
    if len(selected) < count:
        raise RuntimeError(
            f"Only found {len(selected)} unsolved practice problems; "
            f"needed {count}."
        )

    print(
        "🎲 Selected practice difficulties: "
        + ", ".join(q.get("difficulty", "Unknown") for q in selected)
    )
    return selected


def get_problem_content(session, slug):
    query = """
    query questionContent($titleSlug: String!) {
        question(titleSlug: $titleSlug) {
            questionId
            title
            content
            topicTags { name }
            codeSnippets { lang langSlug code }
        }
    }
    """

    resp = session.post(
        "https://leetcode.com/graphql",
        json={"query": query, "variables": {"titleSlug": slug}},
        timeout=15,
    )
    resp.raise_for_status()
    payload = resp.json()
    question = (payload.get("data") or {}).get("question")
    if not isinstance(question, dict):
        return None
    return question

# =========================================================
# COMMUNITY SOLUTION
# =========================================================
def extract_python_code(text):
    if not text:
        return None

    text = html.unescape(str(text))
    patterns = [
        r"```python3\s*(.*?)```",
        r"```python\s*(.*?)```",
        r"```py\s*(.*?)```",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, re.DOTALL | re.IGNORECASE):
            code = match.strip()
            if code:
                return code

    # Some solution articles store code in HTML rather than Markdown.
    for match in re.findall(
        r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>",
        text,
        re.DOTALL | re.IGNORECASE,
    ):
        code = html.unescape(re.sub(r"<[^>]+>", "", match)).strip()
        if code:
            return code

    return None


def get_community_solutions(session, slug):
    """Fetch Python solution articles using LeetCode's article GraphQL fields."""
    articles_query = """
    query questionSolutionArticles(
        $questionSlug: String!, $skip: Int!, $first: Int!,
        $orderBy: SolutionArticleOrderBy!
    ) {
        questionSolutionArticles(
            questionSlug: $questionSlug,
            skip: $skip,
            first: $first,
            orderBy: $orderBy
        ) {
            edges {
                node {
                    slug
                    title
                }
            }
        }
    }
    """

    try:
        response = session.post(
            "https://leetcode.com/graphql",
            json={
                "query": articles_query,
                "variables": {
                    "questionSlug": slug,
                    "skip": 0,
                    "first": 10,
                    "orderBy": "DEFAULT",
                },
            },
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            print(
                f"⚠️ Community article list failed: HTTP {response.status_code} | "
                f"{response.text[:350].replace(chr(10), ' ')}"
            )
            return None

        payload = response.json()
        if payload.get("errors"):
            print(f"⚠️ Community GraphQL errors: {payload['errors'][:2]}")
            return None

        edges = (
            payload.get("data", {})
            .get("questionSolutionArticles", {})
            .get("edges", [])
        )
    except (requests.RequestException, ValueError, TypeError) as exc:
        print(f"⚠️ Community API request failed: {exc}")
        return None

    detail_query = """
    query solutionArticle($slug: String!, $orderBy: SolutionArticleOrderBy!) {
        solutionArticle(slug: $slug, orderBy: $orderBy) {
            title
            content
            langSlug
        }
    }
    """

    for edge in edges:
        node = (edge or {}).get("node") or {}
        article_slug = node.get("slug")
        if not article_slug:
            continue
        try:
            detail_response = session.post(
                "https://leetcode.com/graphql",
                json={
                    "query": detail_query,
                    "variables": {
                        "slug": article_slug,
                        "orderBy": "DEFAULT",
                    },
                },
                timeout=REQUEST_TIMEOUT,
            )
            if detail_response.status_code != 200:
                continue
            detail_payload = detail_response.json()
            article = (
                detail_payload.get("data", {}).get("solutionArticle") or {}
            )
            if article.get("langSlug") not in (None, "python3", "python"):
                continue
            code = extract_python_code(article.get("content"))
            if code:
                print(f"✅ Found Python community article: {article.get('title') or node.get('title')}")
                return code
        except (requests.RequestException, ValueError, TypeError) as exc:
            print(f"⚠️ Community article detail failed: {exc}")

    return None


# =========================================================
# AI PROMPT / RESPONSE CLEANUP
# =========================================================
def get_python_starter_code(question):
    """Return LeetCode's official Python3 starter template, if available."""
    snippets = (question or {}).get("codeSnippets") or []
    for snippet in snippets:
        lang_slug = (snippet.get("langSlug") or "").lower()
        lang = (snippet.get("lang") or "").lower()
        if lang_slug in {"python3", "python"} or lang in {"python3", "python"}:
            return snippet.get("code") or ""
    return ""


def get_required_method_name(starter_code):
    """Extract the method name LeetCode's driver expects."""
    if not starter_code:
        return None
    match = re.search(
        r"^\s*def\s+([A-Za-z_]\w*)\s*\(",
        starter_code,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def solution_has_required_method(solution, required_method):
    if not required_method:
        return True
    pattern = rf"^\s*def\s+{re.escape(required_method)}\s*\("
    return re.search(pattern, solution or "", re.MULTILINE) is not None


def build_prompt(title, content, tags, starter_code=""):
    tags_str = ", ".join(tags) if tags else ""
    required_method = get_required_method_name(starter_code)

    if starter_code:
        starter_section = (
            "Official LeetCode Python3 starter code. Preserve its exact "
            "class and method names:\n" + starter_code
        )
    else:
        starter_section = (
            "Official Python3 starter code was unavailable. Infer the "
            "exact required LeetCode signature carefully."
        )

    method_rule = (
        f"- REQUIRED method name: {required_method}. The Solution class "
        f"MUST define this exact method name.\n"
        if required_method else
        "- Preserve the exact LeetCode method signature; do not invent or rename it.\n"
    )

    return f"""You are solving a LeetCode problem. Produce a correct Python3 submission.

Problem: {title}
Tags: {tags_str}

Problem statement:
{content}

{starter_section}

STRICT REQUIREMENTS:
- Return ONLY complete raw Python3 code. No Markdown fences or explanation.
- Keep class Solution and preserve the exact method name and parameters from the official starter code.
{method_rule}- Do not substitute a similarly named method (for example, minScore is NOT minimizeSum).
- Include necessary imports.
- Handle edge cases and use an efficient algorithm.
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
            print(f"❌ {name}: empty/invalid response shape: {str(data)[:350]}")
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


def get_solution_from_ai(title, content, tags, starter_code=''):
    prompt = build_prompt(title, content, tags, starter_code)
    required_method = get_required_method_name(starter_code)

    print("\n🔄 AI FALLBACK CHAIN START")
    configured = 0

    for provider in AI_PROVIDERS:
        if not provider.get("key") or not provider.get("url"):
            continue

        configured += 1
        solution = call_ai_provider(provider, prompt)
        if not solution:
            continue

        if not solution_has_required_method(solution, required_method):
            print(
                f"⚠️ {provider['name']} used the wrong method signature; "
                f"expected {required_method}. Trying the next provider."
            )
            continue

        return solution, provider["name"]

    if configured == 0:
        print("❌ No AI provider is configured.")
    else:
        print("❌ No provider returned a solution with the required method signature.")

    return None, None

# =========================================================
# SUBMIT
# =========================================================
def submit_and_check(session, slug, question_id, solution):
    global CLOUDFLARE_BLOCKED
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
            CLOUDFLARE_BLOCKED = True
            print("🛑 LeetCode submission blocked by Cloudflare challenge.")
            print("🛑 Stopping the entire run to avoid wasting AI API calls.")
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
def solve_problem(session, title, slug, question_id, content, tags, starter_code="", label=""):
    print(f"\n{'=' * 60}")
    print(f"📝 {label}: {title}")
    print(f"🔗 https://leetcode.com/problems/{slug}/")
    print(f"{'=' * 60}")

    # -----------------------------------------------------
    # 1. COMMUNITY FIRST
    # -----------------------------------------------------
    print("👥 Checking community solution...")
    community = get_community_solutions(session, slug)

    required_method = get_required_method_name(starter_code)
    if community and not solution_has_required_method(community, required_method):
        print(f"⚠️ Community code has the wrong method signature; expected {required_method}. Skipping it.")
        community = None

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
    solution, provider_name = get_solution_from_ai(title, content, tags, starter_code)

    if solution and not solution_has_required_method(solution, required_method):
        print(f"⚠️ {provider_name} returned the wrong method signature; expected {required_method}. Skipping submission.")
        solution = None

    if not solution:
        print(f"⚠️ Could not generate a valid-signature solution: {title}")
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
    prompt = build_prompt(title, content, tags, starter_code)

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
        if not solution_has_required_method(solution, required_method):
            print(f"⚠️ {provider['name']} returned the wrong method signature; expected {required_method}. Skipping submission.")
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
    print("🎯 Target: 4 questions/day = 1 Daily + 3 random Easy/Medium/Hard")
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

    raw_daily_content = q.get("content") or ""
    content = re.sub(r"<[^<]+?>", " ", raw_daily_content)
    content = re.sub(r"\s+", " ", content).strip()
    tags = [t.get("name", "") for t in q.get("topicTags", []) if t.get("name")]

    print(f"Problem: {q['title']} [{q['difficulty']}]")

    if not content:
        print("⚠️ Daily problem statement is empty. Skipping this problem safely.")
        daily_ok = False
    else:
        daily_ok = solve_problem(
            session,
            q["title"],
            q["titleSlug"],
            q["questionId"],
            content,
            tags,
            starter_code=get_python_starter_code(q),
            label="Daily Challenge",
        )

    results.append(("🔥 Daily Challenge", q["title"], q["difficulty"], daily_ok))
    time.sleep(10)

    if CLOUDFLARE_BLOCKED:
        print("🛑 Run stopped because LeetCode presented a Cloudflare challenge.")
        return

    # -----------------------------------------------------
    # PROBLEMS 2-4: 3 RANDOM PRACTICE QUESTIONS (EASY / MEDIUM / HARD)
    # -----------------------------------------------------
    print("\n📚 RANDOM PRACTICE PROBLEMS (3: EASY / MEDIUM / HARD)")
    practice_problems = get_practice_problems(session, count=3, exclude_slug=q.get("titleSlug"))

    for i, eq in enumerate(practice_problems, 1):
        if CLOUDFLARE_BLOCKED:
            print("🛑 Skipping remaining practice problems after Cloudflare challenge.")
            break

        data = get_problem_content(session, eq["titleSlug"])
        if not data:
            print(f"⚠️ Could not fetch statement for {eq.get('title')}. Skipping.")
            results.append((f"📘 Practice #{i}", eq.get("title", "Unknown"), eq.get("difficulty", "Unknown"), False))
            continue

        raw_content = data.get("content") or ""
        easy_content = re.sub(r"<[^<]+?>", " ", raw_content)
        easy_content = re.sub(r"\s+", " ", easy_content).strip()
        easy_tags = [t.get("name", "") for t in (data.get("topicTags") or []) if t.get("name")]

        if not easy_content:
            print(f"⚠️ Empty problem statement for {eq.get('title')}. Skipping.")
            results.append((f"📘 Practice #{i}", eq.get("title", "Unknown"), eq.get("difficulty", "Unknown"), False))
            continue

        ok = solve_problem(
            session,
            eq["title"],
            eq["titleSlug"],
            eq["questionId"],
            easy_content,
            easy_tags,
            starter_code=get_python_starter_code(data),
            label=f"Practice #{i}",
        )

        results.append((f"📘 Practice #{i}", eq["title"], eq.get("difficulty", "Unknown"), ok))
        if CLOUDFLARE_BLOCKED:
            print("🛑 Ending workflow run after Cloudflare challenge.")
            break
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
