"""ZENOS cloud storage for apps: S3-compatible object storage (AWS Signature V4) and WebDAV.
Accounts live in ~/.config/zenos/cloud.json (mode 600); secrets never go back to the page.
Media is streamed through a local proxy on 127.0.0.1 so the page never sees keys and seeking (Range) works."""
import os, json, hmac, hashlib, datetime, secrets, threading, base64, urllib.request, urllib.parse, urllib.error, ssl
import xml.etree.ElementTree as ET
import mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HOME = os.path.expanduser("~")
CFG = os.path.join(HOME, ".config/zenos/cloud.json")
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


# ---------------- accounts ----------------
def _load():
    try:
        with open(CFG) as f:
            return json.load(f)
    except Exception:
        return {"accounts": []}


def _save(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    fd = os.open(CFG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f, indent=1)
    os.chmod(CFG, 0o600)


def public(a):
    """what the page may see about an account (no keys, no passwords)"""
    desc = (a.get("bucket", "") if a["type"] == "s3" else urllib.parse.urlparse(a.get("url", "")).hostname or "")
    return {"id": a["id"], "name": a["name"], "type": a["type"], "maxLevel": a.get("maxLevel", 1), "desc": desc}


def accounts():
    return [public(a) for a in _load()["accounts"]]


def get(acc_id):
    for a in _load()["accounts"]:
        if a["id"] == acc_id:
            return a
    raise KeyError("Unknown storage")


def add(spec):
    t = spec.get("type")
    a = {"id": "c" + secrets.token_hex(4), "name": (spec.get("name") or "").strip()[:60] or "Cloud storage", "type": t,
         "maxLevel": max(1, min(2, int(spec.get("maxLevel") or 1)))}   # external storage: L1-L2 only
    if t == "s3":
        ep = (spec.get("endpoint") or "").strip().rstrip("/")
        if not ep.startswith("https://") and not ep.startswith("http://"):
            ep = "https://" + ep
        a.update(endpoint=ep, region=(spec.get("region") or "us-east-1").strip(), bucket=(spec.get("bucket") or "").strip(),
                 key=(spec.get("key") or "").strip(), secret=(spec.get("secret") or "").strip(), prefix=(spec.get("prefix") or "").strip().strip("/"))
        if not (a["bucket"] and a["key"] and a["secret"]):
            raise ValueError("Endpoint, bucket, access key and secret key are needed.")
    elif t == "webdav":
        u = (spec.get("url") or "").strip()
        if not u.endswith("/"):
            u += "/"
        a.update(url=u, user=(spec.get("user") or "").strip(), password=spec.get("password") or "")
        if not u.startswith(("https://", "http://")):
            raise ValueError("Enter the WebDAV address (https://...).")
    else:
        raise ValueError("Choose S3-compatible or WebDAV.")
    ls(a, "")          # connect once before saving, so a wrong key is caught now
    d = _load(); d["accounts"].append(a); _save(d)
    return public(a)


def remove(acc_id):
    d = _load(); d["accounts"] = [a for a in d["accounts"] if a["id"] != acc_id]; _save(d)
    return True


# ---------------- S3 (Signature V4) ----------------
def _hmac(k, m):
    return hmac.new(k, m.encode(), hashlib.sha256).digest()


def _q(s, safe="-_.~"):
    return urllib.parse.quote(s, safe=safe)


def sigv4(method, url, region, service, key, secret, headers=None, payload_hash=EMPTY_SHA, now=None):
    """returns the headers to send (incl. Authorization). headers: extra headers to sign."""
    u = urllib.parse.urlsplit(url)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    amz = now.strftime("%Y%m%dT%H%M%SZ"); day = amz[:8]
    h = {"host": u.netloc, "x-amz-date": amz}
    if service == "s3":
        h["x-amz-content-sha256"] = payload_hash
    for k, v in (headers or {}).items():
        h[k.lower()] = v
    path = u.path or "/"
    cq = "&".join(f"{_q(k)}={_q(v)}" for k, v in sorted(urllib.parse.parse_qsl(u.query, keep_blank_values=True)))
    names = sorted(h)
    creq = "\n".join([method, path, cq, "".join(f"{n}:{' '.join(str(h[n]).split())}\n" for n in names), ";".join(names), payload_hash])
    scope = f"{day}/{region}/{service}/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(creq.encode()).hexdigest()])
    k = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), day), region), service), "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    h["authorization"] = f"AWS4-HMAC-SHA256 Credential={key}/{scope}, SignedHeaders={';'.join(names)}, Signature={sig}"
    return h


def _s3_url(a, key="", query=""):
    path = "/" + _q(a["bucket"]) + ("/" + "/".join(_q(p) for p in key.split("/")) if key else "/")
    return a["endpoint"] + path + ("?" + query if query else "")


def _open(req, timeout=20):
    return urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context())


