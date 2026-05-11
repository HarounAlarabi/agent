"""Data types for the Educational Content Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EduContentType(str, Enum):
    MINI_LESSON         = "Mini lesson"
    BEGINNER_EXPLAINER  = "Beginner explainer"
    AI_CONCEPT          = "AI concept breakdown"
    PROMPT_ENGINEERING  = "Prompt engineering tip"
    WORKFLOW_TIP        = "Workflow tutorial"
    WHAT_I_LEARNED      = "What I learned"
    TOOL_RECOMMENDATION = "Tool recommendation"
    CODING_INSIGHT      = "Coding insight"
    SIMPLIFICATION      = "Technical simplification"
    CHEAT_SHEET         = "Cheat sheet"
    COMMON_MISTAKES     = "Common mistakes"
    PRACTICAL_EXAMPLE   = "Practical example"
    LEARNING_THREAD     = "Learning thread"
    CURATED_RESOURCE    = "Curated resource"


class Difficulty(str, Enum):
    BEGINNER     = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED     = "Advanced"


class ResourceCategory(str, Enum):
    AI_ML              = "AI / Machine Learning"
    PROMPT_ENGINEERING = "Prompt Engineering"
    WEB_DEV            = "Web Development"
    DEVOPS             = "DevOps / Infrastructure"
    SYSTEM_DESIGN      = "System Design"
    TOOLS              = "Developer Tools"
    CAREER             = "Career & Productivity"
    OPEN_SOURCE        = "Open Source"
    SECURITY           = "Security"
    DATA               = "Data & Analytics"
    OTHER              = "Other"


class ThreadType(str, Enum):
    CONCEPT      = "concept"
    TUTORIAL     = "tutorial"
    MISTAKES     = "mistakes"
    COMPARISON   = "comparison"
    WHAT_LEARNED = "what_i_learned"
    RESOURCE_LIST = "resource_roundup"


THREAD_STRUCTURES: dict[str, str] = {
    ThreadType.CONCEPT: (
        "1. Hook (why this matters right now)\n"
        "2. What it is (simple definition)\n"
        "3. Why it matters (practical impact)\n"
        "4. How it works (simplified mechanics)\n"
        "5. Real-world example\n"
        "6. Common mistake or misconception\n"
        "7. Takeaway or recommendation"
    ),
    ThreadType.TUTORIAL: (
        "1. Hook (the problem you're solving)\n"
        "2. Context (when does this apply)\n"
        "3. Step 1\n"
        "4. Step 2\n"
        "5. Step 3\n"
        "6. Common gotchas\n"
        "7. Summary and next steps"
    ),
    ThreadType.MISTAKES: (
        "1. Hook (the mistake, framed as a shared experience)\n"
        "2. What the mistake looks like in practice\n"
        "3. Why developers make it\n"
        "4. The fix\n"
        "5. Prevention strategy\n"
        "6. Honest lesson"
    ),
    ThreadType.COMPARISON: (
        "1. Hook (why this comparison is worth making)\n"
        "2. Option A — what it is, when it shines\n"
        "3. Option B — what it is, when it shines\n"
        "4. The key difference\n"
        "5. When to use which (concrete scenarios)\n"
        "6. Honest verdict"
    ),
    ThreadType.WHAT_LEARNED: (
        "1. Hook (what triggered this discovery)\n"
        "2. The context / backstory\n"
        "3. What I found or learned\n"
        "4. The surprising / non-obvious part\n"
        "5. How I'm applying it\n"
        "6. What I'd recommend trying"
    ),
    ThreadType.RESOURCE_LIST: (
        "1. Hook (why these resources, why now)\n"
        "2. Resource 1 + genuine observation\n"
        "3. Resource 2 + genuine observation\n"
        "4. Resource 3 + genuine observation\n"
        "5. Key pattern or insight across all of them\n"
        "6. Where to start if you're new to this"
    ),
}


@dataclass
class EduPost:
    content: str
    content_type: EduContentType
    topic: str
    difficulty: Difficulty
    language: str
    is_thread: bool = False
    thread_tweets: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    originality_passed: bool = True
    voice_corrected: bool = False
    claim_downgraded: bool = False


@dataclass
class CuratedResource:
    url: str
    url_hash: str
    title: str
    topic: str
    category: ResourceCategory
    difficulty: Difficulty
    usefulness_score: float
    summary: str
    original_commentary: str
    key_strength: str = ""
    audience: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class LearningSeries:
    id: int
    name: str
    topic: str
    post_count: int
    created_at: str
    last_post_at: str = ""
