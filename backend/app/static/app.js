// LifeFeed single-page client. No build step: plain ES modules served by FastAPI.

const MAX_LEN = 280;
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ---------------------------------------------------------------- state & api

const state = {
  token: safeStorage("get", "lf_token"),
  me: null,
};

function safeStorage(op, key, value) {
  try {
    if (op === "get") return localStorage.getItem(key);
    if (op === "set") localStorage.setItem(key, value);
    if (op === "del") localStorage.removeItem(key);
  } catch { /* storage unavailable (private mode etc.) */ }
  return null;
}

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }

  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && state.token) { setSession(null); go("#/login"); }
    throw new ApiError(res.status, errorMessage(data) || `Request failed (${res.status})`);
  }
  return data;
}

function errorMessage(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail) && data.detail.length) {
    const d = data.detail[0];
    const field = d.loc?.[d.loc.length - 1];
    return field && typeof field === "string" ? `${field}: ${d.msg}` : d.msg;
  }
  return null;
}

function setSession(session) {
  if (session) {
    state.token = session.access_token;
    state.me = session.user;
    safeStorage("set", "lf_token", state.token);
  } else {
    state.token = null;
    state.me = null;
    safeStorage("del", "lf_token");
  }
}

function requireLogin() {
  if (state.me) return true;
  go("#/login");
  return false;
}

// -------------------------------------------------------------------- helpers

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function linkify(text) {
  return esc(text)
    .replace(/https?:\/\/[^\s<]+[^\s<.,:;!?)"']/g, (url) => `<a class="link" href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`)
    .replace(/(^|[^\w/])@(\w{3,30})/g, (_, pre, name) => `${pre}<a class="mention" href="#/u/${name}">@${name}</a>`);
}

function html(strings, ...values) {
  const tpl = document.createElement("template");
  tpl.innerHTML = String.raw(strings, ...values).trim();
  return tpl.content.firstElementChild;
}

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2800);
}

function relTime(iso) {
  const date = new Date(iso);
  const secs = Math.max(0, (Date.now() - date) / 1000);
  if (secs < 60) return `${Math.floor(secs)}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  const opts = { month: "short", day: "numeric" };
  if (date.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
  return date.toLocaleDateString(undefined, opts);
}

function fullTime(iso) {
  const d = new Date(iso);
  return `${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })} · ${d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
}

function compact(n) {
  if (!n) return "";
  return n < 1000 ? String(n) : `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}K`;
}

function avatar(user, size = "") {
  if (user.avatar_url) {
    return `<img class="avatar ${size}" src="${esc(user.avatar_url)}" alt="">`;
  }
  let hash = 0;
  for (const ch of user.username) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  const hue = Math.abs(hash) % 360;
  const initial = esc((user.display_name || user.username).trim()[0]?.toUpperCase() || "?");
  return `<div class="avatar ${size}" style="background:hsl(${hue} 65% 48%)" aria-hidden="true">${initial}</div>`;
}

const icons = {
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z"/></svg>',
  explore: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  profile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/></svg>',
  login: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/></svg>',
  reply: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>',
  repost: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 2l3 3-3 3M4 11V9a4 4 0 0 1 4-4h12M7 22l-3-3 3-3M20 13v2a4 4 0 0 1-4 4H4"/></svg>',
  like: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 20s-7.5-4.6-9.2-9.4C1.6 7.2 4 4 7.2 4c2 0 3.6 1.1 4.8 2.8C13.2 5.1 14.8 4 16.8 4 20 4 22.4 7.2 21.2 10.6 19.5 15.4 12 20 12 20z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3"/></svg>',
  image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg>',
};

// ------------------------------------------------------------------ post card

