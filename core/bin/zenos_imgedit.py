"""ZENOS Images editing engine: classic image processing only (OpenCV + NumPy), no AI models.
One render() is used for both the on-screen preview (small) and the exported file (full size),
so what you see is what you save.

spec = {
  "rot": 0|90|180|270,
  "crop": [x, y, w, h] in 0..1 of the rotated image, or None,
  "adj": {"exposure": ev, "contrast": -1..1, "saturation": -1..1, "warmth": -1..1, "tint": -1..1,
          "highlights": -1..1, "shadows": -1..1},
  "focus": {"mask": id, "blur": 0..100, "feather": 0..100} or None,
  "regions": [{"shape": "rect"|"ellipse", "x","y","w","h" (0..1 of rotated image), "kind": "mosaic"|"blur", "strength": 1..100}]
}"""
import base64, secrets, threading, urllib.request
import numpy as np
import cv2

_lock = threading.Lock()
_cache = {}          # (src, rot) -> full-res BGR uint8, kept for the last few pictures
_masks = {}          # mask id -> float32 mask (0..1) at analysis size
ANALYSIS_MAX = 900


def _read(src):
    if src.startswith("http://") or src.startswith("https://"):
        data = urllib.request.urlopen(src, timeout=30).read()
    else:
        with open(src, "rb") as f:
            data = f.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("This picture format cannot be edited.")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:          # flatten transparency onto white, as a printed copy would look
        a = img[:, :, 3:4].astype(np.float32) / 255
        img = (img[:, :, :3].astype(np.float32) * a + 255 * (1 - a)).astype(np.uint8)
    return img


def _rotate(img, rot):
    rot = int(rot or 0) % 360
    return {0: img, 90: cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE), 180: cv2.rotate(img, cv2.ROTATE_180),
            270: cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)}[rot]


def base(src, rot):
    key = (src, int(rot or 0) % 360)
    with _lock:
        if key in _cache:
            return _cache[key]
    img = _rotate(_read(src), rot)
    with _lock:
        if len(_cache) > 3:
            _cache.pop(next(iter(_cache)))
        _cache[key] = img
    return img


def _fit(img, max_side):
    h, w = img.shape[:2]
    s = min(1.0, max_side / max(h, w)) if max_side else 1.0
    return (cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA) if s < 1 else img), s


def _adjust(img, a):
    if not a or not any(abs(float(v or 0)) > 1e-4 for v in a.values()):
        return img
    f = img.astype(np.float32) / 255.0
    ev = float(a.get("exposure", 0) or 0)
    if ev:
        f *= 2.0 ** ev
    L = (0.114 * f[:, :, 0] + 0.587 * f[:, :, 1] + 0.299 * f[:, :, 2])[:, :, None]
    sh, hi = float(a.get("shadows", 0) or 0), float(a.get("highlights", 0) or 0)
    if sh:
        f += sh * 0.5 * np.clip(1 - L, 0, 1) ** 2
    if hi:
        f += hi * 0.5 * np.clip(L, 0, 1) ** 2
    c = float(a.get("contrast", 0) or 0)
    if c:
        f = (f - 0.5) * (1 + c) + 0.5
    wm, tn = float(a.get("warmth", 0) or 0), float(a.get("tint", 0) or 0)
    if wm:
        f[:, :, 2] *= 1 + 0.15 * wm; f[:, :, 0] *= 1 - 0.15 * wm
    if tn:
        f[:, :, 1] *= 1 - 0.12 * tn
    s = float(a.get("saturation", 0) or 0)
    if s:
        L = (0.114 * f[:, :, 0] + 0.587 * f[:, :, 1] + 0.299 * f[:, :, 2])[:, :, None]
        f = L + (f - L) * (1 + s)
    return (np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8)


