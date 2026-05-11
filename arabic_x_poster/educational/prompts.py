"""Prompt templates for the Educational Content Engine."""

EDU_MINI_POST_PROMPT = """Write a short educational post for a developer's X/Twitter account.

Content type: {content_type}
Topic: {topic}
Difficulty: {difficulty}
Language: {language}
Audience: {audience}

Continuity context (avoid repeating these recent ideas):
{continuity_context}

Learning series context (if applicable):
{series_context}

Style rules:
- Sound like a developer who just figured something out and is sharing it casually
- Short paragraphs (1–2 sentences each), white space matters
- Specific over generic — use a real example or scenario if possible
- End with something that invites engagement: a question, small observation, or honest reflection
- Don't over-explain — trust the reader's intelligence
- Prefer "I've been learning…" over "Here's the definitive guide…"
- Prefer "I noticed…" over "Experts say…"

Difficulty calibration:
- Beginner: explain jargon, use analogies, assume very little prior knowledge
- Intermediate: assume basic knowledge, focus on the specific insight
- Advanced: peer-level, skip the basics, get into the nuanced details

Forbidden phrases: "Here are X things", "game-changing", "unlock", "supercharge",
"In today's fast-paced world", "Let's dive in", "revolutionary"

NEVER sound like a textbook, corporate training, or LinkedIn influencer.

Return ONLY the post text. No labels, no meta-commentary.
"""

EDU_THREAD_PROMPT = """Write an educational X/Twitter thread for developers.

Thread type: {thread_type}
Topic: {topic}
Difficulty: {difficulty}
Language: {language}
Number of tweets: {n_tweets}
Audience: {audience}

Continuity context (avoid repeating):
{continuity_context}

Thread structure to follow exactly:
{thread_structure}

Thread rules:
- Tweet 1 = the hook (make people want to keep reading, not a summary)
- Each tweet = one clear idea, no more
- Under 260 characters per tweet (leave room for numbering)
- Natural flow — each tweet should make the next one feel necessary
- Sound like a developer explaining to a peer, not presenting a slide deck
- Last tweet: practical recommendation, honest reflection, or a question
- No "Thread 🧵", no "1/" counters, no excessive emojis
- Short sentences, real examples, no fluff

Return numbered tweets only:
1. [tweet text]
2. [tweet text]
...
"""

EDU_RESOURCE_COMMENTARY_PROMPT = """Write original developer commentary about this learning resource.

Resource:
Title: {title}
URL: {url}
Summary: {summary}
Category: {category}

Rules:
- Share your genuine reaction as a developer who has reviewed this
- Explain specifically WHY it is useful, not just what it covers
- Be concrete: mention what makes it stand out vs other resources on the topic
- Include a small personal observation or what clicked for you
- Sound like a real person recommending something to a developer friend
- Do NOT restate the title as the first sentence
- Do NOT say "Here is a resource about…"

GOOD example:
"This prompt engineering guide finally made context window sizing make sense to me.
The examples use realistic API calls instead of toy prompts — that's rare.
If you've been guessing at token limits, this is worth 20 minutes."

BAD example:
"Here is a guide about prompt engineering. It covers many important topics."

Language: {language}
Length: 2–3 short paragraphs max

Return ONLY the commentary text.
"""

EDU_USEFULNESS_EVAL_PROMPT = """Evaluate this developer learning resource for usefulness and categorisation.

Title: {title}
URL: {url}
Content preview: {content_preview}

Return ONLY valid JSON:
{{
  "topic": "main topic in 3–6 words",
  "category": "one of: ai_ml | prompt_engineering | web_dev | devops | system_design | tools | career | open_source | security | data | other",
  "difficulty": "one of: beginner | intermediate | advanced",
  "usefulness_score": 7,
  "key_strength": "one sentence on what makes this resource specifically valuable",
  "audience": "one sentence on who benefits most",
  "summary": "2–3 sentence factual summary of what the resource covers"
}}
"""

EDU_SIMPLIFICATION_PROMPT = """Explain this technical concept for a developer audience.

Concept: {concept}
Difficulty: {difficulty}
Language: {language}

Rules:
- Use an analogy only if it genuinely helps (and make it accurate)
- One key insight per explanation — don't try to cover everything
- Use concrete examples, not abstract descriptions
- Sound like you're explaining to a smart colleague, not a classroom
- If the topic has nuance or exceptions, be honest about that
- Prefer "it works like…" over "technically speaking, the algorithm…"

Return 2–4 short paragraphs. This will be used as the basis for a post or thread.
"""

EDU_TRUSTED_SOURCE_POST_PROMPT = """Write a short developer post inspired by this educational resource.

Source title: {title}
Platform: {source_platform}
Category: {category}
Difficulty: {difficulty}
Summary: {summary}
Language: {language}
Audience: {audience}

Post angle: {angle}

Rules:
- Write as a developer sharing something they genuinely found useful — not a book report
- Lead with what was personally interesting or surprising, not a description of the resource
- Be specific: name what concept, insight, or example stood out
- Reference the source naturally (e.g. "This {source_platform} piece on…" or "Came across this on {source_platform}…")
- Sound curious and human, not like a content marketer or academic
- Short paragraphs, real language, no buzzwords
- 2–4 short paragraphs maximum
- Optional: end with a question, an honest reflection, or a practical recommendation

GOOD example:
"This MIT lecture on attention mechanisms finally made the Q/K/V matrix split click for me.
Most explanations jump straight to the math — this one starts with why you'd want to 'attend'
to different parts of input at all. Worth 30 min if you've been cargo-culting transformers."

BAD example:
"Here is an interesting resource from MIT about transformers. It covers many important topics
including attention mechanisms, matrix operations, and more. I recommend checking it out."

Forbidden phrases: "game-changing", "unlock potential", "In today's fast-paced world",
"Let's dive in", "Here are N things", "comprehensive guide", "revolutionary"

Return ONLY the post text. No labels, no meta-commentary.
"""

EDU_TRUSTED_SOURCE_THREAD_PROMPT = """Write an educational X/Twitter thread inspired by this resource.

Source title: {title}
Platform: {source_platform}
Category: {category}
Difficulty: {difficulty}
Summary: {summary}
Number of tweets: {n_tweets}
Language: {language}
Audience: {audience}

Thread angle: {angle}

Thread rules:
- Tweet 1 = hook. Start with the insight, the surprising thing, or the tension — NOT "Here's a thread about…"
- Each tweet = one clear idea. Under 260 chars.
- Reference the source platform naturally in tweet 1 or 2 — not robotically in every tweet
- Sound like a developer explaining something to a peer who asked about it
- Last tweet: practical observation, recommendation, or honest question
- No "Thread 🧵" opener, no excessive emojis, no "1/" counters
- Generate ORIGINAL insights inspired by the material — don't just summarise headings

Return numbered tweets only:
1. [tweet text]
2. [tweet text]
...
"""

EDU_SERIES_CONTINUATION_PROMPT = """Write the next post in a learning series.

Series topic: {series_topic}
Series name: {series_name}
Posts already published in this series:
{previous_posts}

Next post should cover: {next_topic}
Difficulty: {difficulty}
Language: {language}
Content type: {content_type}

Rules:
- Reference earlier posts naturally when relevant (not awkwardly)
- Build on what was already covered without repeating it
- Feel like a continuation of a real learning journey
- Maintain the same voice and level of detail
- Sound like someone who's been sharing their learning publicly for a while

Return ONLY the post text.
"""