function postCard(post, { focus = false, ancestor = false } = {}) {
  const shown = post.repost_of || post;
  const author = shown.author;
  const context = post.repost_of
    ? `<div class="post-context">↻ ${post.author.id === state.me?.id ? "You" : esc(post.author.display_name)} reposted</div>`
    : "";
  const replying = shown.reply_to_username
    ? `<div class="muted">Replying to <a class="mention" href="#/u/${esc(shown.reply_to_username)}">@${esc(shown.reply_to_username)}</a></div>`
    : "";
  const media = shown.media_url ? `<img class="post-media" src="${esc(shown.media_url)}" alt="" loading="lazy">` : "";
  const text = shown.content ? `<div class="post-text">${linkify(shown.content)}</div>` : "";
  const meta = `
    <div class="post-meta">
      <a class="name" href="#/u/${esc(author.username)}">${esc(author.display_name)}</a>
      <span class="handle">@${esc(author.username)}${focus ? "" : ` · <span title="${esc(fullTime(shown.created_at))}">${relTime(shown.created_at)}</span>`}</span>
    </div>`;

  const el = focus
    ? html`<article class="post focus" data-oid="${shown.id}">
        <div style="display:flex;gap:12px;align-items:center">
          <a href="#/u/${esc(author.username)}">${avatar(author)}</a>
          <div class="names"><a class="name" href="#/u/${esc(author.username)}">${esc(author.display_name)}</a>
          <span class="handle">@${esc(author.username)}</span></div>
        </div>
        ${replying}${text}${media}
        <div class="post-time-full">${esc(fullTime(shown.created_at))}</div>
        <div class="post-actions"></div>
      </article>`
    : html`<div>${context}<article class="post${ancestor ? " ancestor" : ""}" data-oid="${shown.id}" data-id="${post.id}">
        <div class="post-gutter"><a href="#/u/${esc(author.username)}">${avatar(author)}</a></div>
        <div class="post-main">${meta}${replying}${text}${media}<div class="post-actions"></div></div>
      </article></div>`;

  renderActions($(".post-actions", el), shown);

  if (!focus) {
    const article = $("article", el);
    article.addEventListener("click", (e) => {
      if (e.target.closest("a, button") || window.getSelection().toString()) return;
      go(`#/p/${shown.id}`);
    });
  }
  return el;
}

function renderActions(bar, post) {
  const mine = state.me && post.author.id === state.me.id;
  bar.innerHTML = `
    <button class="action reply" title="Reply">
      <span class="ico">${icons.reply}</span><span>${compact(post.reply_count)}</span></button>
    <button class="action repost${post.reposted_by_me ? " on" : ""}" title="${post.reposted_by_me ? "Undo repost" : "Repost"}">
      <span class="ico">${icons.repost}</span><span>${compact(post.repost_count)}</span></button>
    <button class="action like${post.liked_by_me ? " on" : ""}" title="${post.liked_by_me ? "Unlike" : "Like"}">
      <span class="ico">${icons.like}</span><span>${compact(post.like_count)}</span></button>
    ${mine ? `<button class="action delete" title="Delete"><span class="ico">${icons.trash}</span></button>` : "<span></span>"}`;

  $(".reply", bar).onclick = () => openReplyDialog(post);
  $(".like", bar).onclick = (e) => toggle(e.currentTarget, post, "like", post.liked_by_me);
  $(".repost", bar).onclick = (e) => toggle(e.currentTarget, post, "repost", post.reposted_by_me);
  const del = $(".delete", bar);
  if (del) del.onclick = () => deletePost(post);
}

async function toggle(button, post, kind, isOn) {
  if (!requireLogin()) return;
  button.disabled = true;
  try {
    const updated = await api(`/api/posts/${post.id}/${kind}`, { method: isOn ? "DELETE" : "POST" });
    syncPost(updated);
    if (kind === "repost") toast(isOn ? "Repost removed" : "Reposted");
  } catch (err) {
    toast(err.message, true);
    button.disabled = false;
  }
}

// Every card showing this post (as itself or inside a repost) gets fresh counts.
function syncPost(updated) {
  for (const article of $$(`article[data-oid="${updated.id}"]`)) {
    renderActions($(".post-actions", article), updated);
  }
}

async function deletePost(post) {
  if (!confirm("Delete this post? This can't be undone.")) return;
  try {
    await api(`/api/posts/${post.id}`, { method: "DELETE" });
    toast("Post deleted");
    if (location.hash === `#/p/${post.id}`) { history.back(); return; }
    for (const article of $$(`article[data-oid="${post.id}"]`)) article.parentElement.remove();
  } catch (err) {
    toast(err.message, true);
  }
}

