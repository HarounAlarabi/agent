import re
import json
import os
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path

# Load .env locally; on Streamlit Cloud inject st.secrets into os.environ
load_dotenv()
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass

from arabic_x_poster.feeds import FEED_CATALOG
from x_arabic_poster import (
    SESSION_FILE,
    ThreadPostError,
    DEFAULT_RSS_FEEDS,
    download_image,
    fetch_article,
    fetch_user_tweets_browser,
    find_article_courses,
    find_topic_image_url,
    post_thread,
    scan_rss,
    summarize_article_to_arabic_tweets,
    translate_tweet,
)

ACCOUNTS_FILE = Path(__file__).parent / "saved_accounts.json"

def load_accounts() -> list[dict]:
    if ACCOUNTS_FILE.exists():
        return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    return []

def save_accounts(accounts: list[dict]):
    ACCOUNTS_FILE.write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8")

st.set_page_config(page_title="Arabic X Poster", layout="wide", page_icon="🐦")

st.markdown("""
<style>
textarea { direction: rtl; text-align: right; font-size: 15px; }
.stTextArea label { direction: ltr; text-align: left; }
</style>
""", unsafe_allow_html=True)

st.title("🐦 Arabic X Thread Poster")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    n_tweets = st.slider("Tweets per thread", min_value=3, max_value=4, value=3)
    max_articles = st.slider("Articles per feed", min_value=1, max_value=10, value=3)

    st.divider()
    st.subheader("📡 RSS Feeds")

    # Group feeds by category — each group is collapsible
    from itertools import groupby
    feeds: list[str] = []
    _catalog_sorted = sorted(FEED_CATALOG, key=lambda e: e.category)
    for category, entries in groupby(_catalog_sorted, key=lambda e: e.category):
        entries = list(entries)
        with st.expander(f"{category} ({len(entries)})", expanded=False):
            for entry in entries:
                if st.checkbox(entry.name, value=True, key=f"feed_chk_{entry.url}"):
                    feeds.append(entry.url)

    # Custom feed
    with st.expander("Custom", expanded=False):
        custom_url = st.text_input("Add a feed URL", placeholder="https://…", key="feed_custom_url")
        if custom_url.strip():
            feeds.append(custom_url.strip())

    if st.button("Scan Feeds", type="primary", use_container_width=True):
        with st.spinner("Scanning RSS feeds…"):
            articles = []
            for url in feeds:
                try:
                    articles.extend(scan_rss(url, max_articles=max_articles))
                except Exception as e:
                    st.warning(f"Could not fetch {url}: {e}")
            st.session_state.articles = articles
            st.session_state.threads = {}
            st.session_state.thread_images = {}
            st.session_state.thread_courses = {}
        st.success(f"Found {len(articles)} articles.")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_rss, tab_accounts, tab_users, tab_generate, tab_trends, tab_edu = st.tabs([
    "📰 RSS Feeds", "👥 My Accounts", "✍️ Translate & Post",
    "🧠 Generate Content", "📡 Trend Intelligence", "🎓 Educational",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RSS Feeds
# ═══════════════════════════════════════════════════════════════════════════════
with tab_rss:
    if "articles" not in st.session_state:
        st.info("Click **Scan Feeds** in the sidebar to load articles.")
    else:
        articles: list[dict] = st.session_state.articles
        if not articles:
            st.warning("No articles found. Try adjusting the feeds or article limit.")
        else:
            if "threads" not in st.session_state:
                st.session_state.threads = {}
            if "thread_images" not in st.session_state:
                st.session_state.thread_images = {}
            if "thread_courses" not in st.session_state:
                st.session_state.thread_courses = {}

            st.subheader(f"📰 {len(articles)} Articles")

            for i, article in enumerate(articles):
                with st.expander(f"**{article['title']}**  —  {article.get('published', '')}", expanded=False):
                    col_meta, col_btn = st.columns([4, 1])
                    with col_meta:
                        summary = article.get("summary", "")
                        summary_clean = re.sub(r"<[^>]+>", "", summary)[:400]
                        st.caption(summary_clean + ("…" if len(summary_clean) == 400 else ""))
                        st.markdown(f"[🔗 Source]({article['link']})")
                    with col_btn:
                        if st.button("Translate →", key=f"tr_{i}", use_container_width=True):
                            full_text = ""
                            if article.get("link"):
                                with st.spinner("Fetching full article…"):
                                    try:
                                        full_text = fetch_article(article["link"])
                                    except Exception:
                                        pass

                            summary = re.sub(
                                r"<[^>]+>",
                                "",
                                article.get("summary", ""),
                            ).strip()
                            content = full_text if len(full_text) >= 500 else summary

                            if len(content) < 120:
                                st.error(
                                    "Could not extract enough article text or RSS summary. "
                                    "Open the source link and try another article."
                                )
                            else:
                                with st.spinner("Summarizing source article into a short Arabic thread…"):
                                    try:
                                        tweets = summarize_article_to_arabic_tweets(
                                            title=article["title"],
                                            article_text=content,
                                            n_tweets=n_tweets,
                                        )
                                        if not tweets:
                                            st.error(
                                                "The AI returned no Arabic tweets. "
                                                "Check that your API keys are valid and try again."
                                            )
                                        else:
                                            image_url = find_topic_image_url(
                                                article.get("link", ""),
                                                article.get("image_url", ""),
                                            )
                                            courses = find_article_courses(article.get("link", ""))
                                            st.session_state.threads[i] = tweets
                                            st.session_state.thread_images[i] = image_url
                                            st.session_state.thread_courses[i] = courses
                                    except Exception as e:
                                        st.error(f"Translation failed: {e}")

                    if i in st.session_state.get("threads", {}):
                        tweets_list: list[str] = st.session_state.threads[i]
                        st.divider()
                        st.markdown("**Arabic Thread Preview** — edit before posting:")
                        image_url = st.session_state.thread_images.get(i, "")
                        if image_url:
                            st.image(image_url, caption="Image attached to tweet 1", width=420)
                        courses = st.session_state.thread_courses.get(i, [])
                        if courses:
                            preview_courses = courses[:3]
                            inline_courses = " | ".join(
                                f"[{course['name']}]({course['link']})" for course in preview_courses
                            )
                            extra_count = max(0, len(courses) - len(preview_courses))
                            suffix = f"  +{extra_count} more" if extra_count else ""
                            st.caption(f"Courses found in the article: {inline_courses}{suffix}")

                        edited: list[str] = []
                        for j, tweet in enumerate(tweets_list):
                            col_tweet, col_count = st.columns([6, 1])
                            with col_tweet:
                                val = st.text_area(
                                    f"Tweet {j+1}/{len(tweets_list)}",
                                    value=tweet,
                                    key=f"tw_{i}_{j}",
                                    height=160,
                                )
                                edited.append(val)
                            with col_count:
                                count = len(val)
                                st.metric(label="chars", value=count)
                                st.caption("🔴" if count > 280 else "🟢")

                        over_limit = [j+1 for j, t in enumerate(edited) if len(t) > 280]
                        if over_limit:
                            st.warning(f"Tweet(s) {over_limit} exceed 280 characters.")

                        post_col, _ = st.columns([1, 3])
                        with post_col:
                            if st.button("✅ Approve & Post Thread", key=f"post_{i}",
                                         type="primary", use_container_width=True,
                                         disabled=bool(over_limit)):
                                with st.spinner(
                                    f"Posting {len(edited)}-tweet thread to X… "
                                    "A browser window will open and close automatically."
                                ):
                                    try:
                                        first_image_path = ""
                                        image_url = st.session_state.thread_images.get(i, "")
                                        if image_url:
                                            first_image_path = download_image(image_url)
                                            if not first_image_path:
                                                st.warning("Could not download the topic image, posting text only.")
                                        ids = post_thread(
                                            edited,
                                            source_url=article["link"],
                                            first_image_path=first_image_path or None,
                                        )
                                        st.success(
                                            f"✅ Thread of {len(ids)} tweets posted!  "
                                            f"[View on X](https://x.com/i/web/status/{ids[0]})"
                                        )
                                    except ThreadPostError as e:
                                        st.error(f"Posting stopped: {e.cause}")
                                        if e.remaining:
                                            import urllib.parse
                                            st.warning(
                                                f"{len(e.remaining)} tweet(s) could not be posted automatically. "
                                                "Click each button below to open it in X and post manually."
                                            )
                                            for idx2, tw in enumerate(e.remaining):
                                                c1, c2 = st.columns([4, 1])
                                                with c1:
                                                    st.text_area(
                                                        f"Tweet {len(e.posted)+idx2+1}/{len(edited)}",
                                                        value=tw, height=100,
                                                        key=f"manual_{i}_{idx2}"
                                                    )
                                                with c2:
                                                    intent = "https://x.com/intent/tweet?text=" + urllib.parse.quote(tw)
                                                    st.link_button("Open in X", intent)
                                    except Exception as e:
                                        st.error(f"Post failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — My Accounts
# ═══════════════════════════════════════════════════════════════════════════════
with tab_accounts:
    st.subheader("👥 My Accounts")

    # ── Session status ─────────────────────────────────────────────────────────
    session_ready = SESSION_FILE.exists()
    if not session_ready:
        st.warning(
            "**X session not set up yet.**  \n"
            "Run this command once in a terminal to log in and save your session:  \n"
            "```\nC:/Python314/python.exe c:/Users/Dell/Desktop/agent/setup_x_session.py\n```"
        )
    else:
        st.success("✅ X session active — tweets will be fetched automatically when you add an account.")

    if "accounts" not in st.session_state:
        st.session_state.accounts = load_accounts()
    if "account_tweets" not in st.session_state:
        st.session_state.account_tweets = {}
    if "account_translations" not in st.session_state:
        st.session_state.account_translations = {}

    # ── Add account form ───────────────────────────────────────────────────────
    with st.form("add_account_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([2, 3, 1])
        with col1:
            new_username = st.text_input("Username", placeholder="elonmusk")
        with col2:
            new_label = st.text_input("Label (optional)", placeholder="Elon Musk — tech & space")
        with col3:
            st.markdown("<br>", unsafe_allow_html=True)
            add_acc = st.form_submit_button("➕ Add & Fetch", use_container_width=True)

    if add_acc:
        username = new_username.strip().lstrip("@")
        if not username:
            st.warning("Enter a username.")
        elif username.lower() in [a["username"].lower() for a in st.session_state.accounts]:
            st.warning(f"@{username} is already saved.")
        else:
            st.session_state.accounts.append({"username": username, "label": new_label.strip()})
            save_accounts(st.session_state.accounts)
            if session_ready:
                with st.spinner(f"Fetching tweets from @{username}…"):
                    try:
                        tweets = fetch_user_tweets_browser(username, max_tweets=10)
                        st.session_state.account_tweets[username] = tweets
                        st.success(f"Fetched {len(tweets)} tweets from @{username}.")
                    except Exception as e:
                        st.error(f"Could not fetch tweets: {e}")
            st.rerun()

    # ── Account list ───────────────────────────────────────────────────────────
    if not st.session_state.accounts:
        st.info("No accounts saved yet — add one above.")
    else:
        search_acc = st.text_input("🔍 Filter", placeholder="Search by username or label…")
        filtered_acc = [
            a for a in st.session_state.accounts
            if not search_acc
            or search_acc.lower() in a["username"].lower()
            or search_acc.lower() in a.get("label", "").lower()
        ]

        for acc in filtered_acc:
            uname = acc["username"]
            tweets_for_acc = st.session_state.account_tweets.get(uname, [])

            with st.expander(
                f"**@{uname}**{'  — ' + acc['label'] if acc.get('label') else ''}  "
                f"({len(tweets_for_acc)} tweets loaded)",
                expanded=len(tweets_for_acc) > 0,
            ):
                hcol1, hcol2, hcol3 = st.columns([2, 2, 1])
                with hcol1:
                    st.link_button("🐦 Open on X", f"https://x.com/{uname}", use_container_width=True)
                with hcol2:
                    if st.button("🔄 Refresh tweets", key=f"ref_{uname}", use_container_width=True, disabled=not session_ready):
                        with st.spinner(f"Fetching @{uname}…"):
                            try:
                                tweets = fetch_user_tweets_browser(uname, max_tweets=10)
                                st.session_state.account_tweets[uname] = tweets
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                with hcol3:
                    if st.button("🗑 Remove", key=f"del_{uname}", use_container_width=True):
                        st.session_state.accounts = [a for a in st.session_state.accounts if a["username"] != uname]
                        st.session_state.account_tweets.pop(uname, None)
                        save_accounts(st.session_state.accounts)
                        st.rerun()

                if not tweets_for_acc:
                    if session_ready:
                        st.caption("No tweets loaded yet — click Refresh tweets.")
                    else:
                        st.caption("Set up your X session first (see instructions above).")
                else:
                    st.markdown("---")
                    trans_key = f"at_{uname}"
                    if trans_key not in st.session_state.account_translations:
                        st.session_state.account_translations[trans_key] = {}

                    for k, tw in enumerate(tweets_for_acc):
                        tw_key = f"{uname}_{k}"
                        preview = tw["text"][:100] + ("…" if len(tw["text"]) > 100 else "")
                        st.markdown(f"**{k+1}.** {preview}")
                        if tw.get("link"):
                            st.caption(tw["link"])

                        btn_col, _ = st.columns([1, 3])
                        with btn_col:
                            if st.button("Translate →", key=f"tr_acc_{tw_key}", use_container_width=True):
                                with st.spinner("Translating…"):
                                    try:
                                        arabic = translate_tweet(tw["text"], uname)
                                        attribution = f"\n\n(via @{uname})"
                                        st.session_state.account_translations[trans_key][k] = arabic + attribution
                                        st.rerun()
                                    except Exception as e:
                                        st.error(str(e))

                        if k in st.session_state.account_translations[trans_key]:
                            ar_col, cnt_col = st.columns([6, 1])
                            with ar_col:
                                edited = st.text_area(
                                    "Arabic — edit if needed",
                                    value=st.session_state.account_translations[trans_key][k],
                                    key=f"ar_acc_{tw_key}",
                                    height=130,
                                )
                            with cnt_col:
                                c = len(edited)
                                st.metric("chars", c)
                                st.caption("🔴" if c > 280 else "🟢")

                            if c > 280:
                                st.warning("Over 280 chars.")
                            else:
                                post_c, _ = st.columns([1, 3])
                                with post_c:
                                    if st.button("🚀 Post", key=f"post_acc_{tw_key}", type="primary", use_container_width=True):
                                        with st.spinner("Posting…"):
                                            try:
                                                from x_arabic_poster import BrowserTweetPoster
                                                tid = BrowserTweetPoster().post(edited)
                                                st.success(f"✅ [View](https://x.com/i/web/status/{tid})")
                                            except Exception as e:
                                                st.error(str(e))
                        st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Translate & Post
# ═══════════════════════════════════════════════════════════════════════════════
with tab_users:
    st.subheader("👤 User Tweet Translator")

    input_mode = st.radio(
        "How do you want to add tweets?",
        ["📋 Paste tweet text", "🔗 Custom RSS feed URL"],
        horizontal=True,
    )

    if "queue" not in st.session_state:
        st.session_state.queue = []

    # ── Mode 1: paste ──────────────────────────────────────────────────────────
    if input_mode == "📋 Paste tweet text":
        st.caption("Open X in your browser, copy the tweet text, and paste it here.")
        with st.form("paste_form", clear_on_submit=True):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                paste_text = st.text_area("Tweet text", height=100, placeholder="Paste the English tweet here…")
            with col_b:
                paste_author = st.text_input("Author (@username)", placeholder="elonmusk")
                paste_link = st.text_input("Tweet URL (optional)", placeholder="https://x.com/…")
            add_btn = st.form_submit_button("➕ Add to queue", use_container_width=True)

        if add_btn:
            if paste_text.strip() and paste_author.strip():
                st.session_state.queue.append({
                    "text": paste_text.strip(),
                    "author": paste_author.strip().lstrip("@"),
                    "link": paste_link.strip(),
                    "translation": None,
                })
                st.rerun()
            else:
                st.warning("Tweet text and username are required.")

    # ── Mode 2: custom RSS ─────────────────────────────────────────────────────
    else:
        st.caption("Paste any RSS feed URL that contains the user's posts (e.g. their blog, newsletter, or a self-hosted RSSHub/Nitter).")
        with st.form("rss_form", clear_on_submit=True):
            col_r1, col_r2, col_r3 = st.columns([3, 1, 1])
            with col_r1:
                rss_url = st.text_input("RSS feed URL", placeholder="https://example.com/feed.xml")
            with col_r2:
                rss_author = st.text_input("Author label", placeholder="elonmusk")
            with col_r3:
                rss_max = st.number_input("Max items", min_value=1, max_value=20, value=5)
            rss_btn = st.form_submit_button("Fetch from RSS", use_container_width=True)

        if rss_btn:
            if rss_url.strip():
                with st.spinner("Fetching RSS feed…"):
                    try:
                        import requests as _req
                        resp = _req.get(rss_url.strip(), timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                        import feedparser as _fp
                        feed = _fp.parse(resp.content)
                        added = 0
                        for entry in feed.entries[:rss_max]:
                            raw = entry.get("summary", entry.get("title", ""))
                            text = re.sub(r"<[^>]+>", "", raw).strip() or entry.get("title", "")
                            if text:
                                st.session_state.queue.append({
                                    "text": text,
                                    "author": rss_author.strip().lstrip("@") or "unknown",
                                    "link": entry.get("link", ""),
                                    "translation": None,
                                })
                                added += 1
                        st.success(f"Added {added} items from the feed.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not fetch feed: {e}")
            else:
                st.warning("Enter a feed URL.")

    # ── Queue ──────────────────────────────────────────────────────────────────
    st.divider()
    if not st.session_state.queue:
        st.info("Your queue is empty — add tweets above.")
    else:
        col_hd, col_clr = st.columns([5, 1])
        with col_hd:
            st.markdown(f"**{len(st.session_state.queue)} tweet(s) in queue:**")
        with col_clr:
            if st.button("🗑 Clear all", use_container_width=True):
                st.session_state.queue = []
                st.rerun()

        to_remove = []
        for k, item in enumerate(st.session_state.queue):
            label = f"@{item['author']}  —  {item['text'][:80]}{'…' if len(item['text']) > 80 else ''}"
            with st.expander(label, expanded=item["translation"] is None):
                st.info(item["text"])
                if item.get("link"):
                    st.markdown(f"[🔗 Source]({item['link']})")

                col_tr, col_rm = st.columns([3, 1])
                with col_tr:
                    if st.button("Translate to Arabic", key=f"utr_{k}", use_container_width=True):
                        with st.spinner("Translating…"):
                            try:
                                arabic = translate_tweet(item["text"], item["author"])
                                attribution = f"\n\n(via @{item['author']})"
                                st.session_state.queue[k]["translation"] = arabic + attribution
                                st.rerun()
                            except Exception as e:
                                st.error(f"Translation failed: {e}")
                with col_rm:
                    if st.button("🗑 Remove", key=f"urm_{k}", use_container_width=True):
                        to_remove.append(k)

                if item["translation"]:
                    st.divider()
                    col_ar, col_cnt = st.columns([6, 1])
                    with col_ar:
                        edited_ar = st.text_area(
                            "Arabic translation — edit if needed",
                            value=item["translation"],
                            key=f"uar_{k}",
                            height=160,
                        )
                    with col_cnt:
                        count = len(edited_ar)
                        st.metric(label="chars", value=count)
                        st.caption("🔴" if count > 280 else "🟢")

                    if count > 280:
                        st.warning("Exceeds 280 characters — shorten before posting.")

                    post_col2, _ = st.columns([1, 3])
                    with post_col2:
                        if st.button("🚀 Post", key=f"upost_{k}", type="primary",
                                     use_container_width=True, disabled=count > 280):
                            with st.spinner("Posting…"):
                                try:
                                    from x_arabic_poster import BrowserTweetPoster
                                    tid = BrowserTweetPoster().post(edited_ar)
                                    st.success(f"✅ Posted! [View](https://x.com/i/web/status/{tid})")
                                    to_remove.append(k)
                                except Exception as e:
                                    st.error(f"Post failed: {e}")
                                    dbg = Path(__file__).parent / "debug_screenshot.png"
                                    if dbg.exists():
                                        st.image(str(dbg), caption="What X showed (debug)")

        for idx in sorted(to_remove, reverse=True):
            st.session_state.queue.pop(idx)
        if to_remove:
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — AI Content Engine
# ═══════════════════════════════════════════════════════════════════════════════
with tab_generate:
    from arabic_x_poster.content_engine import ContentEngine, ContentStorage
    from arabic_x_poster.factory import ServiceFactory

    @st.cache_resource
    def _get_storage():
        return ServiceFactory.content_storage()

    storage = _get_storage()

    POST_TYPES = [
        "Builder story", "Debugging experience", "Lesson learned", "Project update",
        "Workflow breakdown", "Hot take / Opinion", "Beginner mistake",
        "Productivity insight", "Tool review", "Coding frustration",
        "Thread", "Comparison", "Question post", "Today I Learned (TIL)",
        "Technical simplification",
    ]
    TONES = [
        "Curious", "Reflective", "Frustrated (relatable)", "Analytical",
        "Casual", "Confident", "Humble",
    ]
    AUDIENCE_LEVELS = ["Beginner devs", "Intermediate devs", "Advanced / senior devs", "General tech followers"]
    TOPIC_PRESETS = [
        "Custom...", "AI tools & APIs", "Coding & debugging", "React / Next.js",
        "Python", "Automation", "Cybersecurity", "Developer productivity",
        "Open source", "SaaS building", "Data science", "Developer tools",
    ]

    st.subheader("🧠 AI Content Engine")
    st.caption("A guided content strategist — not just a generator. Builds a realistic developer voice over time.")

    from arabic_x_poster.content_engine.account_voice import VOICE_PROFILE
    with st.expander("🎭 Account Voice Profile (applied to all content)", expanded=False):
        vc1, vc2, vc3 = st.columns(3)
        with vc1:
            st.caption(f"**Tone:** {VOICE_PROFILE['tone']}")
            st.caption(f"**Confidence:** {VOICE_PROFILE['confidence_style']}")
            st.caption(f"**Style:** {VOICE_PROFILE['writing_style']}")
        with vc2:
            st.caption(f"**Emoji usage:** {VOICE_PROFILE['emoji_usage']}")
            st.caption(f"**Technical depth:** {VOICE_PROFILE['technical_depth']}")
        with vc3:
            traits = ", ".join(VOICE_PROFILE["personality_traits"])
            st.caption(f"**Traits:** {traits}")
            prefers = " · ".join(VOICE_PROFILE["prefers"])
            st.caption(f"**Prefers:** {prefers}")

    # ── Controls ──────────────────────────────────────────────────────────────
    ctrl_col, gen_col = st.columns([1, 2], gap="large")

    with ctrl_col:
        st.markdown("**Content Setup**")

        topic_preset = st.selectbox("Topic", TOPIC_PRESETS, key="ce_topic_preset")
        if topic_preset == "Custom...":
            topic = st.text_input("Describe the topic", placeholder="e.g. why I stopped using Redux", key="ce_custom_topic")
        else:
            topic = topic_preset

        post_type = st.selectbox("Post Type", POST_TYPES, key="ce_post_type_sel")
        tone = st.selectbox("Tone", TONES, key="ce_tone_sel")
        audience_level = st.selectbox("Audience Level", AUDIENCE_LEVELS, key="ce_audience_sel")
        platform = st.radio("Platform", ["Single tweet", "Thread (3–6 tweets)"], horizontal=True, key="ce_platform_sel")
        language = st.radio("Language", ["English", "Arabic"], horizontal=True, key="ce_language_sel")

        with st.expander("🌐 Trend / Context Keywords (optional)", expanded=False):
            context_keywords = st.text_area(
                "Add trending topics or keywords to enrich context",
                placeholder="e.g. Cursor IDE, AI pair programming, burnout in dev teams",
                height=80, key="ce_context_kw",
            )

        n_hooks = st.slider("Hooks to generate", min_value=5, max_value=10, value=7, key="ce_n_hooks")

        generate_hooks_btn = st.button(
            "⚡ Generate Hooks", type="primary", use_container_width=True,
            disabled=not (topic or "").strip(),
        )

    # ── Generation area ───────────────────────────────────────────────────────
    with gen_col:

        # PHASE 1 — Generate hooks
        if generate_hooks_btn and (topic or "").strip():
            with st.spinner("Expanding intent…"):
                try:
                    engine = ServiceFactory.content_engine()
                    ctx = storage.get_continuity_context(5)
                    intent = engine.expand_intent(
                        topic=topic,
                        post_type=post_type,
                        tone=tone,
                        audience_level=audience_level,
                        context_keywords=context_keywords or "",
                        continuity_context=ctx,
                    )
                    st.session_state.ce_intent = intent
                except Exception:
                    st.session_state.ce_intent = {"core_message": topic}
                    engine = ServiceFactory.content_engine()

            with st.spinner("Generating hooks…"):
                try:
                    hooks = engine.generate_hooks(
                        topic=topic,
                        post_type=post_type,
                        tone=tone,
                        language=language,
                        intent_profile=st.session_state.get("ce_intent", {}),
                        n_hooks=n_hooks,
                    )
                    with st.spinner("Scoring hooks…"):
                        hooks = engine.score_hooks(hooks)
                    st.session_state.ce_hooks = hooks
                    st.session_state.ce_selected_hook_idx = 0
                    st.session_state.ce_topic = topic
                    st.session_state.ce_post_type = post_type
                    st.session_state.ce_tone = tone
                    st.session_state.ce_audience_level = audience_level
                    st.session_state.ce_platform = platform
                    st.session_state.ce_language = language
                    st.session_state.ce_post = None
                    st.session_state.ce_humanized = None
                    st.session_state.ce_draft_id = None
                    st.session_state.ce_thread_tweets = None
                except Exception as e:
                    st.error(f"Hook generation failed: {e}")

        # PHASE 2 — Show intent profile + hooks
        if "ce_hooks" in st.session_state and st.session_state.ce_hooks:
            hooks = st.session_state.ce_hooks

            intent = st.session_state.get("ce_intent", {})
            if intent and intent.get("core_message"):
                with st.expander("🧭 Intent Profile (what the AI understood)", expanded=False):
                    st.markdown(f"**Core message:** {intent.get('core_message', '—')}")
                    st.markdown(f"**Target insight:** {intent.get('target_insight', '—')}")
                    st.markdown(f"**Emotional angle:** {intent.get('emotional_angle', '—')}")
                    st.markdown(f"**Experience anchor:** {intent.get('experience_anchor', '—')}")
                    if intent.get("continuity_hook"):
                        st.markdown(f"**Continuity reference:** {intent['continuity_hook']}")

            st.markdown("**Hooks — select the best:**")

            for idx, hook in enumerate(hooks):
                is_best = idx == 0
                is_selected = st.session_state.get("ce_selected_hook_idx", 0) == idx
                badge = " ⭐ Best" if is_best else ""
                sel_label = " ✓ Selected" if is_selected else ""

                with st.container(border=True):
                    h_col, s_col, btn_col = st.columns([5, 4, 1])
                    with h_col:
                        st.markdown(f"**{idx+1}.{badge}{sel_label}**")
                        st.write(hook.text)
                    with s_col:
                        st.caption(
                            f"🔍 Curiosity **{hook.curiosity:.0f}**  "
                            f"📖 Clarity **{hook.clarity:.0f}**  "
                            f"💡 Pull **{hook.emotional_pull:.0f}**  "
                            f"🙂 Real **{hook.realism:.0f}**  "
                            f"📣 Engage **{hook.engagement_potential:.0f}**  "
                            f"→ **{hook.avg:.1f}/10**"
                        )
                    with btn_col:
                        if st.button("Use", key=f"use_hook_{idx}", use_container_width=True):
                            st.session_state.ce_selected_hook_idx = idx
                            st.session_state.ce_post = None
                            st.session_state.ce_humanized = None
                            st.session_state.ce_thread_tweets = None
                            st.rerun()

            selected_hook = hooks[st.session_state.get("ce_selected_hook_idx", 0)]
            st.info(f"**Selected:** {selected_hook.text}")

            regen_col, gen_post_col = st.columns(2)
            with regen_col:
                if st.button("🔄 Regenerate Hooks", use_container_width=True):
                    for k in ["ce_hooks", "ce_post", "ce_humanized", "ce_draft_id", "ce_thread_tweets", "ce_intent"]:
                        st.session_state.pop(k, None)
                    st.rerun()
            with gen_post_col:
                gen_post_btn = st.button("✍️ Generate Post", type="primary", use_container_width=True)

            # PHASE 3 — Generate post
            if gen_post_btn:
                saved = {k.replace("ce_", ""): st.session_state.get(k) for k in
                         ["ce_platform", "ce_tone", "ce_language", "ce_audience_level", "ce_topic", "ce_post_type"]}
                is_thread = "Thread" in (saved.get("platform") or "")
                intent_profile = st.session_state.get("ce_intent", {})

                with st.spinner("Writing post…"):
                    try:
                        engine = ServiceFactory.content_engine()
                        st.session_state.ce_guard_notice = None
                        if is_thread:
                            n_tw = st.session_state.get("ce_n_thread_tweets", 4)
                            tweets = engine.generate_thread(
                                hook=selected_hook,
                                topic=saved.get("topic", topic),
                                tone=saved.get("tone", tone),
                                audience_level=saved.get("audience_level", audience_level),
                                language=saved.get("language", language),
                                intent_profile=intent_profile,
                                n_tweets=n_tw,
                            )
                            st.session_state.ce_thread_tweets = tweets
                            st.session_state.ce_post = "\n\n".join(tweets)
                        else:
                            raw, guard = engine.generate_post(
                                hook=selected_hook,
                                topic=saved.get("topic", topic),
                                post_type=saved.get("post_type", post_type),
                                tone=saved.get("tone", tone),
                                audience_level=saved.get("audience_level", audience_level),
                                platform=saved.get("platform", platform),
                                language=saved.get("language", language),
                                intent_profile=intent_profile,
                            )
                            if guard.was_downgraded:
                                st.session_state.ce_guard_notice = guard.notice
                            st.session_state.ce_post = raw
                            st.session_state.ce_thread_tweets = None

                        with st.spinner("Humanizing + voice & originality check…"):
                            humanized, h_guard, v_check = engine.humanize(
                                content=st.session_state.ce_post,
                                tone=saved.get("tone", tone),
                                language=saved.get("language", language),
                            )
                            if h_guard.was_downgraded and not st.session_state.get("ce_guard_notice"):
                                st.session_state.ce_guard_notice = h_guard.notice
                            if v_check.was_corrected:
                                st.session_state.ce_voice_notice = v_check.notice
                            if is_thread:
                                lines = [l.strip() for l in humanized.split("\n\n") if l.strip()]
                                if len(lines) >= 2:
                                    st.session_state.ce_thread_tweets = lines
                            st.session_state.ce_humanized = humanized

                    except Exception as e:
                        st.error(f"Post generation failed: {e}")

            # PHASE 4 — Display + actions
            if st.session_state.get("ce_post"):
                if st.session_state.get("ce_guard_notice"):
                    st.warning(f"⚠️ **Claim Guard:** {st.session_state['ce_guard_notice']}")
                if st.session_state.get("ce_voice_notice"):
                    st.info(f"🎭 **Voice Guard:** {st.session_state['ce_voice_notice']}")
                st.divider()
                is_thread_mode = bool(st.session_state.get("ce_thread_tweets"))
                saved_tone = st.session_state.get("ce_tone", tone)
                saved_lang = st.session_state.get("ce_language", language)

                if is_thread_mode:
                    thread_tweets = st.session_state.ce_thread_tweets

                    n_tweets_range = st.slider(
                        "Thread length", min_value=3, max_value=6,
                        value=len(thread_tweets), key="ce_n_thread_tweets",
                    )
                    st.markdown("**Thread — edit each tweet:**")
                    edited_tweets: list[str] = []
                    for ti, tw in enumerate(thread_tweets[:n_tweets_range]):
                        tc, tcount = st.columns([6, 1])
                        with tc:
                            val = st.text_area(
                                f"Tweet {ti+1}/{n_tweets_range}",
                                value=tw, key=f"ce_tw_{ti}", height=110,
                            )
                            edited_tweets.append(val)
                        with tcount:
                            c = len(val)
                            st.metric("chars", c)
                            st.caption("🔴" if c > 280 else "🟢")

                    over = [i+1 for i, t in enumerate(edited_tweets) if len(t) > 280]
                    if over:
                        st.warning(f"Tweet(s) {over} exceed 280 chars.")

                    act1, act2, act3, act4 = st.columns(4)
                    with act1:
                        if st.button("💾 Save Draft", use_container_width=True, key="ce_save_thread"):
                            did = storage.save_draft({
                                "topic": st.session_state.get("ce_topic", topic),
                                "post_type": st.session_state.get("ce_post_type", post_type),
                                "tone": saved_tone, "audience_level": st.session_state.get("ce_audience_level", audience_level),
                                "platform": "Thread", "language": saved_lang,
                                "hooks": [h.text for h in hooks],
                                "selected_hook": selected_hook.text,
                                "hook_scores": [{"text": h.text, "avg": h.avg} for h in hooks],
                                "raw_content": st.session_state.ce_post,
                                "humanized_content": "\n\n".join(edited_tweets),
                                "intent_profile": st.session_state.get("ce_intent", {}),
                            })
                            st.session_state.ce_draft_id = did
                            st.success(f"Saved draft #{did}")
                    with act2:
                        if st.button("📅 Schedule", use_container_width=True, key="ce_sched_thread"):
                            st.session_state.ce_show_schedule_thread = True
                    with act3:
                        if st.button("🔁 Regenerate", use_container_width=True, key="ce_regen_thread"):
                            st.session_state.ce_post = None
                            st.session_state.ce_humanized = None
                            st.session_state.ce_thread_tweets = None
                            st.rerun()
                    with act4:
                        if st.button("🚀 Post Thread", type="primary", use_container_width=True,
                                     disabled=bool(over), key="ce_post_thread"):
                            with st.spinner("Posting thread…"):
                                try:
                                    ids = post_thread(edited_tweets)
                                    did = st.session_state.get("ce_draft_id")
                                    if not did:
                                        did = storage.save_draft({
                                            "topic": topic, "post_type": post_type, "tone": tone,
                                            "audience_level": audience_level, "platform": "Thread",
                                            "language": language, "hooks": [h.text for h in hooks],
                                            "selected_hook": selected_hook.text, "hook_scores": [],
                                            "raw_content": st.session_state.ce_post,
                                            "humanized_content": "\n\n".join(edited_tweets),
                                            "intent_profile": st.session_state.get("ce_intent", {}),
                                        })
                                    storage.mark_posted(did, ids[0])
                                    st.session_state.ce_draft_id = did
                                    st.success(f"✅ Thread of {len(ids)} tweets posted! [View](https://x.com/i/web/status/{ids[0]})")
                                except Exception as e:
                                    st.error(f"Post failed: {e}")

                    if st.session_state.get("ce_show_schedule_thread"):
                        with st.form("schedule_thread_form"):
                            sched_date = st.date_input("Date", key="ce_sched_date_t")
                            sched_time = st.time_input("Time", key="ce_sched_time_t")
                            if st.form_submit_button("Confirm Schedule"):
                                did = st.session_state.get("ce_draft_id")
                                if not did:
                                    did = storage.save_draft({
                                        "topic": topic, "post_type": post_type, "tone": tone,
                                        "audience_level": audience_level, "platform": "Thread",
                                        "language": language, "hooks": [h.text for h in hooks],
                                        "selected_hook": selected_hook.text, "hook_scores": [],
                                        "raw_content": st.session_state.ce_post,
                                        "humanized_content": "\n\n".join(edited_tweets),
                                        "intent_profile": st.session_state.get("ce_intent", {}),
                                    })
                                storage.schedule_post(did, f"{sched_date}T{sched_time}")
                                st.session_state.ce_draft_id = did
                                st.session_state.ce_show_schedule_thread = False
                                st.success(f"Scheduled for {sched_date} at {sched_time}")
                                st.rerun()

                else:
                    st.markdown("**Post — edit before publishing:**")
                    humanized = st.session_state.get("ce_humanized") or st.session_state.ce_post
                    edited_post = st.text_area(
                        "Final content", value=humanized, key="ce_final_edit", height=220,
                    )
                    char_count = len(edited_post)
                    cc1, cc2 = st.columns([1, 5])
                    with cc1:
                        st.metric("chars", char_count)
                        st.caption("🔴" if char_count > 280 else "🟢")

                    pa1, pa2, pa3, pa4 = st.columns(4)
                    with pa1:
                        if st.button("💾 Save Draft", use_container_width=True, key="ce_save_single"):
                            did = storage.save_draft({
                                "topic": st.session_state.get("ce_topic", topic),
                                "post_type": st.session_state.get("ce_post_type", post_type),
                                "tone": saved_tone, "audience_level": st.session_state.get("ce_audience_level", audience_level),
                                "platform": "Single tweet", "language": saved_lang,
                                "hooks": [h.text for h in hooks],
                                "selected_hook": selected_hook.text,
                                "hook_scores": [{"text": h.text, "avg": h.avg} for h in hooks],
                                "raw_content": st.session_state.ce_post,
                                "humanized_content": edited_post,
                                "intent_profile": st.session_state.get("ce_intent", {}),
                            })
                            st.session_state.ce_draft_id = did
                            st.success(f"Saved draft #{did}")
                    with pa2:
                        if st.button("📅 Schedule", use_container_width=True, key="ce_sched_single"):
                            st.session_state.ce_show_schedule_single = True
                    with pa3:
                        if st.button("🔁 Regenerate", use_container_width=True, key="ce_regen_single"):
                            st.session_state.ce_post = None
                            st.session_state.ce_humanized = None
                            st.rerun()
                    with pa4:
                        if st.button("🚀 Post to X", type="primary", use_container_width=True,
                                     disabled=char_count > 280, key="ce_post_single"):
                            with st.spinner("Posting…"):
                                try:
                                    from x_arabic_poster import BrowserTweetPoster
                                    tid = BrowserTweetPoster().post(edited_post)
                                    did = st.session_state.get("ce_draft_id")
                                    if not did:
                                        did = storage.save_draft({
                                            "topic": topic, "post_type": post_type, "tone": tone,
                                            "audience_level": audience_level, "platform": "Single tweet",
                                            "language": language, "hooks": [h.text for h in hooks],
                                            "selected_hook": selected_hook.text, "hook_scores": [],
                                            "raw_content": st.session_state.ce_post,
                                            "humanized_content": edited_post,
                                            "intent_profile": st.session_state.get("ce_intent", {}),
                                        })
                                    storage.mark_posted(did, tid)
                                    st.session_state.ce_draft_id = did
                                    st.success(f"✅ Posted! [View](https://x.com/i/web/status/{tid})")
                                except Exception as e:
                                    st.error(f"Post failed: {e}")

                    if st.session_state.get("ce_show_schedule_single"):
                        with st.form("schedule_single_form"):
                            sched_date = st.date_input("Date", key="ce_sched_date_s")
                            sched_time = st.time_input("Time", key="ce_sched_time_s")
                            if st.form_submit_button("Confirm Schedule"):
                                did = st.session_state.get("ce_draft_id")
                                if not did:
                                    did = storage.save_draft({
                                        "topic": topic, "post_type": post_type, "tone": tone,
                                        "audience_level": audience_level, "platform": "Single tweet",
                                        "language": language, "hooks": [h.text for h in hooks],
                                        "selected_hook": selected_hook.text, "hook_scores": [],
                                        "raw_content": st.session_state.ce_post,
                                        "humanized_content": edited_post,
                                        "intent_profile": st.session_state.get("ce_intent", {}),
                                    })
                                storage.schedule_post(did, f"{sched_date}T{sched_time}")
                                st.session_state.ce_draft_id = did
                                st.session_state.ce_show_schedule_single = False
                                st.success(f"Scheduled for {sched_date} at {sched_time}")
                                st.rerun()

    # ── Pattern Intelligence Library ──────────────────────────────────────────
    st.divider()
    with st.expander("🔬 Pattern Intelligence Library", expanded=False):
        st.caption(
            "Feed high-performing posts from any creator. The engine extracts structural patterns "
            "(never the text), clusters them into reusable templates, and generates original content from them."
        )

        pat_count = storage.pattern_count()
        clusters = storage.get_clusters()
        pm1, pm2, pm3 = st.columns(3)
        pm1.metric("Patterns stored", pat_count)
        pm2.metric("Clusters", len(clusters))
        pm3.metric("Min for clustering", "3+")

        st.markdown("---")

        # ── Step 1: Feed source posts ──────────────────────────────────────
        st.markdown("**Step 1 — Feed high-performing posts**")
        st.caption("Paste posts from any niche creator. Engagement score helps rank patterns (0 = unknown).")

        with st.form("pattern_feed_form", clear_on_submit=True):
            pf_col1, pf_col2 = st.columns([4, 1])
            with pf_col1:
                source_post_text = st.text_area(
                    "Post text", height=120,
                    placeholder="Paste the source post here (any language)…",
                    key="pf_source_text",
                )
            with pf_col2:
                source_engagement = st.number_input(
                    "Engagement score", min_value=0, max_value=100000,
                    value=0, step=100, key="pf_eng_score",
                    help="Total likes + reposts + replies, or leave 0",
                )
            extract_btn = st.form_submit_button("🔍 Extract Pattern", use_container_width=True)

        if extract_btn and source_post_text.strip():
            with st.spinner("Extracting structural pattern (not storing the text)…"):
                try:
                    from arabic_x_poster.factory import ServiceFactory as SF
                    pe = SF.pattern_engine()
                    clean_text = source_post_text.strip()
                    pattern = pe.extract_pattern(clean_text, float(source_engagement))
                    saved_ok = storage.save_pattern(pattern)
                    if saved_ok:
                        # Keep text in session state (not DB) for originality checking at generation time
                        source_texts = st.session_state.get("pf_source_texts", [])
                        if clean_text not in source_texts:
                            source_texts.append(clean_text)
                        st.session_state.pf_source_texts = source_texts
                        st.success(
                            f"Pattern extracted and stored.  "
                            f"Hook: **{pattern.hook_type}** | Format: **{pattern.content_format}** | "
                            f"Tone: **{pattern.emotional_tone}** | Trigger: **{pattern.engagement_trigger}**"
                        )
                        st.caption(f"Narrative flow: *{pattern.narrative_structure}*")
                        st.caption(f"Source texts held in session for originality checking ({len(source_texts)} total).")
                    else:
                        st.info("This post was already in the library (duplicate).")
                    st.rerun()
                except Exception as e:
                    st.error(f"Pattern extraction failed: {e}")

        # ── Step 2: Cluster ────────────────────────────────────────────────
        if pat_count >= 2:
            st.markdown("---")
            st.markdown("**Step 2 — Cluster into templates**")
            col_cl1, col_cl2 = st.columns([2, 1])
            with col_cl1:
                st.caption(f"{pat_count} pattern(s) in library. Clustering groups similar patterns into ranked templates.")
            with col_cl2:
                if st.button("⚡ Cluster Patterns", use_container_width=True, key="cluster_btn"):
                    patterns = storage.get_patterns()
                    from arabic_x_poster.factory import ServiceFactory as SF
                    pe = SF.pattern_engine()
                    new_clusters = pe.cluster_patterns(patterns)
                    storage.save_clusters(new_clusters)
                    st.success(f"Built {len(new_clusters)} cluster(s).")
                    st.rerun()

        # ── Step 3: View clusters ──────────────────────────────────────────
        if clusters:
            st.markdown("---")
            st.markdown("**Step 3 — Pattern clusters (ranked by avg engagement)**")
            for ci, cluster in enumerate(clusters):
                badge = "⭐ " if ci == 0 else ""
                with st.container(border=True):
                    cc1, cc2 = st.columns([5, 2])
                    with cc1:
                        st.markdown(f"**{badge}{cluster.template_name}**")
                        st.caption(f"*{cluster.template_structure}*")
                    with cc2:
                        st.caption(
                            f"Patterns: **{cluster.pattern_count}**  "
                            f"Avg engagement: **{cluster.avg_engagement:.0f}**"
                        )

            # ── Step 4: Generate from pattern ─────────────────────────────
            st.markdown("---")
            st.markdown("**Step 4 — Generate original content from a pattern**")

            cluster_labels = [f"{c.template_name} (×{c.pattern_count}, eng {c.avg_engagement:.0f})" for c in clusters]
            selected_cluster_label = st.selectbox("Choose a pattern template", cluster_labels, key="pgen_cluster_sel")
            selected_cluster = clusters[cluster_labels.index(selected_cluster_label)]

            pg_col1, pg_col2 = st.columns(2)
            with pg_col1:
                pgen_topic = st.text_input("Your topic", placeholder="e.g. why I stopped using ORMs", key="pgen_topic")
                pgen_tone = st.selectbox("Tone", ["Casual", "Reflective", "Analytical", "Frustrated (relatable)", "Curious"], key="pgen_tone")
            with pg_col2:
                pgen_audience = st.selectbox("Audience", ["Beginner devs", "Intermediate devs", "Advanced / senior devs", "General tech followers"], key="pgen_audience")
                pgen_lang = st.radio("Language", ["English", "Arabic"], horizontal=True, key="pgen_lang")

            if st.button("✨ Generate from Pattern", type="primary", use_container_width=True,
                         disabled=not (pgen_topic or "").strip(), key="pgen_btn"):
                with st.spinner("Generating original post from pattern (uniqueness check included)…"):
                    try:
                        from arabic_x_poster.factory import ServiceFactory as SF
                        pe = SF.pattern_engine()
                        # Source texts kept in session state (never persisted to DB)
                        source_posts_for_check = st.session_state.get("pf_source_texts", [])
                        generated_text, passed = pe.generate_from_pattern(
                            cluster=selected_cluster,
                            topic=pgen_topic.strip(),
                            tone=pgen_tone,
                            language=pgen_lang,
                            audience_level=pgen_audience,
                            source_posts=source_posts_for_check,
                        )
                        if generated_text:
                            st.session_state.pgen_result = generated_text
                            st.session_state.pgen_passed_uniqueness = passed
                            st.session_state.pgen_cluster_used = selected_cluster.template_name
                        else:
                            st.error("Could not generate a unique post after 3 attempts. Try a different topic or cluster.")
                    except Exception as e:
                        st.error(f"Pattern generation failed: {e}")

            if st.session_state.get("pgen_result"):
                passed = st.session_state.get("pgen_passed_uniqueness", True)
                cluster_used = st.session_state.get("pgen_cluster_used", "")
                if not passed:
                    st.warning(
                        "⚠️ **Uniqueness filter flagged this.** The LLM check suggested the output may be "
                        "too close to a source pattern. Edit carefully before posting."
                    )
                else:
                    st.success(f"✅ Uniqueness check passed — pattern used: *{cluster_used}*")

                edited_pgen = st.text_area(
                    "Generated post — edit before posting",
                    value=st.session_state.pgen_result,
                    key="pgen_edit", height=200,
                )
                pg_cc = len(edited_pgen)
                pg_c1, pg_c2, pg_c3 = st.columns([1, 1, 4])
                with pg_c1:
                    st.metric("chars", pg_cc)
                    st.caption("🔴" if pg_cc > 280 else "🟢")
                with pg_c2:
                    if st.button("🚀 Post to X", type="primary", disabled=pg_cc > 280, key="pgen_post_btn"):
                        with st.spinner("Posting…"):
                            try:
                                from x_arabic_poster import BrowserTweetPoster
                                tid = BrowserTweetPoster().post(edited_pgen)
                                st.success(f"✅ Posted! [View](https://x.com/i/web/status/{tid})")
                                del st.session_state["pgen_result"]
                            except Exception as e:
                                st.error(f"Post failed: {e}")

        # ── Manage library ─────────────────────────────────────────────────
        if pat_count > 0:
            st.markdown("---")
            with st.expander("⚙️ Manage pattern library", expanded=False):
                st.caption(f"{pat_count} pattern(s) stored. Deleting clears all patterns and clusters.")
                if st.button("🗑 Clear all patterns", key="clear_patterns_btn"):
                    storage.delete_all_patterns()
                    for k in ["pgen_result", "pgen_passed_uniqueness", "pgen_cluster_used"]:
                        st.session_state.pop(k, None)
                    st.success("Pattern library cleared.")
                    st.rerun()

    # ── Analytics & Performance Insights ──────────────────────────────────────
    st.divider()
    with st.expander("📊 Analytics & Performance Insights", expanded=False):
        analytics = storage.get_analytics()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Generated", analytics["total_generated"])
        m2.metric("Posted", analytics["total_posted"])
        m3.metric("Scheduled", analytics["total_scheduled"])
        m4.metric("Avg Performance", analytics["avg_performance"])

        insights = storage.get_performance_insights()
        if insights["best_types"]:
            ic1, ic2, ic3 = st.columns(3)
            with ic1:
                st.markdown("**Best post types:**")
                for ptype, score, count in insights["best_types"]:
                    st.caption(f"• {ptype} — score {score} ({count} posts)")
            with ic2:
                st.markdown("**Best topics:**")
                for tp, score, count in insights["best_topics"]:
                    st.caption(f"• {tp} — score {score} ({count} posts)")
            with ic3:
                st.markdown("**Best tones:**")
                for tn, score in insights["best_tones"]:
                    st.caption(f"• {tn} — score {score}")
        else:
            st.caption("Post content and add engagement metrics to unlock performance insights.")

        # Engagement update form
        recent_posted = [p for p in storage.get_recent_posts(20) if p.get("status") == "posted"]
        if recent_posted:
            st.markdown("**Update engagement metrics:**")
            selected_post_label = st.selectbox(
                "Select posted content",
                options=[f"#{p['id']} — {p['topic']} ({p['posted_at'][:10] if p.get('posted_at') else '?'})" for p in recent_posted],
                key="ce_eng_selector",
            )
            if selected_post_label:
                sel_id = int(selected_post_label.split("#")[1].split(" ")[0])
                sel_post = next((p for p in recent_posted if p["id"] == sel_id), None)
                if sel_post:
                    with st.form(f"eng_form_{sel_id}"):
                        e1, e2, e3 = st.columns(3)
                        e4, e5, e6 = st.columns(3)
                        likes = e1.number_input("Likes", min_value=0, value=int(sel_post.get("likes") or 0))
                        retweets = e2.number_input("Reposts", min_value=0, value=int(sel_post.get("retweets") or 0))
                        replies = e3.number_input("Replies", min_value=0, value=int(sel_post.get("replies") or 0))
                        impressions = e4.number_input("Impressions", min_value=0, value=int(sel_post.get("impressions") or 0))
                        bookmarks = e5.number_input("Bookmarks", min_value=0, value=int(sel_post.get("bookmarks") or 0))
                        profile_visits = e6.number_input("Profile visits", min_value=0, value=int(sel_post.get("profile_visits") or 0))
                        if st.form_submit_button("Update Metrics"):
                            storage.update_engagement(sel_id, likes, retweets, replies, impressions, bookmarks, profile_visits)
                            st.success("Metrics updated — performance score recalculated.")
                            st.rerun()

        # History
        recent = storage.get_recent_posts(15)
        if recent:
            st.markdown("**Recent content:**")
            for post in recent:
                status_icon = {"posted": "✅", "scheduled": "📅", "draft": "📝"}.get(post.get("status", "draft"), "📝")
                preview = (post.get("humanized_content") or post.get("raw_content") or "")[:90]
                with st.expander(
                    f"{status_icon} {post.get('post_type', '—')}  |  {post.get('topic', '—')}  |  {(post.get('created_at') or '')[:16]}",
                    expanded=False,
                ):
                    st.caption(f"**Tone:** {post.get('tone', '—')}  |  **Audience:** {post.get('audience_level', '—')}  |  **Lang:** {post.get('language', '—')}")
                    st.text(preview + ("…" if len(preview) == 90 else ""))
                    if post.get("scheduled_for"):
                        st.caption(f"📅 Scheduled: {post['scheduled_for']}")
                    if post.get("tweet_id"):
                        st.markdown(f"[View on X](https://x.com/i/web/status/{post['tweet_id']})")
                    if post.get("status") == "posted":
                        st.caption(
                            f"❤️ {post.get('likes', 0)}  🔁 {post.get('retweets', 0)}  "
                            f"💬 {post.get('replies', 0)}  👁 {post.get('impressions', 0)}  "
                            f"🔖 {post.get('bookmarks', 0)}  📈 score {post.get('performance_score', 0)}"
                        )
                    if st.button("🗑 Delete", key=f"del_ce_{post['id']}", use_container_width=False):
                        storage.delete_draft(post["id"])
                        st.rerun()

    # ── Reply Generator ───────────────────────────────────────────────────────
    st.divider()
    with st.expander("💬 Reply Generator", expanded=False):
        st.caption("Paste a tweet you want to reply to. Get a genuine developer reply — not generic praise.")
        reply_tweet = st.text_area("Tweet to reply to", height=90, key="ce_reply_input",
                                   placeholder="Paste the tweet text here…")
        reply_lang = st.radio("Reply language", ["English", "Arabic"], horizontal=True, key="ce_reply_lang")
        if st.button("Generate Reply", key="ce_gen_reply"):
            if reply_tweet.strip():
                with st.spinner("Generating reply…"):
                    try:
                        engine = ServiceFactory.content_engine()
                        reply = engine.generate_reply(reply_tweet.strip(), reply_lang)
                        st.session_state.ce_reply_text = reply
                    except Exception as e:
                        st.error(f"Reply generation failed: {e}")
            else:
                st.warning("Paste a tweet first.")

        if "ce_reply_text" in st.session_state:
            edited_reply = st.text_area(
                "Reply — edit if needed",
                value=st.session_state.ce_reply_text,
                key="ce_reply_edit", height=110,
            )
            rc = len(edited_reply)
            st.caption(f"{rc} chars  {'🔴' if rc > 280 else '🟢'}")
            if st.button("🚀 Post Reply", key="ce_post_reply", type="primary", disabled=rc > 280):
                with st.spinner("Posting…"):
                    try:
                        from x_arabic_poster import BrowserTweetPoster
                        tid = BrowserTweetPoster().post(edited_reply)
                        st.success(f"✅ [View](https://x.com/i/web/status/{tid})")
                        del st.session_state["ce_reply_text"]
                    except Exception as e:
                        st.error(f"Post failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Trend Intelligence
# ═══════════════════════════════════════════════════════════════════════════════
with tab_trends:
    from arabic_x_poster.trend_intelligence.ui_tab import render_tab as _render_trend_tab
    _render_trend_tab()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Educational Content Engine
# ═══════════════════════════════════════════════════════════════════════════════
with tab_edu:
    from arabic_x_poster.educational.ui_tab import render_tab as _render_edu_tab
    _render_edu_tab()
