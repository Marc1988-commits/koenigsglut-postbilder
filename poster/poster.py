#!/usr/bin/env python3
"""Eigenes Posting-Tool fuer Instagram und Facebook (Meta Graph API).

Liest poster/warteschlange.json, veroeffentlicht alle freigegebenen Beitraege,
deren Zeit erreicht ist, und schreibt das Ergebnis zurueck in die Datei.
Nur Python-Standardbibliothek, keine Abhaengigkeiten.

Zugangsdaten kommen aus Umgebungsvariablen (GitHub-Secrets), je Konto mit Praefix:
  KG_ = Koenigsglut, NG = nordgrimmsaga
  <P>PAGE_ID, <P>PAGE_TOKEN, <P>IG_ID
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

API = "https://graph.facebook.com/" + os.environ.get("GRAPH_VERSION", "v23.0")
QUEUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "warteschlange.json")
PREFIX = {"koenigsglut": "KG_", "nordgrimmsaga": "NG_"}
MAX_LATE = timedelta(hours=int(os.environ.get("MAX_LATE_HOURS", "6")))


class GraphError(Exception):
    pass


def call(method, path, token, **params):
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
            msg = err.get("error_user_msg") or err.get("message") or str(e)
        except Exception:
            msg = str(e)
        raise GraphError(msg) from None


def creds(account):
    p = PREFIX.get(account)
    if not p:
        raise GraphError(f"Unbekanntes Konto: {account}")
    c = {k: os.environ.get(p + k.upper(), "").strip() for k in ("page_id", "page_token", "ig_id")}
    if not c["page_token"]:
        raise GraphError(f"Zugang fuer {account} fehlt (Secret {p}PAGE_TOKEN)")
    return c


def is_video(url):
    return url.lower().split("?")[0].endswith((".mp4", ".mov"))


# ---------- Facebook ----------
def post_facebook(c, post):
    text = post.get("facebook_text") or post.get("text", "")
    media = post.get("media", [])
    page, tok = c["page_id"], c["page_token"]
    if not page:
        raise GraphError("FB-Seiten-ID fehlt")
    if not media:
        r = call("POST", f"{page}/feed", tok, message=text)
    elif len(media) == 1 and is_video(media[0]):
        r = call("POST", f"{page}/videos", tok, file_url=media[0], description=text)
    elif len(media) == 1:
        r = call("POST", f"{page}/photos", tok, url=media[0], caption=text)
    else:
        ids = []
        for m in media:
            if is_video(m):
                raise GraphError("FB-Mehrfachbeitrag nur mit Bildern")
            ids.append(call("POST", f"{page}/photos", tok, url=m, published="false")["id"])
        params = {f"attached_media[{i}]": json.dumps({"media_fbid": x}) for i, x in enumerate(ids)}
        r = call("POST", f"{page}/feed", tok, message=text, **params)
    return r.get("post_id") or r.get("id")


# ---------- Instagram ----------
def wait_ready(cid, tok, minutes=8):
    end = time.time() + minutes * 60
    while time.time() < end:
        st = call("GET", cid, tok, fields="status_code,status").get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise GraphError(f"Instagram konnte die Datei nicht verarbeiten ({st})")
        time.sleep(10)
    raise GraphError("Instagram hat zu lange fuer die Verarbeitung gebraucht")


def post_instagram(c, post):
    ig, tok = c["ig_id"], c["page_token"]
    if not ig:
        raise GraphError("Instagram-ID fehlt")
    text = post.get("instagram_text") or post.get("text", "")
    media = post.get("media", [])
    if not media:
        raise GraphError("Instagram braucht Bild oder Video")
    if len(media) == 1 and is_video(media[0]):
        cid = call("POST", f"{ig}/media", tok, media_type="REELS", video_url=media[0],
                   caption=text, share_to_feed="true")["id"]
    elif len(media) == 1:
        cid = call("POST", f"{ig}/media", tok, image_url=media[0], caption=text)["id"]
    else:
        if len(media) > 10:
            raise GraphError("Instagram-Karussell hoechstens 10 Dateien")
        kids = []
        for m in media:
            p = {"is_carousel_item": "true"}
            p.update({"media_type": "VIDEO", "video_url": m} if is_video(m) else {"image_url": m})
            k = call("POST", f"{ig}/media", tok, **p)["id"]
            wait_ready(k, tok)
            kids.append(k)
        cid = call("POST", f"{ig}/media", tok, media_type="CAROUSEL",
                   children=",".join(kids), caption=text)["id"]
    wait_ready(cid, tok)
    r = call("POST", f"{ig}/media_publish", tok, creation_id=cid)
    try:
        link = call("GET", r["id"], tok, fields="permalink").get("permalink")
    except GraphError:
        link = None
    return link or r["id"]


# ---------- Ablauf ----------
def check_access():
    ok = True
    for account in PREFIX:
        try:
            c = creds(account)
        except GraphError as e:
            print(f"- {account}: {e}")
            ok = False
            continue
        try:
            name = call("GET", c["page_id"], c["page_token"], fields="name").get("name")
            print(f"- {account}: Facebook-Seite '{name}' ok")
        except GraphError as e:
            print(f"- {account}: Facebook-Fehler: {e}"); ok = False
        if c["ig_id"]:
            try:
                u = call("GET", c["ig_id"], c["page_token"], fields="username").get("username")
                print(f"- {account}: Instagram @{u} ok")
            except GraphError as e:
                print(f"- {account}: Instagram-Fehler: {e}"); ok = False
    return ok


def run(dry=False):
    with open(QUEUE, encoding="utf-8") as f:
        queue = json.load(f)
    now = datetime.now(timezone.utc)
    changed = False
    for post in queue:
        if post.get("status") != "freigegeben":
            continue
        when = datetime.fromisoformat(post["zeit"])
        if when.tzinfo is None:
            raise SystemExit(f"{post['id']}: Zeit ohne Zeitzone")
        if when > now:
            continue
        if now - when > MAX_LATE:
            post["status"] = "verpasst"
            post["meldung"] = f"Mehr als {MAX_LATE} zu spaet, nicht gepostet"
            changed = True
            continue
        results = post.setdefault("ergebnis", {})
        print(f"{post['id']}: {post['konto']} -> {', '.join(post['netzwerke'])}")
        if dry:
            continue
        try:
            c = creds(post["konto"])
        except GraphError as e:
            post["status"], post["meldung"] = "fehler", str(e); changed = True; continue
        failed = False
        for net in post["netzwerke"]:
            if str(results.get(net, "")).startswith(("http", "id:")):
                continue  # schon erledigt
            try:
                fn = post_facebook if net == "facebook" else post_instagram if net == "instagram" else None
                if not fn:
                    raise GraphError(f"Netzwerk {net} wird nicht unterstuetzt")
                ref = fn(c, post)
                results[net] = ref if str(ref).startswith("http") else f"id:{ref}"
                print(f"  {net}: ok {results[net]}")
            except GraphError as e:
                results[net] = f"Fehler: {e}"
                print(f"  {net}: FEHLER {e}")
                failed = True
        post["status"] = "fehler" if failed else "veroeffentlicht"
        post["gepostet_um"] = now.isoformat(timespec="seconds")
        changed = True
    if changed and not dry:
        with open(QUEUE, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return changed


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "check":
        sys.exit(0 if check_access() else 1)
    run(dry=(mode == "dry"))