// ------------------------------------------------------------------ compose

function composer({ placeholder = "What's happening?", replyTo = null, onPosted, autofocus = false } = {}) {
  const el = html`<div class="compose">
      ${avatar(state.me)}
      <div class="compose-body">
        <textarea rows="2" maxlength="${MAX_LEN + 50}" placeholder="${esc(placeholder)}"></textarea>
        <div class="compose-preview" hidden><img alt=""><button type="button" title="Remove image">✕</button></div>
        <div class="compose-bar">
          <label class="icon-btn" title="Add image">${icons.image}
            <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden></label>
          <span class="grow"></span>
          <span class="counter"></span>
          <button class="btn" disabled>${replyTo ? "Reply" : "Post"}</button>
        </div>
      </div>
    </div>`;
  const textarea = $("textarea", el);
  const submit = $(".btn", el);
  const counter = $(".counter", el);
  const preview = $(".compose-preview", el);
  const fileInput = $("input[type=file]", el);
  let mediaUrl = null;
  let uploading = false;

  const refresh = () => {
    const left = MAX_LEN - textarea.value.length;
    counter.textContent = textarea.value.length ? left : "";
    counter.classList.toggle("over", left < 0);
    submit.disabled = uploading || left < 0 || (!textarea.value.trim() && !mediaUrl);
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  };

  textarea.addEventListener("input", refresh);
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !submit.disabled) submit.click();
  });

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    fileInput.value = "";
    if (!file) return;
    uploading = true; refresh();
    try {
      const form = new FormData();
      form.append("file", file);
      mediaUrl = (await api("/api/media", { method: "POST", form })).url;
      $("img", preview).src = mediaUrl;
      preview.hidden = false;
    } catch (err) {
      toast(err.message, true);
    } finally {
      uploading = false; refresh();
    }
  });

  $("button", preview).onclick = () => { mediaUrl = null; preview.hidden = true; refresh(); };

  submit.onclick = async () => {
    submit.disabled = true;
    try {
      const post = await api("/api/posts", {
        method: "POST",
        body: { content: textarea.value, media_url: mediaUrl, reply_to_id: replyTo?.id ?? null },
      });
      textarea.value = ""; mediaUrl = null; preview.hidden = true;
      toast(replyTo ? "Reply sent" : "Posted");
      onPosted?.(post);
    } catch (err) {
      toast(err.message, true);
    } finally {
      refresh();
    }
  };

  refresh();
  if (autofocus) setTimeout(() => textarea.focus());
  return el;
}

function openReplyDialog(post) {
  if (!requireLogin()) return;
  const dialog = $("#dialog");
  dialog.innerHTML = `<div class="dialog-head"><button class="back" title="Close">✕</button><h2>Reply</h2></div>`;
  const original = postCard(post, { ancestor: true });
  $$("button", original).forEach((b) => (b.disabled = true));
  $(".post-actions", original).remove();
  dialog.append(original);
  dialog.append(composer({
    placeholder: "Post your reply",
    replyTo: post,
    autofocus: true,
    onPosted: (reply) => {
      dialog.close();
      syncPost({ ...post, reply_count: post.reply_count + 1 });
      if (location.hash === `#/p/${post.id}`) route();
      else go(`#/p/${reply.id}`);
    },
  }));
  $(".back", dialog).onclick = () => dialog.close();
  dialog.showModal();
}

// --------------------------------------------------------------- list loader

// Renders pages from fetchPage(cursor) -> {items, next_cursor}, with infinite scroll.
function pagedList(container, fetchPage, renderItem, emptyHtml) {
  let cursor = null;
  let loading = false;
  let done = false;
  const sentinel = html`<div class="spinner"></div>`;
  container.append(sentinel);

  const load = async () => {
    if (loading || done) return;
    loading = true;
    try {
      const page = await fetchPage(cursor);
      if (!container.isConnected) return;
      if (cursor === null && !page.items.length) container.insertAdjacentHTML("beforeend", emptyHtml);
      for (const item of page.items) {
        const node = renderItem(item);
        if (node) container.insertBefore(node, sentinel);
      }
      cursor = page.next_cursor;
      done = !cursor;
    } catch (err) {
      toast(err.message, true);
      done = true;
    } finally {
      loading = false;
      if (done) { observer.disconnect(); sentinel.remove(); }
    }
  };

  const observer = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) load();
  }, { rootMargin: "600px" });
  observer.observe(sentinel);
  return {
    prepend(node) {
      $(".empty", container)?.remove();
      container.prepend(node);
    },
  };
}

