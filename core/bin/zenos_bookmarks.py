"""ZENOS Browser bookmarks: one JSON file, two roots (Bookmarks bar, Other bookmarks), folders nest.
Import/export use the Netscape bookmark file format that every browser reads and writes."""
import os, json, time, secrets, html
from html.parser import HTMLParser

PATH = os.path.expanduser("~/.config/zenos/bookmarks.json")
ROOTS = ("bar", "other")
SAFE_SCHEMES = ("http://", "https://")       # no javascript:/data:/file: bookmarks (a bookmark must never run code)


def _id():
    return "b" + secrets.token_hex(5)


def _empty():
    return {"version": 1,
            "bar": {"id": "bar", "type": "folder", "title": "Bookmarks bar", "children": []},
            "other": {"id": "other", "type": "folder", "title": "Other bookmarks", "children": []}}


def load():
    try:
        with open(PATH) as f:
            d = json.load(f)
        for r in ROOTS:
            d.setdefault(r, _empty()[r])
        return d
    except Exception:
        return _empty()


def save(d):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def clean_url(u):
    u = (u or "").strip()
    if not u.startswith(SAFE_SCHEMES):
        raise ValueError("Bookmarks can only hold web addresses (https://…).")
    return u[:4000]


def walk(d):
    def rec(node, parent):
        yield node, parent
        for c in node.get("children", []):
            yield from rec(c, node)
    for r in ROOTS:
        yield from rec(d[r], None)


def find(d, nid):
    for n, p in walk(d):
        if n["id"] == nid:
            return n, p
    raise KeyError("That bookmark no longer exists.")


def find_url(d, url):
    for n, _ in walk(d):
        if n.get("type") == "url" and n.get("url") == url:
            return n
    return None


def path_of(d, nid):
    """folder titles from the root down to the item's parent"""
    out = []
    n, p = find(d, nid)
    while p is not None:
        out.insert(0, p["title"])
        p = find(d, p["id"])[1]
    return out


def folders(d):
    """flat list for pickers: [{id, title, depth}]"""
    out = []
    def rec(node, depth):
        out.append({"id": node["id"], "title": node["title"], "depth": depth})
        for c in node.get("children", []):
            if c["type"] == "folder":
                rec(c, depth + 1)
    for r in ROOTS:
        rec(d[r], 0)
    return out


def add(d, parent_id, title, url=None, kind="url", index=None):
    parent, _ = find(d, parent_id or "bar")
    if parent["type"] != "folder":
        raise ValueError("Choose a folder.")
    node = {"id": _id(), "type": kind, "title": (title or "").strip()[:300], "added": int(time.time())}
    if kind == "url":
        node["url"] = clean_url(url)
        node["title"] = node["title"] or node["url"]
    else:
        node["children"] = []
        node["title"] = node["title"] or "New folder"
    ch = parent["children"]
    ch.insert(len(ch) if index is None else max(0, min(len(ch), int(index))), node)
    return node


def update(d, nid, title=None, url=None):
    n, _ = find(d, nid)
    if title is not None and nid not in ROOTS:
        n["title"] = title.strip()[:300] or n["title"]
    if url is not None and n["type"] == "url":
        n["url"] = clean_url(url)
    return n


def _inside(node, nid):
    return any(c["id"] == nid or _inside(c, nid) for c in node.get("children", []))


def move(d, nid, parent_id, index=None):
    if nid in ROOTS:
        raise ValueError("This folder cannot be moved.")
    n, old = find(d, nid)
    dest, _ = find(d, parent_id)
    if dest["type"] != "folder" or dest["id"] == nid or _inside(n, dest["id"]):
        raise ValueError("A folder cannot go inside itself.")
    i_old = old["children"].index(n)
    old["children"].pop(i_old)
    ch = dest["children"]
    if index is None:
        index = len(ch)
    index = int(index)
    if old is dest and index > i_old:
        index -= 1
    ch.insert(max(0, min(len(ch), index)), n)
    return n