def _focus(img, fo):
    m = _masks.get(fo.get("mask")) if fo else None
    blur = float(fo.get("blur", 0) or 0) if fo else 0
    if m is None or blur <= 0:
        return img
    h, w = img.shape[:2]
    mask = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    feather = max(1, int(max(h, w) * (0.002 + 0.02 * float(fo.get("feather", 30) or 0) / 100)))
    k = max(1, feather // 2)
    mask = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
    mask = cv2.GaussianBlur(mask, (0, 0), feather)[:, :, None]
    sigma = max(0.5, max(h, w) * 0.012 * blur / 100)
    # lens-like background: blur twice (wider, softer falloff than one gaussian)
    bg = cv2.GaussianBlur(img, (0, 0), sigma)
    bg = cv2.GaussianBlur(bg, (0, 0), sigma * 0.6)
    out = img.astype(np.float32) * mask + bg.astype(np.float32) * (1 - mask)
    return np.clip(out, 0, 255).astype(np.uint8)


def _regions(img, regs):
    if not regs:
        return img
    img = img.copy()
    h, w = img.shape[:2]
    for r in regs:
        x0, y0 = int(max(0, r["x"]) * w), int(max(0, r["y"]) * h)
        x1, y1 = int(min(1, r["x"] + r["w"]) * w), int(min(1, r["y"] + r["h"]) * h)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        roi = img[y0:y1, x0:x1]
        st = max(1.0, float(r.get("strength", 50)))
        if r.get("kind") == "blur":
            fx = cv2.GaussianBlur(roi, (0, 0), max(1.0, max(h, w) * 0.0006 * st))
        else:   # mosaic: block size follows the picture size so it looks the same in preview and export
            b = max(2, int(max(h, w) * 0.0009 * st))
            sm = cv2.resize(roi, (max(1, (x1 - x0) // b), max(1, (y1 - y0) // b)), interpolation=cv2.INTER_AREA)
            fx = cv2.resize(sm, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        if r.get("shape") == "ellipse":
            m = np.zeros(roi.shape[:2], np.uint8)
            cv2.ellipse(m, ((x1 - x0) // 2, (y1 - y0) // 2), ((x1 - x0) // 2, (y1 - y0) // 2), 0, 0, 360, 255, -1)
            roi[m > 0] = fx[m > 0]
        else:
            roi[:] = fx
    return img


def render(src, spec, max_side=0, apply_crop=True):
    img, _ = _fit(base(src, spec.get("rot", 0)), max_side)
    img = _adjust(img, spec.get("adj"))
    img = _focus(img, spec.get("focus"))
    img = _regions(img, spec.get("regions"))
    c = spec.get("crop")
    if apply_crop and c and c[2] > 0 and c[3] > 0:
        h, w = img.shape[:2]
        x0, y0 = int(c[0] * w), int(c[1] * h)
        x1, y1 = max(x0 + 1, int((c[0] + c[2]) * w)), max(y0 + 1, int((c[1] + c[3]) * h))
        img = img[y0:y1, x0:x1]
    return img


def encode(img, fmt="jpeg", quality=92):
    ok, buf = cv2.imencode(".png" if fmt == "png" else ".jpg", img, [] if fmt == "png" else [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("Could not encode the picture.")
    return buf.tobytes()


def preview(src, spec, max_side=1400):
    img = render(src, spec, max_side, apply_crop=False)     # crop is drawn as an overlay while editing
    return "data:image/jpeg;base64," + base64.b64encode(encode(img, "jpeg", 88)).decode()


def segment(src, rot, rect, fg=None, bg=None, prev=None):
    """GrabCut (Rother, Kolmogorov & Blake 2004): a graph-cut on colour models; no learned model.
    rect/strokes are in 0..1 of the rotated image. Returns a mask id and a preview of the mask edge."""
    img, s = _fit(base(src, rot), ANALYSIS_MAX)
    h, w = img.shape[:2]
    if prev and prev in _masks and (fg or bg):
        m = np.where(_masks[prev] > 0.5, cv2.GC_PR_FGD, cv2.GC_PR_BGD).astype(np.uint8)
        mode = cv2.GC_INIT_WITH_MASK
    else:
        m = np.zeros((h, w), np.uint8)
        mode = cv2.GC_INIT_WITH_RECT
    r = (int(rect[0] * w), int(rect[1] * h), max(2, int(rect[2] * w)), max(2, int(rect[3] * h)))
    rad = max(3, int(max(h, w) * 0.012))
    for strokes, val in ((fg or [], cv2.GC_FGD), (bg or [], cv2.GC_BGD)):
        for st in strokes:
            pts = [(int(p[0] * w), int(p[1] * h)) for p in st]
            for a_, b_ in zip(pts, pts[1:] or pts):
                cv2.line(m, a_, b_, int(val), rad * 2)
            if strokes and (fg or bg):
                mode = cv2.GC_INIT_WITH_MASK
    if mode == cv2.GC_INIT_WITH_MASK and not (prev and prev in _masks):
        # strokes on a fresh selection: the box still says "outside is background"
        box = np.zeros_like(m); box[:] = cv2.GC_BGD
        box[r[1]:r[1] + r[3], r[0]:r[0] + r[2]] = cv2.GC_PR_FGD
        keep = (m == cv2.GC_FGD) | (m == cv2.GC_BGD)
        box[keep] = m[keep]; m = box
    bgm, fgm = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, m, r if mode == cv2.GC_INIT_WITH_RECT else None, bgm, fgm, 5, mode)
    mask = np.where((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
    # keep the largest pieces only, so stray specks do not stay sharp
    n, lab, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8))
    if n > 2:
        big = stats[1:, cv2.CC_STAT_AREA].max()
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] < big * 0.05:
                mask[lab == i] = 0
    mid = "m" + secrets.token_hex(5)
    _masks[mid] = mask
    if len(_masks) > 12:
        _masks.pop(next(iter(_masks)))
    # an overlay for the editor: subject clear, outside tinted
    ov = np.zeros((h, w, 4), np.uint8)
    ov[:, :, 0] = 239; ov[:, :, 1] = 59; ov[:, :, 2] = 155
    ov[:, :, 3] = ((1 - mask) * 110).astype(np.uint8)
    edge = cv2.morphologyEx((mask * 255).astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    ov[edge > 0] = (255, 255, 255, 230)
    ok, buf = cv2.imencode(".png", ov)
    cover = float(mask.mean())
    return {"mask": mid, "overlay": "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode(), "cover": cover}