const qs = (params) => {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined));
  return s.toString() ? `?${s}` : "";
};

// -------------------------------------------------------------------- layout

function renderNav(active) {
  const me = state.me;
  const link = (hash, key, label, icon) =>
    `<a class="nav-link${active === key ? " active" : ""}" href="${hash}">${icon}<span>${label}</span></a>`;
  $("#nav").innerHTML = `
    <a class="brand" href="#/"><span>L</span><span class="brand-text">ifeFeed</span></a>
    ${me ? link("#/", "home", "Home", icons.home) : ""}
    ${link("#/explore", "explore", "Explore", icons.explore)}
    ${me ? link(`#/u/${esc(me.username)}`, "profile", "Profile", icons.profile) : link("#/login", "login", "Log in", icons.login)}
    <div class="nav-spacer"></div>
    ${me ? `<button class="nav-user" title="Log out">${avatar(me)}
      <div class="names"><div class="name">${esc(me.display_name)}</div><span class="handle">@${esc(me.username)} · Log out</span></div></button>` : ""}`;
  const logout = $(".nav-user", $("#nav"));
  if (logout) logout.onclick = () => {
    if (!confirm("Log out of LifeFeed?")) return;
    setSession(null);
    toast("Logged out");
    go("#/explore");
  };
}

async function renderAside() {
  const aside = $("#aside");
  aside.innerHTML = `<div class="aside-inner">
      <input class="search" type="search" placeholder="Search people" aria-label="Search people">
      <div class="card suggestions" hidden><h2>Who to follow</h2><div class="list"></div></div>
      <div class="footer-note">LifeFeed · running locally</div>
    </div>`;
  const search = $(".search", aside);
  search.value = new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "";
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter") go(`#/search?q=${encodeURIComponent(search.value.trim())}`);
  });

  if (!state.me) return;
  try {
    const users = await api("/api/users/suggestions?limit=4");
    if (!users.length) return;
    const card = $(".suggestions", aside);
    for (const u of users) $(".list", card).append(userRow(u, { followButton: true }));
    card.hidden = false;
  } catch { /* the sidebar is optional */ }
}

function userRow(user, { followButton = false } = {}) {
  const el = html`<a class="user-row" href="#/u/${esc(user.username)}">
      ${avatar(user)}
      <div class="names"><div class="name">${esc(user.display_name)}</div>
        <span class="handle">@${esc(user.username)}</span>
        ${user.bio && !followButton ? `<div class="bio">${esc(user.bio)}</div>` : ""}</div>
    </a>`;
  if (followButton) {
    const btn = html`<button class="btn dark">Follow</button>`;
    btn.onclick = async (e) => {
      e.preventDefault();
      btn.disabled = true;
      try {
        await api(`/api/users/${user.username}/follow`, { method: "POST" });
        btn.textContent = "Following";
        btn.className = "btn outline";
        toast(`Following @${user.username}`);
      } catch (err) {
        toast(err.message, true);
        btn.disabled = false;
      }
    };
    el.append(btn);
  }
  return el;
}

function header(title, subtitle = "", { back = false } = {}) {
  return html`<div class="header"><h1>
      ${back ? '<button class="back" title="Back" onclick="history.length > 1 ? history.back() : (location.hash = \'#/\')">←</button>' : ""}
      <span>${esc(title)}${subtitle ? `<small>${esc(subtitle)}</small>` : ""}</span></h1></div>`;
}

// --------------------------------------------------------------------- pages

