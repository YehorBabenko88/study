"""Local-only, in-memory Study web demonstration. NOT a production server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json
from study_core import LexicalItem, Anchor, build_scene, check_recall
from visual_memory import save, list_scenes, get_scene, delete_scene, svg

SAMPLE = {
    "tasse": LexicalItem("Tasse", "de", "чашка", "die", "/ˈtasə/"),
    "haus": LexicalItem("Haus", "de", "дом", "das", "/haʊs/"),
    "stuhl": LexicalItem("Stuhl", "de", "стул", "der", "/ʃtuːl/"),
}
MAX_BODY = 16384

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/study.html"):
            page = Path(__file__).with_name("study.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return self.wfile.write(page)
        if parsed.path == "/v1/mnemonics":
            return self.respond(200, {"items": list_scenes()})
        if parsed.path.startswith("/v1/mnemonics/") and parsed.path.endswith("/image"):
            sid = parsed.path.split("/")[3]
            scene = get_scene(sid)
            if scene is None:
                return self.respond(404, {"error": "not_found"})
            raw = svg(scene)
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            return self.wfile.write(raw)
        if parsed.path.startswith("/v1/mnemonics/"):
            scene = get_scene(parsed.path.split("/")[3])
            return self.respond(200, scene) if scene else self.respond(404, {"error": "not_found"})
        if parsed.path == "/health":
            return self.respond(200, {"status": "ok", "mode": "local-demo"})
        if parsed.path == "/v1/lexicon/search":
            q = parse_qs(parsed.query).get("q", [""])[0].strip().casefold()
            result = [vars(v) for v in SAMPLE.values() if q and (q in v.lemma.casefold() or q in v.translation.casefold())]
            return self.respond(200, {"items": result, "source": "hand-curated demo only"})
        return self.respond(404, {"error": "not_found"})

    def do_DELETE(self):
        if self.path.startswith("/v1/mnemonics/") and len(self.path.split("/")) == 4:
            return self.respond(200, {"deleted": delete_scene(self.path.split("/")[3])})
        return self.respond(404, {"error": "not_found"})

    def do_POST(self):
        if self.path not in ("/v1/mnemonics/preview", "/v1/mnemonics", "/v1/learning/check"):
            return self.respond(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY:
                return self.respond(413, {"error": "invalid_body_length"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            if self.path in ("/v1/mnemonics/preview", "/v1/mnemonics"):
                word = data.get("word", "")
                if not isinstance(word, str):
                    raise ValueError("word must be string")
                item = SAMPLE.get(word.casefold().strip())
                if item is None:
                    return self.respond(404, {"error": "word_not_in_demo"})
                raw_anchors = data.get("anchors")
                if not isinstance(raw_anchors, list) or not 1 <= len(raw_anchors) <= 20:
                    raise ValueError("1–20 anchors required")
                anchors = []
                for a in raw_anchors:
                    if not isinstance(a, dict):
                        raise ValueError("invalid anchor")
                    vals = [a.get(k) for k in ("sound_fragment", "object_name", "meaning_link")]
                    if not all(isinstance(v, str) and 0 < len(v.strip()) <= 200 for v in vals):
                        raise ValueError("invalid anchor fields")
                    anchors.append(Anchor(*vals))
                scene = build_scene(item, anchors)
                if self.path == "/v1/mnemonics":
                    scene = save(scene)
                    scene["image_url"] = "/v1/mnemonics/" + scene["scene_id"] + "/image"
                return self.respond(200, scene)
            expected, response = data.get("expected"), data.get("response")
            if not isinstance(expected, str) or not isinstance(response, str) or max(len(expected), len(response)) > 200:
                raise ValueError("invalid recall fields")
            # A real assessment must retrieve the expected answer from a trusted server-side item ID.
            return self.respond(200, check_recall(expected, response, cues_shown=bool(data.get("cues_shown", False))))
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            return self.respond(400, {"error": "invalid_request", "detail": str(exc)})

def main():
    # Loopback only; no authentication or persistent storage.
    with ThreadingHTTPServer(("127.0.0.1", 8766), Handler) as server:
        print("Study demo API: http://127.0.0.1:8766")
        server.serve_forever()

if __name__ == "__main__":
    main()
