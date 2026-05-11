"""Trend Intelligence UI tab — rendered by app.py via render_tab()."""

from __future__ import annotations

import streamlit as st

from arabic_x_poster.factory import ServiceFactory
from arabic_x_poster.config import SESSION_FILE


# ── Source labels ─────────────────────────────────────────────────────────────

SOURCE_LABELS = {
    "hn": "Hacker News",
    "reddit": "Reddit",
    "github": "GitHub Trending",
    "product_hunt": "Product Hunt",
}

TONE_OPTIONS = ["Reflective", "Curious", "Analytical", "Frustrated (relatable)", "Casual", "Confident"]
AUDIENCE_OPTIONS = ["Beginner devs", "Intermediate devs", "Advanced / senior devs", "General tech followers"]
LANGUAGE_OPTIONS = ["English", "Arabic"]

DEFAULT_REDDIT_SUBS = "programming, webdev, MachineLearning, Python, ExperiencedDevs"


def render_tab():
    st.subheader("📡 Trend Intelligence")
    st.caption(
        "Monitors developer communities, extracts structural patterns, and generates "
        "original perspectives — never copies or paraphrases source content."
    )

    trend_storage = ServiceFactory.trend_storage()
    conn_mgr = ServiceFactory.x_connection()

    # ── Two-column layout ─────────────────────────────────────────────────────
    left, right = st.columns([1, 2], gap="large")

    # ════════════════════════════════════════════════════════════════
    # LEFT PANEL — controls + connection + creators
    # ════════════════════════════════════════════════════════════════
    with left:

        # X Session status
        status_icon = "🟢" if conn_mgr.is_connected else "🔴"
        st.markdown(
            f"**X Session:** {status_icon} {conn_mgr.status_label} "
            f"*(refreshed {conn_mgr.session_age_label()})*"
        )
        if not conn_mgr.is_connected:
            st.warning(
                "Run `C:/Python314/python.exe setup_x_session.py` to connect your X account."
            )

        st.divider()

        # Source selection
        st.markdown("**Trend Sources**")
        selected_sources = []
        for sid, slabel in SOURCE_LABELS.items():
            if st.checkbox(slabel, value=True, key=f"ti_src_{sid}"):
                selected_sources.append(sid)

        if "reddit" in selected_sources:
            reddit_subs_input = st.text_input(
                "Reddit subreddits (comma-separated)",
                value=DEFAULT_REDDIT_SUBS,
                key="ti_reddit_subs",
            )
            reddit_subs = [s.strip() for s in reddit_subs_input.split(",") if s.strip()]
        else:
            reddit_subs = []

        github_lang = st.text_input(
            "GitHub language filter (optional)",
            placeholder="python, javascript, rust…",
            key="ti_github_lang",
        ).strip()

        min_score = st.slider(
            "Minimum relevance score", 0.0, 1.0, 0.25, 0.05, key="ti_min_score"
        )

        fetch_btn = st.button(
            "🔄 Fetch & Analyse Trends",
            type="primary",
            use_container_width=True,
            key="ti_fetch_btn",
            disabled=not selected_sources,
        )

        st.divider()

        # Monitored creators
        st.markdown("**Monitored Creators**")
        st.caption("Handles to watch for post patterns (no text stored).")
        creators = trend_storage.get_creators()
        if creators:
            for c in creators:
                cc1, cc2 = st.columns([3, 1])
                with cc1:
                    platform_icon = "🐦" if c["platform"] == "x" else "🌐"
                    st.caption(f"{platform_icon} @{c['handle']}")
                with cc2:
                    if st.button("✕", key=f"ti_rm_{c['id']}", use_container_width=True):
                        trend_storage.remove_creator(c["handle"], c["platform"])
                        st.rerun()
        else:
            st.caption("No creators monitored yet.")

        with st.form("ti_add_creator_form", clear_on_submit=True):
            new_handle = st.text_input("Add @handle", placeholder="username")
            new_platform = st.selectbox("Platform", ["x", "github", "reddit"], key="ti_new_platform")
            if st.form_submit_button("Add", use_container_width=True):
                if new_handle.strip():
                    added = trend_storage.add_creator(new_handle.strip(), new_platform)
                    if added:
                        st.success(f"Added @{new_handle.strip()}")
                        st.rerun()
                    else:
                        st.info("Already monitored.")

        st.divider()

        # Storage stats
        new_count = trend_storage.trend_count("new")
        used_count = trend_storage.trend_count("used")
        s1, s2 = st.columns(2)
        s1.metric("New trends", new_count)
        s2.metric("Used", used_count)
        if new_count > 0 and st.button("🗑 Clear all trends", key="ti_clear_btn", use_container_width=True):
            trend_storage.clear_old_trends(keep_days=0)
            for k in list(st.session_state.keys()):
                if k.startswith("ti_"):
                    st.session_state.pop(k, None)
            st.rerun()

    # ════════════════════════════════════════════════════════════════
    # RIGHT PANEL — trend feed + perspective generation
    # ════════════════════════════════════════════════════════════════
    with right:

        # Fetch trends
        if fetch_btn and selected_sources:
            with st.spinner("Fetching from selected sources…"):
                fetcher = ServiceFactory.source_fetcher()
                raw_items = fetcher.fetch_all(
                    sources=selected_sources,
                    reddit_subs=reddit_subs or None,
                    github_language=github_lang,
                )

            with st.spinner(f"Scoring {len(raw_items)} items…"):
                scorer = ServiceFactory.trend_scorer()
                scored = scorer.score(raw_items)

            with st.spinner("Extracting patterns (no source text stored)…"):
                extractor = ServiceFactory.trend_extractor()
                extracted = extractor.extract_batch(scored, min_score=min_score)

            # Persist extracted patterns
            saved_count = 0
            st.session_state.ti_raw_texts = {}  # hash → text (session only, not DB)
            for i, (scored_item, ex) in enumerate(
                zip(scored[:len(extracted)], extracted)
            ):
                saved_id = trend_storage.save_trend(ex.as_storage_dict())
                if saved_id:
                    saved_count += 1
                    # Keep raw text in session state for originality checking
                    st.session_state.ti_raw_texts[ex.source_hash] = scored_item.item.combined_text

            st.success(
                f"Fetched {len(raw_items)} items → {len(extracted)} analysed → "
                f"{saved_count} new patterns stored."
            )
            st.rerun()

        # Trend feed
        trends = trend_storage.get_trends(status="new", limit=40, min_score=min_score)
        all_trends = trend_storage.get_trends(status=None, limit=40, min_score=min_score)

        if not all_trends:
            st.info("No trends yet — click **Fetch & Analyse Trends** to start.")
        else:
            view_mode = st.radio(
                "Show", ["New only", "All"], horizontal=True, key="ti_view_mode"
            )
            display_trends = trends if view_mode == "New only" else all_trends

            st.markdown(f"**{len(display_trends)} trend pattern(s)**")

            for trend_row in display_trends:
                _render_trend_card(trend_row, trend_storage)