function homePage(main) {
  let mode = safeStorage("get", "lf_feed_mode") === "ranked" ? "ranked" : "chronological";
  const head = header("Home");
  const tabs = html`<div class="tabs">
      <button class="tab" data-mode="chronological">Latest</button>
      <button class="tab" data-mode="ranked">Top</button>
    </div>`;
  head.append(tabs);
  const list = html`<div></div>`;
  let feed;

  const load = () => {
    $$(".tab", tabs).forEach((t) => t.classList.toggle("active", t.dataset.mode === mode));
    list.replaceChildren();
    // Several people you follow may repost the same thing; show it once.
    const seen = new Set();
    feed = pagedList(
      list,
      (cursor) => api(`/api/feed${qs({ mode, cursor })}`),
      (p) => {
        const id = (p.repost_of || p).id;
        if (seen.has(id)) return null;
        seen.add(id);
        return postCard(p);
      },
      `<div class="empty"><h2>Welcome to LifeFeed!</h2>
        <p>${mode === "ranked" ? "Top shows the most-engaged posts from the last week." : "Your feed is empty."}
        Follow some people from <a class="link" href="#/explore">Explore</a> to fill it up.</p></div>`,
    );
  };

  for (const t of $$(".tab", tabs)) {
    t.onclick = () => {
      mode = t.dataset.mode;
      safeStorage("set", "lf_feed_mode", mode);
      load();
    };
  }

  main.append(head, composer({ onPosted: (p) => feed.prepend(postCard(p)) }), list);
  load();
}

function explorePage(main) {
  const list = html`<div></div>`;
  main.append(header("Explore", "Latest posts from everyone"), list);
  pagedList(
    list,
    (cursor) => api(`/api/posts${qs({ cursor })}`),
    (p) => postCard(p),
    `<div class="empty"><h2>Nothing here yet</h2><p>Be the first to post something.</p></div>`,
  );
}

async function searchPage(main, q) {
  main.append(header("Search", q ? `People matching “${q}”` : "Everyone"));
  const list = html`<div><div class="spinner"></div></div>`;
  main.append(list);
  try {
    const users = await api(`/api/users${qs({ q, limit: 50 })}`);
    list.replaceChildren(...users.map((u) => userRow(u)));
    if (!users.length) list.innerHTML = `<div class="empty"><h2>No results</h2><p>Try a different name.</p></div>`;
  } catch (err) {
    toast(err.message, true);
  }
}

async function profilePage(main, username, tab) {
  let profile;
  try {
    profile = await api(`/api/users/${encodeURIComponent(username)}`);
  } catch (err) {
    main.append(header("Profile", "", { back: true }),
      html`<div class="empty"><h2>This account doesn’t exist</h2><p>Try searching for another.</p></div>`);
    return;
  }
  const isMe = state.me?.id === profile.id;
  const base = `#/u/${esc(profile.username)}`;

  if (tab === "followers" || tab === "following") {
    main.append(header(profile.display_name, `@${profile.username}`, { back: true }));
    const tabs = html`<div class="tabs">
        <a class="tab${tab === "followers" ? " active" : ""}" href="${base}/followers">Followers</a>
        <a class="tab${tab === "following" ? " active" : ""}" href="${base}/following">Following</a>
      </div>`;
    $(".header", main).append(tabs);
    const list = html`<div></div>`;
    main.append(list);
    pagedList(
      list,
      (cursor) => api(`/api/users/${profile.username}/${tab}${qs({ cursor })}`),
      (u) => userRow(u),
      `<div class="empty"><p>${tab === "followers" ? "No followers yet." : "Not following anyone yet."}</p></div>`,
    );
    return;
  }

  main.append(header(profile.display_name, `${profile.post_count} posts`, { back: true }));
  const top = html`<div>
      <div class="banner"></div>
      <div class="profile-top">${avatar(profile, "lg")}<span class="profile-action"></span></div>
      <div class="profile-info">
        <div class="name">${esc(profile.display_name)}</div>
        <div class="handle">@${esc(profile.username)}${profile.follows_you ? '<span class="badge">Follows you</span>' : ""}</div>
        ${profile.bio ? `<div class="bio">${linkify(profile.bio)}</div>` : ""}
        <div class="muted" style="margin-top:12px">Joined ${new Date(profile.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" })}</div>
        <div class="profile-stats muted">
          <a href="${base}/following"><b>${profile.following_count}</b> Following</a>
          <a href="${base}/followers"><b class="follower-count">${profile.follower_count}</b> Followers</a>
        </div>
      </div>
      <div class="tabs">
        <a class="tab${!tab ? " active" : ""}" href="${base}">Posts</a>
        <a class="tab${tab === "replies" ? " active" : ""}" href="${base}/replies">Replies</a>
        <a class="tab${tab === "likes" ? " active" : ""}" href="${base}/likes">Likes</a>
      </div>
    </div>`;
  main.append(top);

  const action = $(".profile-action", top);
  if (isMe) {
    const btn = html`<button class="btn outline">Edit profile</button>`;
    btn.onclick = () => openEditProfile(profile);
    action.append(btn);
  } else {
    const renderFollow = () => {
      action.replaceChildren();
      const btn = profile.is_following
        ? html`<button class="btn outline following"><span>Following</span></button>`
        : html`<button class="btn dark">Follow</button>`;
      btn.onclick = async () => {
        if (!requireLogin()) return;
        btn.disabled = true;
        try {
          profile = await api(`/api/users/${profile.username}/follow`, {
            method: profile.is_following ? "DELETE" : "POST",
          });
          $(".follower-count", top).textContent = profile.follower_count;
          renderFollow();
        } catch (err) {
          toast(err.message, true);
          btn.disabled = false;
        }
      };
      action.append(btn);
    };
    renderFollow();
  }

  const list = html`<div></div>`;
  main.append(list);
  const path = tab === "likes"
    ? `/api/users/${profile.username}/likes`
    : `/api/users/${profile.username}/posts`;
  pagedList(
    list,
    (cursor) => api(`${path}${qs({ cursor, replies: tab === "replies" ? "true" : null })}`),
    (p) => postCard(p),
    `<div class="empty"><p>${tab === "likes" ? "No likes yet." : "No posts yet."}</p></div>`,
  );
}