def _s3_ls(a, path):
    prefix = "/".join(x for x in [a.get("prefix", ""), path.strip("/")] if x)
    prefix = prefix + "/" if prefix else ""
    out, token = [], None
    while True:
        q = {"list-type": "2", "delimiter": "/", "prefix": prefix}
        if token:
            q["continuation-token"] = token
        url = _s3_url(a, "", urllib.parse.urlencode(sorted(q.items()), quote_via=urllib.parse.quote))
        req = urllib.request.Request(url, headers=sigv4("GET", url, a["region"], "s3", a["key"], a["secret"]))
        try:
            body = _open(req).read()
        except urllib.error.HTTPError as e:
            raise ValueError(_s3_err(e))
        root = ET.fromstring(body)
        ns = {"s": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
        f = (lambda n: "s:" + n) if ns else (lambda n: n)
        for cp in root.findall(f("CommonPrefixes"), ns):
            p = cp.find(f("Prefix"), ns).text or ""
            out.append({"name": p[len(prefix):].strip("/"), "dir": True, "path": p[len(a.get('prefix', '')):].strip("/")})
        for c in root.findall(f("Contents"), ns):
            k = c.find(f("Key"), ns).text or ""
            if k == prefix:
                continue
            sz = c.find(f("Size"), ns)
            out.append({"name": k[len(prefix):], "dir": False, "size": int(sz.text) if sz is not None else 0,
                        "path": k[len(a.get('prefix', '')):].strip("/") if a.get("prefix") else k})
        t = root.find(f("NextContinuationToken"), ns)
        if t is None or not t.text:
            break
        token = t.text
    return out


def _s3_err(e):
    try:
        root = ET.fromstring(e.read())
        code = next((x.text for x in root.iter() if x.tag.endswith("Code")), "")
        msg = next((x.text for x in root.iter() if x.tag.endswith("Message")), "")
        return f"Storage refused the request ({e.code} {code}). {msg or ''}".strip()
    except Exception:
        return f"Storage refused the request ({e.code})."


# ---------------- WebDAV ----------------
def _dav_auth(a):
    if not a.get("user"):
        return {}
    return {"Authorization": "Basic " + base64.b64encode(f"{a['user']}:{a['password']}".encode()).decode()}


def _dav_url(a, path):
    return a["url"] + "/".join(_q(p) for p in path.strip("/").split("/") if p) + ("/" if path and not path.endswith("/") else "")


def _dav_ls(a, path):
    url = _dav_url(a, path.strip("/") + "/" if path.strip("/") else "")
    body = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:getcontentlength/></d:prop></d:propfind>'
    req = urllib.request.Request(url, data=body, method="PROPFIND", headers={"Depth": "1", "Content-Type": "application/xml", **_dav_auth(a)})
    try:
        root = ET.fromstring(_open(req).read())
    except urllib.error.HTTPError as e:
        raise ValueError(f"Storage refused the request ({e.code}). Check the address, user and password.")
    base = urllib.parse.urlsplit(url).path
    out = []
    for r in root.iter("{DAV:}response"):
        href = urllib.parse.unquote(urllib.parse.urlsplit(r.findtext("{DAV:}href") or "").path)
        if href.rstrip("/") == urllib.parse.unquote(base).rstrip("/"):
            continue
        is_dir = r.find(".//{DAV:}collection") is not None
        size = r.findtext(".//{DAV:}getcontentlength")
        name = href.rstrip("/").split("/")[-1]
        rel = (path.strip("/") + "/" + name).strip("/")
        out.append({"name": name, "dir": is_dir, "size": int(size) if size and size.isdigit() else 0, "path": rel})
    return out


# ---------------- common ----------------
def ls(a, path):
    items = _s3_ls(a, path) if a["type"] == "s3" else _dav_ls(a, path)
    items.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return items


def remote_request(a, path, method="GET", rng=None):
    if a["type"] == "s3":
        key = "/".join(x for x in [a.get("prefix", ""), path.strip("/")] if x)
        url = _s3_url(a, key)
        h = sigv4(method, url, a["region"], "s3", a["key"], a["secret"], payload_hash="UNSIGNED-PAYLOAD")
    else:
        url = a["url"] + "/".join(_q(p) for p in path.strip("/").split("/"))
        h = _dav_auth(a)
    if rng:
        h["Range"] = rng
    return urllib.request.Request(url, method=method, headers=h)


# ---------------- local streaming proxy ----------------
_tokens = {}
_server = None


class _H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _go(self, method):
        tok = self.path.split("/")[2] if self.path.startswith("/m/") else ""
        if tok not in _tokens:
            self.send_error(404); return
        acc_id, path = _tokens[tok]
        try:
            a = get(acc_id)
            r = _open(remote_request(a, path, method, self.headers.get("Range")), timeout=30)
            code = r.status
        except urllib.error.HTTPError as e:
            r, code = e, e.code
        except Exception:
            self.send_error(502); return
        self.send_response(code)
        # object stores often label everything "application/octet-stream"; trust the file extension then
        guess = mimetypes.guess_type(path)[0]
        rt = r.headers.get("Content-Type") or ""
        if guess and (not rt or "octet-stream" in rt or rt.split("/")[0] != guess.split("/")[0]):
            rt = guess
        if rt:
            self.send_header("Content-Type", rt)
        for k in ("Content-Length", "Content-Range", "Accept-Ranges", "Last-Modified", "ETag"):
            v = r.headers.get(k)
            if v:
                self.send_header(k, v)
        if not r.headers.get("Accept-Ranges"):
            self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if method == "GET":
            try:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        self._go("GET")

    def do_HEAD(self):
        self._go("HEAD")


def media_url(acc_id, path):
    global _server
    if _server is None:
        _server = ThreadingHTTPServer(("127.0.0.1", 0), _H)
        _server.daemon_threads = True
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    tok = secrets.token_urlsafe(16)
    _tokens[tok] = (acc_id, path)
    name = urllib.parse.quote(path.split("/")[-1])
    return f"http://127.0.0.1:{_server.server_address[1]}/m/{tok}/{name}"