def _render_trend_card(trend_row: dict, trend_storage):
    """Render a single trend card with pattern info and generation controls."""
    score = trend_row.get("overall_score", 0)
    source = trend_row.get("source", "unknown")
    topic = trend_row.get("topic_context", "unknown topic")
    status = trend_row.get("status", "new")
    tid = trend_row["id"]

    status_icon = {"new": "🆕", "used": "✅", "dismissed": "🚫"}.get(status, "")
    source_icon = {"hn": "🟠", "reddit": "🔵", "github": "⚫", "product_hunt": "🟡"}.get(source, "🌐")
    score_bar = "█" * min(10, int(score * 10))

    with st.container(border=True):
        hd1, hd2, hd3 = st.columns([4, 2, 1])
        with hd1:
            st.markdown(f"**{source_icon} {topic}** {status_icon}")
            st.caption(
                f"Hook: `{trend_row.get('hook_type', '—')}` · "
                f"Tone: `{trend_row.get('emotional_tone', '—')}` · "
                f"Trigger: `{trend_row.get('engagement_trigger', '—')}`"
            )
        with hd2:
            st.caption(
                f"Score: **{score:.2f}** {score_bar}\n"
                f"vel={trend_row.get('velocity_score', 0):.2f} "
                f"fresh={trend_row.get('freshness_score', 0):.2f}"
            )
        with hd3:
            if st.button("🚫", key=f"ti_dismiss_{tid}", help="Dismiss"):
                trend_storage.dismiss_trend(tid)
                st.rerun()

        # Pattern details (collapsed)
        with st.expander("Pattern details", expanded=False):
            st.caption(f"**Format:** {trend_row.get('content_format', '—')}")
            st.caption(f"**Narrative:** {trend_row.get('narrative_structure', '—')}")
            st.caption(f"**Topic angle:** {trend_row.get('topic_angle', '—')}")
            tags = trend_row.get("tags", "[]")
            if isinstance(tags, str):
                import json
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = []
            if tags:
                st.caption(f"**Tags:** {', '.join(tags)}")

        # Generate perspective controls
        with st.expander("✨ Generate perspective", expanded=False):
            _render_perspective_generator(trend_row, trend_storage)