function openEditProfile(profile) {
  const dialog = $("#dialog");
  dialog.innerHTML = `
    <div class="dialog-head"><button class="back" title="Close">✕</button><h2>Edit profile</h2>
      <button class="btn dark save">Save</button></div>
    <div class="dialog-body">
      <div class="avatar-edit"><span class="avatar-slot">${avatar(profile)}</span>
        <label class="btn outline">Change photo<input type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden></label></div>
      <label class="field"><span>Name</span><input name="display_name" maxlength="50"></label>
      <label class="field"><span>Bio</span><textarea name="bio" maxlength="160"></textarea></label>
    </div>`;
  const nameInput = $("input[name=display_name]", dialog);
  const bioInput = $("textarea[name=bio]", dialog);
  nameInput.value = profile.display_name;
  bioInput.value = profile.bio;
  let avatarUrl;

  $("input[type=file]", dialog).onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const form = new FormData();
      form.append("file", file);
      avatarUrl = (await api("/api/media", { method: "POST", form })).url;
      $(".avatar-slot", dialog).innerHTML = avatar({ ...profile, avatar_url: avatarUrl });
    } catch (err) {
      toast(err.message, true);
    }
  };
  $(".back", dialog).onclick = () => dialog.close();
  $(".save", dialog).onclick = async (e) => {
    e.target.disabled = true;
    try {
      const body = { display_name: nameInput.value, bio: bioInput.value };
      if (avatarUrl) body.avatar_url = avatarUrl;
      const updated = await api("/api/users/me", { method: "PATCH", body });
      state.me = { ...state.me, ...updated };
      dialog.close();
      toast("Profile saved");
      route();
    } catch (err) {
      toast(err.message, true);
      e.target.disabled = false;
    }
  };
  dialog.showModal();
}