def remove(d, nid):
    if nid in ROOTS:
        raise ValueError("This folder cannot be deleted.")
    n, p = find(d, nid)
    i = p["children"].index(n)
    p["children"].pop(i)
    return {"node": n, "parent": p["id"], "index": i}


def restore(d, node, parent_id, index):
    """undo a delete: put the same item (with its children) back where it was"""
    def check(n):
        if n.get("type") == "url":
            n["url"] = clean_url(n.get("url"))
        elif n.get("type") == "folder":
            n.setdefault("children", [])
            for c in n["children"]:
                check(c)
        else:
            raise ValueError("Not a bookmark.")
    check(node)
    for _, _p in walk(d):
        pass
    try:
        find(d, node["id"])
        raise ValueError("Already restored.")
    except KeyError:
        pass
    try:
        parent, _ = find(d, parent_id)
    except KeyError:
        parent = d["other"]
    ch = parent["children"]
    ch.insert(max(0, min(len(ch), int(index or 0))), node)
    return node


# ---------- Netscape bookmark file ----------
def export_html(d):
    e = lambda s: html.escape(s or "", quote=True)
    out = ["<!DOCTYPE NETSCAPE-Bookmark-file-1>",
           '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
           "<TITLE>Bookmarks</TITLE>", "<H1>Bookmarks</H1>", "<DL><p>"]
    def rec(node, ind):
        for c in node["children"]:
            if c["type"] == "folder":
                extra = ' PERSONAL_TOOLBAR_FOLDER="true"' if c is d["bar"] else ""
                out.append(f'{ind}<DT><H3 ADD_DATE="{c.get("added", 0)}"{extra}>{e(c["title"])}</H3>')
                out.append(f"{ind}<DL><p>"); rec(c, ind + "    "); out.append(f"{ind}</DL><p>")
            else:
                out.append(f'{ind}<DT><A HREF="{e(c["url"])}" ADD_DATE="{c.get("added", 0)}">{e(c["title"])}</A>')
    out.append('    <DT><H3 PERSONAL_TOOLBAR_FOLDER="true">Bookmarks bar</H3>')
    out.append("    <DL><p>"); rec(d["bar"], "        "); out.append("    </DL><p>")
    rec(d["other"], "    ")
    out.append("</DL><p>")
    return "\n".join(out) + "\n"


class _P(HTMLParser):
    def __init__(self, root):
        super().__init__(convert_charrefs=True)
        self.stack = [root]; self.pending = None; self.cur = None; self.buf = ""; self.count = 0; self.skipped = 0
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h3":
            self.cur = ("folder", a); self.buf = ""
        elif tag == "a":
            self.cur = ("url", a); self.buf = ""
        elif tag == "dl":
            self.depth += 1
            if self.pending is not None:
                self.stack.append(self.pending); self.pending = None
            elif self.depth > 1:
                self.stack.append(self.stack[-1])     # keep push/pop balanced for odd files

    def handle_endtag(self, tag):
        if tag in ("h3", "a") and self.cur:
            kind, a = self.cur; title = self.buf.strip(); self.cur = None
            parent = self.stack[-1]
            if kind == "folder":
                node = {"id": _id(), "type": "folder", "title": title[:300] or "Folder", "children": [], "added": int(time.time())}
                parent["children"].append(node); self.pending = node
            else:
                href = (a.get("href") or "").strip()
                if href.startswith(SAFE_SCHEMES):
                    parent["children"].append({"id": _id(), "type": "url", "title": title[:300] or href, "url": href[:4000], "added": int(time.time())})
                    self.count += 1
                else:
                    self.skipped += 1
        elif tag == "dl":
            self.depth -= 1
            if len(self.stack) > 1:
                self.stack.pop()

    def handle_data(self, data):
        if self.cur:
            self.buf += data


def import_html(d, text):
    folder = {"id": _id(), "type": "folder", "title": "Imported " + time.strftime("%Y-%m-%d"), "children": [], "added": int(time.time())}
    p = _P(folder)
    p.feed(text)
    if not folder["children"]:
        raise ValueError("No bookmarks were found in that file.")
    d["other"]["children"].append(folder)
    return {"count": p.count, "skipped": p.skipped, "folder": folder["id"]}