def _render_perspective_generator(trend_row: dict, trend_storage):
    """Controls for generating an original perspective from this trend."""
    from arabic_x_poster.trend_intelligence.extractor import ExtractedTrend
    from arabic_x_poster.content_engine.storage import ContentStorage
    from arabic_x_poster.config import PROJECT_ROOT
    import json

    tid = trend_row["id"]
    key_prefix = f"ti_pg_{tid}"

    # Rebuild ExtractedTrend from stored row
    ex_trend = ExtractedTrend(
        source_hash=trend_row.get("source_hash", ""),
        source=trend_row.get("source", ""),
        topic_context=trend_row.get("topic_context", ""),
        hook_type=trend_row.get("hook_type", "observation"),
        emotional_tone=trend_row.get("emotional_tone", "curiosity"),
        content_format=trend_row.get("content_format", "insight"),
        engagement_trigger=trend_row.get("engagement_trigger", "relatability"),
        narrative_structure=trend_row.get("narrative_structure", "observation → reflection"),
        topic_angle=trend_row.get("topic_angle", "workflow"),
        raw_engagement=float(trend_row.get("raw_engagement", 0)),
        age_hours=float(trend_row.get("age_hours", 0)),
        velocity_score=float(trend_row.get("velocity_score", 0)),
        freshness_score=float(trend_row.get("freshness_score", 0)),
        relevance_score=float(trend_row.get("relevance_score", 0)),
        overall_score=float(trend_row.get("overall_score", 0)),
        tags=json.loads(trend_row.get("tags") or "[]"),
    )

    pg_lang = st.radio("Language", LANGUAGE_OPTIONS, horizontal=True, key=f"{key_prefix}_lang")
    pg_tone = st.selectbox("Tone", TONE_OPTIONS, key=f"{key_prefix}_tone")
    pg_audience = st.selectbox("Audience", AUDIENCE_OPTIONS, key=f"{key_prefix}_audience")

    angles_key = f"{key_prefix}_angles"
    selected_key = f"{key_prefix}_sel"
    result_key = f"{key_prefix}_result"

    # Phase 1: Generate angles
    if st.button("💡 Generate Angles", key=f"{key_prefix}_angles_btn", use_container_width=True):
        with st.spinner("Generating 3 original perspective angles…"):
            gen = ServiceFactory.perspective_generator()
            angles = gen.generate_angles(ex_trend, n=3)
            st.session_state[angles_key] = angles
            st.session_state.pop(result_key, None)

    angles = st.session_state.get(angles_key, [])
    if angles:
        angle_labels = [f"{i+1}. {a.label} ({a.framing})" for i, a in enumerate(angles)]
        chosen_label = st.radio("Choose angle", angle_labels, key=f"{key_prefix}_radio")
        chosen_idx = angle_labels.index(chosen_label)
        chosen_angle = angles[chosen_idx]
        st.caption(f"Hook suggestion: *{chosen_angle.hook_suggestion}*")

        # Phase 2: Generate post
        gen_col, regen_col = st.columns(2)
        with gen_col:
            gen_btn = st.button(
                "✍️ Generate Post",
                type="primary",
                use_container_width=True,
                key=f"{key_prefix}_gen_btn",
            )
        with regen_col:
            if st.button("🔄 Regenerate Angles", key=f"{key_prefix}_regen_angles", use_container_width=True):
                st.session_state.pop(angles_key, None)
                st.session_state.pop(result_key, None)
                st.rerun()

        if gen_btn:
            content_storage = ContentStorage(PROJECT_ROOT / "content_engine.db")
            continuity = content_storage.get_continuity_context(5)
            source_texts = list(st.session_state.get("ti_raw_texts", {}).values())

            with st.spinner("Writing original perspective…"):
                gen = ServiceFactory.perspective_generator()
                result = gen.generate(
                    trend=ex_trend,
                    angle=chosen_angle,
                    language=pg_lang,
                    tone=pg_tone,
                    audience_level=pg_audience,
                    continuity_context=continuity,
                    source_posts=source_texts or None,
                )
                st.session_state[result_key] = result

    result = st.session_state.get(result_key)
    if result:
        # Guard notices
        if not result.originality_passed:
            st.warning("⚠️ **Originality flag** — review this post carefully before posting.")
        if result.notices:
            for notice in result.notices:
                st.info(f"ℹ️ {notice}")

        edited = st.text_area(
            "Generated perspective — edit before posting",
            value=result.content,
            height=180,
            key=f"{key_prefix}_edit",
        )
        char_count = len(edited)
        cm1, cm2, cm3, cm4 = st.columns(4)
        with cm1:
            st.metric("chars", char_count)
            st.caption("🔴" if char_count > 280 else "🟢")
        with cm2:
            if st.button("💾 Save Draft", key=f"{key_prefix}_save", use_container_width=True):
                from arabic_x_poster.content_engine.storage import ContentStorage
                cs = ContentStorage(PROJECT_ROOT / "content_engine.db")
                did = cs.save_draft({
                    "topic": ex_trend.topic_context,
                    "post_type": "Trend-inspired",
                    "tone": pg_tone,
                    "audience_level": pg_audience,
                    "platform": "Single tweet",
                    "language": pg_lang,
                    "hooks": [],
                    "selected_hook": result.angle.label,
                    "hook_scores": [],
                    "raw_content": result.content,
                    "humanized_content": edited,
                    "intent_profile": {"source": ex_trend.source, "topic_angle": ex_trend.topic_angle},
                })
                trend_storage.save_perspective({
                    "trend_id": trend_row["id"],
                    "angle": result.angle.label,
                    "content": edited,
                    "language": pg_lang,
                    "tone": pg_tone,
                    "originality_passed": result.originality_passed,
                    "voice_corrected": result.voice_corrected,
                    "draft_id": did,
                })
                trend_storage.mark_trend_used(trend_row["id"])
                st.success(f"Saved as draft #{did}")
                st.rerun()
        with cm3:
            if st.button("🔄 Regen Post", key=f"{key_prefix}_regen_post", use_container_width=True):
                st.session_state.pop(result_key, None)
                st.rerun()
        with cm4:
            if st.button(
                "🚀 Post to X",
                type="primary",
                key=f"{key_prefix}_post",
                use_container_width=True,
                disabled=char_count > 280,
            ):
                with st.spinner("Posting…"):
                    try:
                        from x_arabic_poster import BrowserTweetPoster
                        tweet_id = BrowserTweetPoster().post(edited)
                        trend_storage.mark_trend_used(trend_row["id"])
                        trend_storage.save_perspective({
                            "trend_id": trend_row["id"],
                            "angle": result.angle.label,
                            "content": edited,
                            "language": pg_lang,
                            "tone": pg_tone,
                            "originality_passed": result.originality_passed,
                            "voice_corrected": result.voice_corrected,
                        })
                        st.success(f"✅ Posted! [View](https://x.com/i/web/status/{tweet_id})")
                        st.session_state.pop(result_key, None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Post failed: {e}")