async function postPage(main, id) {
  main.append(header("Post", "", { back: true }));
  const body = html`<div><div class="spinner"></div></div>`;
  main.append(body);
  let post, ancestors;
  try {
    [post, ancestors] = await Promise.all([api(`/api/posts/${id}`), api(`/api/posts/${id}/thread`)]);
  } catch (err) {
    body.innerHTML = `<div class="empty"><h2>Post not found</h2><p>It may have been deleted.</p></div>`;
    return;
  }
  if (post.repost_of) { go(`#/p/${post.repost_of.id}`); return; }

  body.replaceChildren(
    ...ancestors.map((p) => postCard(p, { ancestor: true })),
    postCard(post, { focus: true }),
  );
  const replies = html`<div></div>`;
  const list = pagedList(
    replies,
    (cursor) => api(`/api/posts/${id}/replies${qs({ cursor })}`),
    (p) => postCard(p),
    "",
  );
  if (state.me) {
    const box = composer({
      placeholder: "Post your reply",
      replyTo: post,
      onPosted: (reply) => {
        post.reply_count += 1;
        syncPost(post);
        list.prepend(postCard(reply));
      },
    });
    body.append(box);
  }
  body.append(replies);
}

function authPage(main) {
  let mode = "login";
  const el = html`<div class="auth">
      <h1></h1>
      <form>
        <label class="field"><span>Username</span><input name="username" autocomplete="username" required></label>
        <label class="field register-only"><span>Display name (optional)</span><input name="display_name" maxlength="50"></label>
        <label class="field"><span>Password</span><input name="password" type="password" required></label>
        <div class="form-error"></div>
        <button class="btn dark block" type="submit"></button>
      </form>
      <div class="auth-switch"></div>
      <div class="demo-hint">Loaded the demo data? Log in as <b>ada</b>, <b>grace</b>, <b>linus</b> or <b>margaret</b> with password <b>password123</b>.</div>
    </div>`;
  const form = $("form", el);
  const error = $(".form-error", el);

  const render = () => {
    const register = mode === "register";
    $("h1", el).textContent = register ? "Create your account" : "Log in to LifeFeed";
    $("button[type=submit]", el).textContent = register ? "Sign up" : "Log in";
    $(".register-only", el).hidden = !register;
    form.password.autocomplete = register ? "new-password" : "current-password";
    form.password.minLength = register ? 8 : 0;
    $(".auth-switch", el).innerHTML = register
      ? 'Have an account already? <button type="button">Log in</button>'
      : 'Don’t have an account? <button type="button">Sign up</button>';
    $(".auth-switch button", el).onclick = () => { mode = register ? "login" : "register"; error.textContent = ""; render(); };
  };

  form.onsubmit = async (e) => {
    e.preventDefault();
    error.textContent = "";
    const submit = $("button[type=submit]", el);
    submit.disabled = true;
    try {
      const body = { username: form.username.value.trim(), password: form.password.value };
      if (mode === "register") body.display_name = form.display_name.value.trim() || null;
      setSession(await api(`/api/auth/${mode}`, { method: "POST", body }));
      toast(mode === "register" ? "Welcome to LifeFeed!" : "Welcome back!");
      go("#/");
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  };

  render();
  main.append(el);
}

// -------------------------------------------------------------------- router

async function route() {
  const [path, query = ""] = location.hash.replace(/^#/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const main = $("#main");
  main.replaceChildren();
  $("#dialog").open && $("#dialog").close();
  window.scrollTo(0, 0);

  let active = "";
  if (parts.length === 0) {
    if (!state.me) { go("#/explore"); return; }
    active = "home";
    homePage(main);
  } else if (parts[0] === "explore") {
    active = "explore";
    explorePage(main);
  } else if (parts[0] === "search") {
    active = "explore";
    searchPage(main, new URLSearchParams(query).get("q") || "");
  } else if (parts[0] === "login") {
    if (state.me) { go("#/"); return; }
    active = "login";
    authPage(main);
  } else if (parts[0] === "u" && parts[1]) {
    active = state.me && parts[1].toLowerCase() === state.me.username.toLowerCase() ? "profile" : "";
    profilePage(main, decodeURIComponent(parts[1]), parts[2]);
  } else if (parts[0] === "p" && /^\d+$/.test(parts[1] || "")) {
    postPage(main, parts[1]);
  } else {
    main.append(header("Not found"), html`<div class="empty"><h2>Page not found</h2><p><a class="link" href="#/">Go home</a></p></div>`);
  }
  renderNav(active);
  renderAside();
}

async function boot() {
  if (state.token) {
    try {
      state.me = await api("/api/auth/me");
    } catch {
      setSession(null);
    }
  }
  window.addEventListener("hashchange", route);
  route();
}

boot();
