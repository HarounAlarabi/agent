"""Educational Content Engine UI tab — rendered by app.py via render_tab()."""

from __future__ import annotations

import streamlit as st

from arabic_x_poster.factory import ServiceFactory
from arabic_x_poster.educational.types import (
    Difficulty,
    EduContentType,
    ThreadType,
    ResourceCategory,
)
from arabic_x_poster.educational.trusted_sources import (
    TRUSTED_SOURCES,
    SOURCES_BY_CATEGORY,
)
from arabic_x_poster.educational.source_pipeline import EDU_TOPICS

CONTENT_TYPES = [e.value for e in EduContentType]
DIFFICULTIES = [e.value for e in Difficulty]
THREAD_TYPES = [e.value.replace("_", " ").title() for e in ThreadType]
THREAD_TYPE_MAP = {e.value.replace("_", " ").title(): e for e in ThreadType}
LANGUAGES = ["English", "Arabic"]
AUDIENCES = ["Beginners", "Intermediate devs", "Advanced / senior devs", "General tech followers"]

TOPIC_PRESETS = [
    "Custom…",
    "Large Language Models (LLMs)",
    "Prompt Engineering",
    "RAG (Retrieval-Augmented Generation)",
    "Fine-tuning vs. prompting",
    "AI agents & tool use",
    "Python basics",
    "APIs & REST",
    "Git workflow",
    "Docker & containers",
    "System design 101",
    "Debugging strategies",
    "Code review skills",
    "React fundamentals",
    "SQL vs NoSQL",
]


