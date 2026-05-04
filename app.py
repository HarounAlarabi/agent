import os
import re
import json
import tweepy
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

from x_arabic_poster import scan_rss, translate_to_thread, post_thread, translate_tweet, fetch_user_tweets_browser, fetch_article, SESSION_FILE, ThreadPostError

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
    n_tweets = st.slider("Tweets per thread", min_value=2, max_value=3, value=2)
    max_articles = st.slider("Articles per feed", min_value=1, max_value=10, value=3)

    st.divider()
    st.subheader("📡 RSS Feeds")
    default_feeds = (
        "https://techcrunch.com/category/artificial-intelligence/feed\n"
        "https://feeds.bbci.co.uk/news/technology/rss.xml"
    )
    feeds_input = st.text_area("One URL per line", value=default_feeds, height=120)
    feeds = [f.strip() for f in feeds_input.strip().splitlines() if f.strip()]

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
        st.success(f"Found {len(articles)} articles.")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_rss, tab_accounts, tab_users = st.tabs(["📰 RSS Feeds", "👥 My Accounts", "✍️ Translate & Post"])


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
                            content = full_text if len(full_text) > 300 else article.get("summary", "")
                            with st.spinner("Translating…"):
                                try:
                                    tweets = translate_to_thread(
                                        title=article["title"],
                                        summary=content,
                                        n_tweets=n_tweets,
                                    )
                                    st.session_state.threads[i] = tweets
                                except Exception as e:
                                    st.error(f"Translation failed: {e}")

                    if i in st.session_state.get("threads", {}):
                        tweets_list: list[str] = st.session_state.threads[i]
                        st.divider()
                        st.markdown("**Arabic Thread Preview** — edit before posting:")

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
                                        ids = post_thread(edited, source_url=article["link"])
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