def render_tab():
    st.subheader("🎓 Learning & Educational Content")
    st.caption(
        "Generate beginner-friendly explainers, AI concept breakdowns, prompt engineering tips, "
        "educational threads, and curated learning resources — with original developer commentary."
    )

    edu_storage = ServiceFactory.educational_storage()

    # ── Two-column layout ─────────────────────────────────────────────────────
    left, right = st.columns([1, 2], gap="large")

    # ════════════════════════════════════════════════════════════════
    # LEFT PANEL — content controls
    # ════════════════════════════════════════════════════════════════
    with left:
        st.markdown("**Content Setup**")

        # ── Source mode ───────────────────────────────────────────────────────
        source_mode = st.radio(
            "Generate from",
            ["Topic", "Resource from feed"],
            horizontal=True,
            key="edu_source_mode",
        )

        sel_resource: dict | None = None
        resource_angle: str = "What I found interesting / surprising"

        if source_mode == "Resource from feed":
            # Collect items from trusted feed + saved resources
            feed_items = edu_storage.get_feed_items(min_quality=0.0, status=None, limit=100)
            saved_res  = edu_storage.get_resources(limit=100)

            # Normalise to a common shape
            all_resources: list[dict] = []
            for fi in feed_items:
                all_resources.append({
                    "_type": "feed",
                    "_id": fi["id"],
                    "title": fi.get("title", ""),
                    "source_platform": fi.get("source_platform", ""),
                    "educational_category": fi.get("educational_category", ""),
                    "difficulty_level": fi.get("difficulty_level", "Intermediate"),
                    "summary": fi.get("summary", ""),
                    "educational_quality_score": fi.get("educational_quality_score", 0),
                })
            for sr in saved_res:
                all_resources.append({
                    "_type": "saved",
                    "_id": sr["id"],
                    "title": sr.get("title", ""),
                    "source_platform": sr.get("category", ""),
                    "educational_category": sr.get("category", ""),
                    "difficulty_level": sr.get("difficulty", "Intermediate"),
                    "summary": sr.get("summary", ""),
                    "educational_quality_score": sr.get("usefulness_score", 0),
                })

            # Sort by quality
            all_resources.sort(key=lambda r: r["educational_quality_score"], reverse=True)

            if not all_resources:
                st.info(
                    "No resources in the feed yet. "
                    "Use the **Trusted Source Browser** below to fetch content, "
                    "or add URLs in **Resource Curator**."
                )
                topic = ""
                resource_angle = "What I found interesting / surprising"
            else:
                res_labels = [
                    f"[{r['source_platform'] or r['educational_category']}]  "
                    f"{r['title'][:65]}{'…' if len(r['title']) > 65 else ''}  "
                    f"({r['difficulty_level']} · {r['educational_quality_score']:.1f})"
                    for r in all_resources
                ]
                sel_label = st.selectbox(
                    "Select resource",
                    res_labels,
                    key="edu_res_picker",
                )
                sel_resource = all_resources[res_labels.index(sel_label)]
                topic = sel_resource["title"]

                st.caption(
                    f"**Platform:** {sel_resource['source_platform']}  ·  "
                    f"**Category:** {sel_resource['educational_category']}  ·  "
                    f"**Difficulty:** {sel_resource['difficulty_level']}"
                )
                if sel_resource.get("summary"):
                    with st.expander("Resource summary", expanded=False):
                        st.caption(sel_resource["summary"][:300])

                resource_angle = st.selectbox(
                    "Post angle",
                    [
                        "What I found interesting / surprising",
                        "Practical takeaway for working devs",
                        "Beginner-friendly explanation of the core concept",
                        "Why this resource stands out from others on this topic",
                        "How this changes how I think about the problem",
                    ],
                    key="edu_res_angle",
                )
        else:
            topic_preset = st.selectbox("Topic", TOPIC_PRESETS, key="edu_topic_preset")
            if topic_preset == "Custom…":
                topic = st.text_input(
                    "Describe the topic",
                    placeholder="e.g. what attention in transformers actually does",
                    key="edu_custom_topic",
                )
            else:
                topic = topic_preset

        content_type_val = st.selectbox("Content Type", CONTENT_TYPES, key="edu_content_type")
        difficulty_val = st.selectbox("Difficulty", DIFFICULTIES, key="edu_difficulty")
        language = st.radio("Language", LANGUAGES, horizontal=True, key="edu_language")
        audience = st.selectbox("Audience", AUDIENCES, key="edu_audience")

        st.divider()
        st.markdown("**Thread settings** *(only for thread types)*")
        thread_type_label = st.selectbox("Thread structure", THREAD_TYPES, key="edu_thread_type")
        n_tweets = st.slider("Thread length", min_value=4, max_value=8, value=6, key="edu_n_tweets")

        # Series mode toggle (only available in topic mode)
        st.divider()
        series_mode = st.toggle(
            "Series mode",
            key="edu_series_mode",
            disabled=(source_mode == "Resource from feed"),
        )
        if series_mode and source_mode == "Topic":
            series_list = edu_storage.get_series()
            if series_list:
                series_labels = [f"#{s['id']} — {s['name']} ({s['post_count']} posts)" for s in series_list]
                sel_series_label = st.selectbox("Select series", series_labels, key="edu_sel_series")
                sel_series = series_list[series_labels.index(sel_series_label)]
                next_subtopic = st.text_input(
                    "Next subtopic for this series",
                    placeholder="e.g. Attention heads explained",
                    key="edu_next_subtopic",
                )
            else:
                st.info("No series yet — create one in the Series panel below.")
                sel_series = None
                next_subtopic = ""
        else:
            sel_series = None
            next_subtopic = ""

        st.divider()

        generate_btn = st.button(
            "⚡ Generate",
            type="primary",
            use_container_width=True,
            disabled=not (topic or "").strip(),
            key="edu_generate_btn",
        )

    # ════════════════════════════════════════════════════════════════
    # RIGHT PANEL — generation + preview
    # ════════════════════════════════════════════════════════════════
    with right:

        if generate_btn and (topic or "").strip():
            content_type_enum = EduContentType(content_type_val)
            difficulty_enum = Difficulty(difficulty_val)
            thread_type_enum = THREAD_TYPE_MAP.get(thread_type_label, ThreadType.CONCEPT)
            is_thread_gen = content_type_enum == EduContentType.LEARNING_THREAD

            with st.spinner("Generating educational content…"):
                try:
                    engine = ServiceFactory.educational_engine()

                    if source_mode == "Resource from feed" and sel_resource:
                        # ── Resource-based generation ─────────────────────────
                        if is_thread_gen:
                            post = engine.generate_thread_from_resource(
                                resource=sel_resource,
                                thread_type=thread_type_enum,
                                difficulty=difficulty_enum,
                                language=language,
                                audience=audience,
                                n_tweets=n_tweets,
                                angle=resource_angle,
                            )
                        else:
                            post = engine.generate_from_resource(
                                resource=sel_resource,
                                content_type=content_type_enum,
                                difficulty=difficulty_enum,
                                language=language,
                                audience=audience,
                                angle=resource_angle,
                            )
                        # Mark feed item as used so it moves out of "new"
                        if sel_resource.get("_type") == "feed":
                            edu_storage.mark_feed_item_used(sel_resource["_id"])

                    elif series_mode and sel_series and next_subtopic.strip():
                        # ── Series continuation ───────────────────────────────
                        summaries = edu_storage.get_series_summaries(sel_series["id"])
                        post = engine.generate_series_post(
                            series_name=sel_series["name"],
                            series_topic=sel_series["topic"],
                            next_subtopic=next_subtopic.strip(),
                            previous_summaries=summaries,
                            content_type=content_type_enum,
                            difficulty=difficulty_enum,
                            language=language,
                        )
                    elif is_thread_gen:
                        # ── Topic-based thread ────────────────────────────────
                        continuity = _get_continuity(edu_storage)
                        post = engine.generate_thread(
                            topic=topic,
                            thread_type=thread_type_enum,
                            difficulty=difficulty_enum,
                            language=language,
                            audience=audience,
                            n_tweets=n_tweets,
                            continuity_context=continuity,
                        )
                    else:
                        # ── Topic-based single post ───────────────────────────
                        continuity = _get_continuity(edu_storage)
                        post = engine.generate_post(
                            topic=topic,
                            content_type=content_type_enum,
                            difficulty=difficulty_enum,
                            language=language,
                            audience=audience,
                            continuity_context=continuity,
                            series_context=(
                                f"Part of series: {sel_series['name']}" if sel_series else ""
                            ),
                        )

                    st.session_state.edu_post = post
                    st.session_state.edu_meta_topic = topic
                    st.session_state.edu_meta_content_type = content_type_val
                    st.session_state.edu_meta_difficulty = difficulty_val
                    st.session_state.edu_meta_language = language
                    st.session_state.edu_meta_series_id = sel_series["id"] if sel_series else None

                except Exception as e:
                    st.error(f"Generation failed: {e}")

        post = st.session_state.get("edu_post")

        if post:
            # Guard notices
            if post.notices:
                for notice in post.notices:
                    if "Voice guard" in notice:
                        st.info(f"🎭 {notice}")
                    elif "Claim guard" in notice:
                        st.warning(f"⚠️ {notice}")
                    else:
                        st.caption(f"ℹ️ {notice}")

            if post.is_thread and post.thread_tweets:
                _render_thread_result(post, edu_storage)
            else:
                _render_single_result(post, edu_storage)

        else:
            st.info("Configure options on the left and click **Generate** to create educational content.")

    # ════════════════════════════════════════════════════════════════
    # CONCEPT SIMPLIFIER
    # ════════════════════════════════════════════════════════════════
    st.divider()
    with st.expander("🔍 Concept Simplifier", expanded=False):
        st.caption("Paste any complex concept — get a clear, jargon-free explanation in plain language.")
        simp_col1, simp_col2 = st.columns([3, 1])
        with simp_col1:
            simp_concept = st.text_area(
                "Concept to simplify",
                height=90,
                placeholder="e.g. backpropagation in neural networks",
                key="edu_simp_concept",
            )
        with simp_col2:
            simp_diff = st.selectbox("Target level", DIFFICULTIES, key="edu_simp_diff")
            simp_lang = st.radio("Language", LANGUAGES, horizontal=False, key="edu_simp_lang")
        if st.button("Simplify", key="edu_simp_btn", disabled=not (simp_concept or "").strip()):
            with st.spinner("Simplifying…"):
                try:
                    engine = ServiceFactory.educational_engine()
                    result = engine.simplify_concept(
                        concept=simp_concept.strip(),
                        difficulty=Difficulty(simp_diff),
                        language=simp_lang,
                    )
                    st.session_state.edu_simp_result = result
                except Exception as e:
                    st.error(f"Simplification failed: {e}")

        if st.session_state.get("edu_simp_result"):
            edited_simp = st.text_area(
                "Simplified explanation — edit before posting",
                value=st.session_state.edu_simp_result,
                key="edu_simp_edit",
                height=160,
            )
            sc = len(edited_simp)
            ss1, ss2, ss3 = st.columns([1, 1, 4])
            with ss1:
                st.metric("chars", sc)
                st.caption("🔴" if sc > 280 else "🟢")
            with ss2:
                if st.button("🚀 Post", key="edu_simp_post", type="primary", disabled=sc > 280):
                    _post_single(edited_simp)
            with ss3:
                if st.button("🔄 Regenerate", key="edu_simp_regen"):
                    st.session_state.pop("edu_simp_result", None)
                    st.rerun()

    # ════════════════════════════════════════════════════════════════
    # TRUSTED SOURCE BROWSER
    # ════════════════════════════════════════════════════════════════
    st.divider()
    with st.expander("📡 Trusted Source Browser", expanded=False):
        _render_trusted_source_browser(edu_storage)

    # ════════════════════════════════════════════════════════════════
    # RESOURCE CURATOR
    # ════════════════════════════════════════════════════════════════
    st.divider()
    with st.expander("📚 Resource Curator", expanded=False):
        st.caption(
            "Paste a URL — the engine fetches the page, evaluates usefulness, "
            "and generates original developer commentary you can post."
        )
        rc_col1, rc_col2 = st.columns([4, 1])
        with rc_col1:
            rc_url = st.text_input("Resource URL", placeholder="https://…", key="edu_rc_url")
        with rc_col2:
            rc_lang = st.radio("Language", LANGUAGES, horizontal=False, key="edu_rc_lang")

        if st.button("🔍 Curate Resource", key="edu_rc_btn", disabled=not (rc_url or "").strip()):
            with st.spinner("Fetching page and evaluating…"):
                try:
                    curator = ServiceFactory.resource_curator()
                    resource = curator.curate(url=rc_url.strip(), language=rc_lang)
                    st.session_state.edu_curated = resource
                except Exception as e:
                    st.error(f"Resource curation failed: {e}")

        curated = st.session_state.get("edu_curated")
        if curated:
            st.markdown("---")
            rm1, rm2, rm3 = st.columns(3)
            rm1.metric("Usefulness score", f"{curated.usefulness_score:.1f}/10")
            rm2.caption(f"**Category:** {curated.category.value if hasattr(curated.category, 'value') else curated.category}")
            rm3.caption(f"**Difficulty:** {curated.difficulty.value if hasattr(curated.difficulty, 'value') else curated.difficulty}")

            st.caption(f"**Topic:** {curated.topic}")
            if curated.key_strength:
                st.caption(f"**Key strength:** {curated.key_strength}")
            if curated.audience:
                st.caption(f"**Audience:** {curated.audience}")
            st.caption(f"**Summary:** {curated.summary[:300]}")

            st.markdown("**Original commentary** (edit before posting):")
            edited_commentary = st.text_area(
                "Commentary",
                value=curated.original_commentary,
                key="edu_rc_commentary",
                height=140,
            )
            rc_c = len(edited_commentary)
            rca1, rca2, rca3 = st.columns([1, 1, 1])
            with rca1:
                st.metric("chars", rc_c)
                st.caption("🔴" if rc_c > 280 else "🟢")
            with rca2:
                if st.button("💾 Save Resource", key="edu_rc_save"):
                    rid = edu_storage.save_resource(curated)
                    if rid:
                        st.success(f"Resource saved (#{rid})")
                    else:
                        st.info("Resource already in library.")
            with rca3:
                if st.button("🚀 Post Commentary", key="edu_rc_post", type="primary", disabled=rc_c > 280):
                    _post_single(edited_commentary)

        # Saved resources panel
        st.markdown("---")
        st.markdown("**Saved resources library**")
        rc_filter_col1, rc_filter_col2 = st.columns(2)
        with rc_filter_col1:
            rc_cat_filter = st.selectbox(
                "Filter by category",
                ["All"] + [e.value for e in ResourceCategory],
                key="edu_rc_cat_filter",
            )
        with rc_filter_col2:
            rc_diff_filter = st.selectbox(
                "Filter by difficulty",
                ["All"] + DIFFICULTIES,
                key="edu_rc_diff_filter",
            )

        saved_resources = edu_storage.get_resources(
            category=rc_cat_filter if rc_cat_filter != "All" else None,
            difficulty=rc_diff_filter if rc_diff_filter != "All" else None,
            min_score=0.0,
            limit=30,
        )

        rc_count = edu_storage.resource_count()
        st.caption(f"{rc_count} total resources saved.")

        for res in saved_resources:
            with st.container(border=True):
                sr1, sr2, sr3 = st.columns([4, 2, 1])
                with sr1:
                    st.markdown(f"**{res.get('title', 'Untitled')}**")
                    st.caption(f"{res.get('topic', '')} · {res.get('category', '')} · {res.get('difficulty', '')}")
                with sr2:
                    st.caption(f"Score: **{res.get('usefulness_score', 0):.1f}/10**")
                    st.caption(f"Added: {(res.get('added_at') or '')[:10]}")
                with sr3:
                    if st.button("🗑", key=f"edu_rc_del_{res['id']}", help="Delete"):
                        edu_storage.delete_resource(res["id"])
                        st.rerun()

                if res.get("original_commentary"):
                    with st.expander("Commentary", expanded=False):
                        st.caption(res["original_commentary"])
                        if st.button("🚀 Post", key=f"edu_rc_post_saved_{res['id']}", type="primary"):
                            _post_single(res["original_commentary"])

    # ════════════════════════════════════════════════════════════════
    # LEARNING SERIES
    # ════════════════════════════════════════════════════════════════
    st.divider()
    with st.expander("📖 Learning Series", expanded=False):
        st.caption(
            "Group related posts into a named series for continuity. "
            "The engine uses previous posts in the series to avoid repetition."
        )

        # Create new series
        with st.form("edu_create_series_form", clear_on_submit=True):
            ls_col1, ls_col2 = st.columns(2)
            with ls_col1:
                ls_name = st.text_input("Series name", placeholder="e.g. LLMs from scratch")
                ls_topic = st.text_input("Main topic", placeholder="e.g. Large Language Models")
            with ls_col2:
                ls_desc = st.text_area("Description (optional)", height=80, key="edu_ls_desc")
            if st.form_submit_button("Create Series", use_container_width=True):
                if ls_name.strip() and ls_topic.strip():
                    sid = edu_storage.create_series(
                        name=ls_name.strip(),
                        topic=ls_topic.strip(),
                        description=ls_desc.strip(),
                    )
                    st.success(f"Series created (#{sid})")
                    st.rerun()
                else:
                    st.warning("Name and topic are required.")

        # List series
        series_list = edu_storage.get_series()
        if not series_list:
            st.caption("No learning series yet — create one above.")
        else:
            st.markdown("---")
            st.markdown("**Your series:**")
            for series in series_list:
                with st.container(border=True):
                    lsc1, lsc2, lsc3 = st.columns([4, 2, 1])
                    with lsc1:
                        st.markdown(f"**#{series['id']} — {series['name']}**")
                        st.caption(f"Topic: {series['topic']}  |  {series['post_count']} posts")
                        if series.get("description"):
                            st.caption(series["description"])
                    with lsc2:
                        created = (series.get("created_at") or "")[:10]
                        last_post = (series.get("last_post_at") or "—")[:10]
                        st.caption(f"Created: {created}")
                        st.caption(f"Last post: {last_post}")
                    with lsc3:
                        if st.button("🗑", key=f"edu_del_series_{series['id']}", help="Delete series"):
                            edu_storage.delete_series(series["id"])
                            st.rerun()

                    # Recent posts in this series
                    recent_in_series = edu_storage.get_recent_edu_posts(limit=3, series_id=series["id"])
                    if recent_in_series:
                        with st.expander(f"Recent posts ({len(recent_in_series)} shown)", expanded=False):
                            for sp in recent_in_series:
                                preview = (sp.get("content") or "")[:120]
                                st.caption(
                                    f"• [{(sp.get('created_at') or '')[:10]}] {preview}{'…' if len(preview) == 120 else ''}"
                                )

    # ════════════════════════════════════════════════════════════════
    # RECENT EDUCATIONAL POSTS
    # ════════════════════════════════════════════════════════════════
    st.divider()
    with st.expander("🕐 Recent Educational Posts", expanded=False):
        recent_posts = edu_storage.get_recent_edu_posts(limit=20)
        if not recent_posts:
            st.caption("No educational posts generated yet.")
        else:
            for ep in recent_posts:
                posted_icon = "✅" if ep.get("posted") else "📝"
                series_tag = f" · Series #{ep['series_id']}" if ep.get("series_id") else ""
                with st.expander(
                    f"{posted_icon} {ep.get('content_type', '—')} · {ep.get('topic', '—')}"
                    f" · {(ep.get('created_at') or '')[:10]}{series_tag}",
                    expanded=False,
                ):
                    st.caption(
                        f"Difficulty: {ep.get('difficulty', '—')}  |  "
                        f"Language: {ep.get('language', '—')}  |  "
                        f"Thread: {'yes' if ep.get('is_thread') else 'no'}"
                    )
                    if ep.get("tweet_id"):
                        st.markdown(f"[View on X](https://x.com/i/web/status/{ep['tweet_id']})")

                    content_preview = (ep.get("content") or "")[:300]
                    st.text(content_preview + ("…" if len(content_preview) == 300 else ""))

                    if ep.get("is_thread") and ep.get("thread_tweets"):
                        with st.expander("Thread tweets", expanded=False):
                            for ti, tw in enumerate(ep["thread_tweets"]):
                                st.caption(f"**{ti+1}.** {tw}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_continuity(edu_storage) -> str:
    posts = edu_storage.get_recent_edu_posts(limit=5)
    if not posts:
        return ""
    snippets = [(p.get("content") or "")[:150] for p in posts if p.get("content")]
    return "\n".join(f"- {s}" for s in snippets[:3])


def _post_single(text: str):
    with st.spinner("Posting…"):
        try:
            from x_arabic_poster import BrowserTweetPoster
            tid = BrowserTweetPoster().post(text)
            st.success(f"✅ Posted! [View](https://x.com/i/web/status/{tid})")
        except Exception as e:
            st.error(f"Post failed: {e}")


def _render_single_result(post, edu_storage):
    edited = st.text_area(
        "Generated post — edit before publishing",
        value=post.content,
        key="edu_single_edit",
        height=200,
    )
    char_count = len(edited)
    c1, c2 = st.columns([1, 5])
    with c1:
        st.metric("chars", char_count)
        st.caption("🔴" if char_count > 280 else "🟢")

    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("💾 Save", key="edu_single_save", use_container_width=True):
            did = edu_storage.save_edu_post({
                "content_type": st.session_state.get("edu_meta_content_type", ""),
                "topic": st.session_state.get("edu_meta_topic", ""),
                "difficulty": st.session_state.get("edu_meta_difficulty", ""),
                "language": st.session_state.get("edu_meta_language", ""),
                "content": edited,
                "is_thread": False,
                "series_id": st.session_state.get("edu_meta_series_id"),
            })
            if st.session_state.get("edu_meta_series_id"):
                edu_storage.increment_series(st.session_state["edu_meta_series_id"])
            st.success(f"Saved (#{did})")
    with a2:
        if st.button("🔄 Regenerate", key="edu_single_regen", use_container_width=True):
            st.session_state.pop("edu_post", None)
            st.rerun()
    with a3:
        if st.button("🚀 Post to X", key="edu_single_post", type="primary",
                     use_container_width=True, disabled=char_count > 280):
            edu_storage.save_edu_post({
                "content_type": st.session_state.get("edu_meta_content_type", ""),
                "topic": st.session_state.get("edu_meta_topic", ""),
                "difficulty": st.session_state.get("edu_meta_difficulty", ""),
                "language": st.session_state.get("edu_meta_language", ""),
                "content": edited,
                "is_thread": False,
                "series_id": st.session_state.get("edu_meta_series_id"),
            })
            if st.session_state.get("edu_meta_series_id"):
                edu_storage.increment_series(st.session_state["edu_meta_series_id"])
            _post_single(edited)


def _render_thread_result(post, edu_storage):
    from x_arabic_poster import post_thread as _post_thread_fn

    tweets = post.thread_tweets
    st.markdown("**Educational thread — edit each tweet:**")

    edited_tweets: list[str] = []
    for i, tw in enumerate(tweets):
        tc, tcount = st.columns([6, 1])
        with tc:
            val = st.text_area(
                f"Tweet {i+1}/{len(tweets)}",
                value=tw,
                key=f"edu_tw_{i}",
                height=110,
            )
            edited_tweets.append(val)
        with tcount:
            c = len(val)
            st.metric("chars", c)
            st.caption("🔴" if c > 280 else "🟢")

    over = [i + 1 for i, t in enumerate(edited_tweets) if len(t) > 280]
    if over:
        st.warning(f"Tweet(s) {over} exceed 280 chars.")

    ta1, ta2, ta3 = st.columns(3)
    with ta1:
        if st.button("💾 Save Thread", key="edu_thread_save", use_container_width=True):
            did = edu_storage.save_edu_post({
                "content_type": EduContentType.LEARNING_THREAD.value,
                "topic": st.session_state.get("edu_meta_topic", ""),
                "difficulty": st.session_state.get("edu_meta_difficulty", ""),
                "language": st.session_state.get("edu_meta_language", ""),
                "content": "\n\n".join(edited_tweets),
                "is_thread": True,
                "thread_tweets": edited_tweets,
                "series_id": st.session_state.get("edu_meta_series_id"),
            })
            if st.session_state.get("edu_meta_series_id"):
                edu_storage.increment_series(st.session_state["edu_meta_series_id"])
            st.success(f"Thread saved (#{did})")
    with ta2:
        if st.button("🔄 Regenerate", key="edu_thread_regen", use_container_width=True):
            st.session_state.pop("edu_post", None)
            st.rerun()
    with ta3:
        if st.button("🚀 Post Thread", key="edu_thread_post", type="primary",
                     use_container_width=True, disabled=bool(over)):
            with st.spinner("Posting thread…"):
                try:
                    ids = _post_thread_fn(edited_tweets)
                    did = edu_storage.save_edu_post({
                        "content_type": EduContentType.LEARNING_THREAD.value,
                        "topic": st.session_state.get("edu_meta_topic", ""),
                        "difficulty": st.session_state.get("edu_meta_difficulty", ""),
                        "language": st.session_state.get("edu_meta_language", ""),
                        "content": "\n\n".join(edited_tweets),
                        "is_thread": True,
                        "thread_tweets": edited_tweets,
                        "series_id": st.session_state.get("edu_meta_series_id"),
                    })
                    edu_storage.mark_posted(did, ids[0])
                    if st.session_state.get("edu_meta_series_id"):
                        edu_storage.increment_series(st.session_state["edu_meta_series_id"])
                    st.success(
                        f"✅ Thread of {len(ids)} tweets posted! "
                        f"[View](https://x.com/i/web/status/{ids[0]})"
                    )
                    st.session_state.pop("edu_post", None)
                except Exception as e:
                    st.error(f"Post failed: {e}")


# ── Trusted Source Browser ────────────────────────────────────────────────────

_POST_ANGLES = [
    "What I found interesting / surprising",
    "Practical takeaway for working devs",
    "Beginner-friendly explanation of the core concept",
    "Why this resource stands out from others on this topic",
    "How this changes how I think about the problem",
]

_THREAD_ANGLES = [
    "Key concepts broken down step-by-step",
    "What the resource teaches + why it matters",
    "Common misconceptions this resource corrects",
    "Practical implications for day-to-day dev work",
]


def _render_trusted_source_browser(edu_storage):
    from arabic_x_poster.educational.prompts import (
        EDU_TRUSTED_SOURCE_POST_PROMPT,
        EDU_TRUSTED_SOURCE_THREAD_PROMPT,
    )

    st.caption(
        "Automatically fetch and filter educational content from trusted universities, "
        "platforms, and AI research labs. Generate original developer posts from what you find."
    )

    # ── Source selector ───────────────────────────────────────────────────────
    st.markdown("**Select sources to fetch from:**")
    selected_source_ids: list[str] = []
    for cat, sources in SOURCES_BY_CATEGORY.items():
        st.caption(f"**{cat}**")
        cols = st.columns(min(len(sources), 3))
        for i, src in enumerate(sources):
            with cols[i % 3]:
                if st.checkbox(src.name, value=False, key=f"tsb_src_{src.source_id}"):
                    selected_source_ids.append(src.source_id)

    tsb_col1, tsb_col2, tsb_col3 = st.columns([1, 1, 2])
    with tsb_col1:
        max_per_source = st.number_input(
            "Items per source", min_value=2, max_value=15, value=6, key="tsb_max_per"
        )
    with tsb_col2:
        min_quality = st.slider(
            "Min quality score", 0.0, 10.0, 4.0, 0.5, key="tsb_min_quality"
        )

    fetch_btn = st.button(
        "🔄 Fetch & Score",
        type="primary",
        use_container_width=False,
        key="tsb_fetch_btn",
        disabled=not selected_source_ids,
    )

    if fetch_btn and selected_source_ids:
        with st.spinner(f"Fetching from {len(selected_source_ids)} source(s)…"):
            fetcher = ServiceFactory.trusted_source_fetcher()
            raw_items = fetcher.fetch_all(
                source_ids=selected_source_ids,
                max_per_source=int(max_per_source),
            )

        if not raw_items:
            st.warning("No items retrieved — the selected feeds may be temporarily unavailable.")
        else:
            with st.spinner(f"Scoring {len(raw_items)} items for quality…"):
                pipeline = ServiceFactory.source_quality_pipeline()
                scored = pipeline.score_batch(raw_items, min_quality=min_quality)

            passed = [s for s in scored if s.passes_filter]
            rejected = len(scored) - len(passed)

            saved = 0
            for s in passed:
                rid = edu_storage.save_feed_item(s.as_storage_dict())
                if rid:
                    saved += 1

            st.success(
                f"Fetched {len(raw_items)} → {len(passed)} passed quality filter "
                f"({rejected} rejected) → {saved} new items saved."
            )
            st.rerun()

    # ── Feed display ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Feed filters:**")
    fb_col1, fb_col2, fb_col3, fb_col4 = st.columns(4)
    with fb_col1:
        fb_cat = st.selectbox("Category", ["All"] + EDU_TOPICS, key="tsb_cat_filter")
    with fb_col2:
        fb_diff = st.selectbox("Difficulty", ["All"] + DIFFICULTIES, key="tsb_diff_filter")
    with fb_col3:
        fb_status = st.radio("Show", ["New", "All"], horizontal=True, key="tsb_status_filter")
    with fb_col4:
        fb_min_q = st.slider("Min score", 0.0, 10.0, 0.0, 0.5, key="tsb_feed_min_q")

    feed_items = edu_storage.get_feed_items(
        category=fb_cat if fb_cat != "All" else None,
        difficulty=fb_diff if fb_diff != "All" else None,
        min_quality=fb_min_q,
        status="new" if fb_status == "New" else None,
        limit=40,
    )

    new_count = edu_storage.feed_item_count(status="new")
    total_count = edu_storage.feed_item_count()
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("New items", new_count)
    mc2.metric("Total in feed", total_count)
    mc3.metric("Showing", len(feed_items))

    if total_count > 0:
        if st.button("🗑 Clear old feed items (keep 14 days)", key="tsb_clear_old"):
            deleted = edu_storage.clear_old_feed_items(keep_days=14)
            st.success(f"Cleared {deleted} old item(s).")
            st.rerun()

    if not feed_items:
        st.info("No feed items yet — select sources above and click **Fetch & Score**.")
    else:
        st.markdown(f"**{len(feed_items)} item(s)**")
        for item in feed_items:
            _render_feed_card(item, edu_storage)


def _render_feed_card(item: dict, edu_storage):
    from arabic_x_poster.educational.prompts import (
        EDU_TRUSTED_SOURCE_POST_PROMPT,
        EDU_TRUSTED_SOURCE_THREAD_PROMPT,
    )
    import re as _re

    item_id = item["id"]
    quality = item.get("educational_quality_score", 0)
    relevance = item.get("developer_relevance_score", 0)
    category = item.get("educational_category", "—")
    difficulty = item.get("difficulty_level", "—")
    platform = item.get("source_platform", "—")
    status = item.get("status", "new")
    status_icon = "✅" if status == "used" else "🆕"
    q_bar = "█" * min(10, int(quality))

    with st.container(border=True):
        hd1, hd2, hd3 = st.columns([5, 3, 1])
        with hd1:
            st.markdown(f"**{item.get('title', 'Untitled')}** {status_icon}")
            st.caption(f"{platform}  ·  {category}  ·  {difficulty}")
        with hd2:
            st.caption(
                f"Quality: **{quality:.1f}** {q_bar}\n"
                f"Relevance: **{relevance:.1f}**"
            )
        with hd3:
            if st.button("🚫", key=f"tsb_dismiss_{item_id}", help="Remove"):
                edu_storage.delete_feed_item(item_id)
                st.rerun()

        if item.get("summary"):
            with st.expander("Summary", expanded=False):
                st.caption(item["summary"][:400])
                st.markdown(f"[🔗 Source]({item.get('url', '')})")

        # ── Generate post from this item ──────────────────────────────────
        with st.expander("✨ Generate post from this resource", expanded=False):
            gf_key = f"tsb_gf_{item_id}"
            gf_lang = st.radio("Language", LANGUAGES, horizontal=True, key=f"{gf_key}_lang")
            gf_audience = st.selectbox("Audience", AUDIENCES, key=f"{gf_key}_audience")
            gf_angle = st.selectbox("Post angle", _POST_ANGLES, key=f"{gf_key}_angle")
            gf_mode = st.radio(
                "Generate", ["Single post", "Thread"],
                horizontal=True, key=f"{gf_key}_mode",
            )

            if gf_mode == "Thread":
                gf_n = st.slider("Tweets", 4, 8, 6, key=f"{gf_key}_n")
            else:
                gf_n = 0

            gen_key = f"{gf_key}_result"

            if st.button("⚡ Generate", type="primary", key=f"{gf_key}_btn", use_container_width=True):
                with st.spinner("Generating…"):
                    try:
                        t = ServiceFactory.translator()
                        if gf_mode == "Thread":
                            prompt = EDU_TRUSTED_SOURCE_THREAD_PROMPT.format(
                                title=item.get("title", ""),
                                source_platform=platform,
                                category=category,
                                difficulty=difficulty,
                                summary=(item.get("summary") or "")[:400],
                                n_tweets=gf_n,
                                language=gf_lang,
                                audience=gf_audience,
                                angle=gf_angle,
                            )
                            raw = t.complete(prompt, max_tokens=1200).strip()
                            tweets: list[str] = []
                            for line in raw.splitlines():
                                m = _re.match(r"^\s*\d+[.)]\s*(.+)", line.strip())
                                if m and m.group(1).strip():
                                    tweets.append(m.group(1).strip())
                            if len(tweets) < 2:
                                tweets = [l.strip() for l in raw.splitlines() if l.strip()]
                            st.session_state[gen_key] = {"mode": "thread", "tweets": tweets[:gf_n]}
                        else:
                            prompt = EDU_TRUSTED_SOURCE_POST_PROMPT.format(
                                title=item.get("title", ""),
                                source_platform=platform,
                                category=category,
                                difficulty=difficulty,
                                summary=(item.get("summary") or "")[:400],
                                language=gf_lang,
                                audience=gf_audience,
                                angle=gf_angle,
                            )
                            raw = t.complete(prompt, max_tokens=600).strip()
                            st.session_state[gen_key] = {"mode": "single", "text": raw}
                    except Exception as e:
                        st.error(f"Generation failed: {e}")

            result = st.session_state.get(gen_key)
            if result:
                if result["mode"] == "single":
                    edited = st.text_area(
                        "Post — edit before publishing",
                        value=result["text"],
                        key=f"{gf_key}_edit",
                        height=180,
                    )
                    cc = len(edited)
                    ca1, ca2, ca3 = st.columns([1, 1, 4])
                    with ca1:
                        st.metric("chars", cc)
                        st.caption("🔴" if cc > 280 else "🟢")
                    with ca2:
                        if st.button("🚀 Post", key=f"{gf_key}_post", type="primary", disabled=cc > 280):
                            _post_single(edited)
                            edu_storage.mark_feed_item_used(item_id)
                            st.session_state.pop(gen_key, None)
                            st.rerun()
                    with ca3:
                        if st.button("🔄 Regenerate", key=f"{gf_key}_regen"):
                            st.session_state.pop(gen_key, None)
                            st.rerun()

                else:  # thread
                    tweets = result["tweets"]
                    st.markdown("**Thread — edit before posting:**")
                    edited_tweets: list[str] = []
                    for ti, tw in enumerate(tweets):
                        tc, tcount = st.columns([6, 1])
                        with tc:
                            val = st.text_area(
                                f"Tweet {ti+1}", value=tw,
                                key=f"{gf_key}_tw_{ti}", height=90,
                            )
                            edited_tweets.append(val)
                        with tcount:
                            c = len(val)
                            st.metric("chars", c)
                            st.caption("🔴" if c > 280 else "🟢")

                    over = [i + 1 for i, t in enumerate(edited_tweets) if len(t) > 280]
                    if over:
                        st.warning(f"Tweet(s) {over} exceed 280 chars.")

                    ta1, ta2 = st.columns(2)
                    with ta1:
                        if st.button("🔄 Regenerate", key=f"{gf_key}_thread_regen"):
                            st.session_state.pop(gen_key, None)
                            st.rerun()
                    with ta2:
                        if st.button(
                            "🚀 Post Thread", key=f"{gf_key}_thread_post",
                            type="primary", use_container_width=True, disabled=bool(over),
                        ):
                            from x_arabic_poster import post_thread as _pt
                            with st.spinner("Posting…"):
                                try:
                                    ids = _pt(edited_tweets)
                                    edu_storage.mark_feed_item_used(item_id)
                                    st.session_state.pop(gen_key, None)
                                    st.success(
                                        f"✅ Thread posted! "
                                        f"[View](https://x.com/i/web/status/{ids[0]})"
                                    )
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Post failed: {e}")
