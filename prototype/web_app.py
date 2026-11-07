"""Local-only, in-memory Study web demonstration. NOT a production server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json
import base64
from api_security import rejection as security_rejection, csrf_token
from study_core import LexicalItem, Anchor, build_scene, check_recall
from visual_memory import save, list_scenes, get_scene, delete_scene, svg
from ai_images import configured, generate, image_bytes, import_png
from learning_memory import due_scenes, submit, stats
from skill_memory import record as record_skill, overview as skill_overview
from lexicon_store import search as lexicon_search, count as lexicon_count
from sentence_translation import translate as translate_sentence, split_words
from spatial_board import save as save_board, load as load_board, list_boards
from board_assets import store as store_board_image, read as read_board_image, recognize as recognize_page
from phonovision import analyze_wav, svg as sound_svg, metaphor
from local_speech import transcribe as offline_transcribe, align as offline_align
from pitch_shift import shift_wav
from mesh_export import mesh as export_mesh
from speech_projects import save as save_speech_project, get as get_speech_project, list_projects as list_speech_projects, save_audio as save_speech_audio, read_audio as read_speech_audio
from document_import import create as create_document, process as process_document, status as document_status, page as document_page, list_documents
from comfy_adapter import configured as comfy_configured, submit as comfy_submit, result as comfy_result, image_bytes as comfy_image, cancel as comfy_cancel, list_jobs as comfy_jobs, consume_generation_request, QueueFull

SAMPLE = {
    "tasse": LexicalItem("Tasse", "de", "чашка", "die", "/ˈtasə/"),
    "haus": LexicalItem("Haus", "de", "дом", "das", "/haʊs/"),
    "stuhl": LexicalItem("Stuhl", "de", "стул", "der", "/ʃtuːl/"),
}
MAX_BODY = 16384
MAX_BOARD_BODY = 4_000_000

class Handler(BaseHTTPRequestHandler):
    def parse_request(self):
        if not super().parse_request():
            return False
        error = security_rejection(self)
        if error:
            self.close_connection = True
            self.respond(403, {"error": error})
            return False
        return True

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
        if parsed.path == "/v1/security/bootstrap":
            return self.respond(200, {"csrf_token": csrf_token(self.server)})
        if parsed.path in ("/study-fetch.js", "/canvas-ux.js"):
            filename = {"/study-fetch.js": "study-fetch.js", "/canvas-ux.js": "canvas_ux.js"}[parsed.path]
            asset = Path(__file__).with_name(filename)
            if not asset.is_file():
                return self.respond(404, {"error": "not_found"})
            raw = asset.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return self.wfile.write(raw)
        if parsed.path == "/workspace":
            page=Path(__file__).with_name("workspace.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(page)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            return self.wfile.write(page)
        if parsed.path in ("/","/home"):
            page=Path(__file__).with_name("home.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(page)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            return self.wfile.write(page)
        if parsed.path == "/v1/documents":
            return self.respond(200,{"items":list_documents()})
        if parsed.path.startswith("/v1/documents/"):
            parts=parsed.path.strip("/").split("/")
            try:
                if len(parts)==3:
                    p=document_status(parts[2])
                    return self.respond(200,p) if p else self.respond(404,{"error":"not_found"})
                if len(parts)==5 and parts[3]=="pages":
                    p=document_page(parts[2],int(parts[4]))
                    return self.respond(200,p) if p else self.respond(404,{"error":"page_not_ready"})
            except ValueError:return self.respond(400,{"error":"invalid_document"})
        if parsed.path=="/v1/comfy/status":
            return self.respond(200,{"enabled":comfy_configured()})
        if parsed.path == "/v1/comfy/jobs":
            return self.respond(200,{"items":comfy_jobs()})
        if parsed.path.startswith("/v1/comfy/jobs/"):
            parts=parsed.path.strip("/").split("/")
            try:
                if len(parts)==4:return self.respond(200,comfy_result(parts[3]))
                if len(parts)==5 and parts[4]=="image":
                    q=parse_qs(parsed.query)
                    raw=comfy_image(parts[3],q.get("filename",[""])[0],q.get("subfolder",[""])[0])
                    self.send_response(200)
                    self.send_header("Content-Type","image/png")
                    self.send_header("Content-Length",str(len(raw)))
                    self.end_headers()
                    return self.wfile.write(raw)
            except KeyError:return self.respond(404,{"error":"job_not_found"})
            except ValueError as exc:return self.respond(400,{"error":"invalid_job","detail":str(exc)})
            except Exception:return self.respond(502,{"error":"comfy_result_unavailable"})
        if parsed.path == "/v1/speech-projects":
            return self.respond(200,{"items":list_speech_projects()})
        if parsed.path.startswith("/v1/speech-projects/"):
            parts=parsed.path.strip("/").split("/")
            if len(parts) in (3,4):
                try:
                    if len(parts)==4 and parts[3]=="audio":
                        raw=read_speech_audio(parts[2])
                        if raw is None:return self.respond(404,{"error":"not_found"})
                        self.send_response(200)
                        self.send_header("Content-Type","audio/wav")
                        self.send_header("Content-Length",str(len(raw)))
                        self.send_header("Cache-Control","no-store")
                        self.end_headers()
                        return self.wfile.write(raw)
                    if len(parts)==3:
                        p=get_speech_project(parts[2])
                        return self.respond(200,p) if p else self.respond(404,{"error":"not_found"})
                except ValueError:
                    return self.respond(400,{"error":"invalid_project_id"})
        if parsed.path.startswith("/v1/board-assets/"):
            try:
                binary=read_board_image(parsed.path.split("/")[3])
            except ValueError:
                return self.respond(400,{"error":"invalid_asset_id"})
            if binary is None:return self.respond(404,{"error":"not_found"})
            self.send_response(200)
            self.send_header("Content-Type","image/png")
            self.send_header("Content-Length",str(len(binary)))
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers()
            return self.wfile.write(binary)
        if parsed.path in ("/acoustic-studio", "/phonovision-3d", "/spectral-relief"):
            page = Path(__file__).with_name("acoustic_studio.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(page)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers()
            return self.wfile.write(page)
        if parsed.path == "/legacy-spectral-relief":
            page = Path(__file__).with_name("phonovision_3d.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(page)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers()
            return self.wfile.write(page)
        if parsed.path == "/canvas":
            page = Path(__file__).with_name("canvas.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(page)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            return self.wfile.write(page)
        if parsed.path == "/v1/boards":
            return self.respond(200,{"items":list_boards()})
        if parsed.path.startswith("/v1/boards/"):
            try:
                item=load_board(parsed.path.split("/")[3])
                return self.respond(200,item) if item else self.respond(404,{"error":"not_found"})
            except ValueError:
                return self.respond(400,{"error":"invalid_board_id"})
        if parsed.path == "/legacy-board":
            page = Path(__file__).with_name("board.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return self.wfile.write(page)
        if parsed.path == "/legacy-study":
            page = Path(__file__).with_name("study.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return self.wfile.write(page)
        if parsed.path.startswith("/v1/skills/overview/"):
            try:
                return self.respond(200, skill_overview(parsed.path.split("/")[4]))
            except KeyError:
                return self.respond(404, {"error":"scene_not_found"})
            except ValueError:
                return self.respond(400, {"error":"invalid_scene_id"})
        if parsed.path == "/v1/lexicon/stats":
            return self.respond(200, {"entries":lexicon_count(),"status":"imported_sources_only"})
        if parsed.path == "/v1/learning/due":
            return self.respond(200, {"items": due_scenes()})
        if parsed.path.startswith("/v1/learning/stats/"):
            try:
                return self.respond(200, stats(parsed.path.split("/")[4]))
            except ValueError:
                return self.respond(400, {"error": "invalid_scene_id"})
        if parsed.path == "/v1/images/provider":
            return self.respond(200, {"configured": configured(), "provider": "optional"})
        if parsed.path.startswith("/v1/mnemonics/") and parsed.path.endswith("/generated-image"):
            binary = image_bytes(parsed.path.split("/")[3])
            if binary is None:
                return self.respond(404, {"error": "image_not_found"})
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(binary)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return self.wfile.write(binary)
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
            lang = parse_qs(parsed.query).get("lang",["de"])[0]
            try:
                result = lexicon_search(q,lang=lang)
            except ValueError:
                return self.respond(400, {"error":"invalid_search"})
            if not result and lang == "de":
                result = [vars(v) for v in SAMPLE.values() if q and (q in v.lemma.casefold() or q in v.translation.casefold())]
            return self.respond(200, {"items":result,"source":"imported_lexicon_or_demo_fallback"})
        return self.respond(404, {"error": "not_found"})

    def do_DELETE(self):
        if self.path.startswith("/v1/mnemonics/") and len(self.path.split("/")) == 4:
            return self.respond(200, {"deleted": delete_scene(self.path.split("/")[3])})
        return self.respond(404, {"error": "not_found"})

    def do_PUT(self):
        if self.path=="/v1/documents":
            try:
                size=int(self.headers.get("Content-Length","0"))
                if not 1<=size<=100_000_000:return self.respond(413,{"error":"pdf_too_large"})
                return self.respond(200,create_document(self.rfile.read(size),self.headers.get("X-Document-Name","book.pdf")[:200]))
            except ValueError as exc:return self.respond(400,{"error":"invalid_pdf","detail":str(exc)})

        if self.path.startswith("/v1/speech-projects/") and self.path.endswith("/audio"):
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 1<=length<=2_000_000:return self.respond(413,{"error":"audio_too_large"})
                result=save_speech_audio(self.path.split("/")[3],self.rfile.read(length))
                return self.respond(200,result)
            except KeyError:return self.respond(404,{"error":"project_not_found"})
            except ValueError as exc:return self.respond(400,{"error":"invalid_audio","detail":str(exc)})
        if self.path in ("/v1/board-assets","/v1/ocr","/v1/phonovision/analyze","/v1/speech/transcribe","/v1/speech/align","/v1/speech/pitch-shift"):
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 1<=length<=8_000_000:
                    return self.respond(413,{"error":"invalid_image_size"})
                data=self.rfile.read(length)
                if self.path=="/v1/speech/transcribe":
                    return self.respond(200,offline_transcribe(data,self.headers.get("X-Language","de")))
                if self.path=="/v1/speech/align":
                    return self.respond(200,offline_align(data,base64.b64decode(self.headers.get("X-Transcript-B64",""),validate=True).decode("utf-8"),self.headers.get("X-Language","de")))
                if self.path=="/v1/speech/pitch-shift":
                    result=shift_wav(data,float(self.headers.get("X-Semitones","0")))
                    if result is None:
                        return self.respond(503,{"error":"librosa_not_installed"})
                    self.send_response(200)
                    self.send_header("Content-Type","audio/wav")
                    self.send_header("Content-Length",str(len(result)))
                    self.end_headers()
                    return self.wfile.write(result)
                if self.path=="/v1/phonovision/analyze":
                    result=analyze_wav(data)
                    result["svg"]=sound_svg(result)
                    return self.respond(200,result)
                if self.path=="/v1/board-assets":
                    return self.respond(200,store_board_image(data))
                lang=self.headers.get("X-OCR-Language","deu")
                return self.respond(200,recognize_page(data,lang))
            except (ValueError, UnicodeError, base64.binascii.Error) as exc:
                return self.respond(400,{"error":"invalid_input","detail":str(exc)})

        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 4 or parts[:2] != ["v1", "mnemonics"] or parts[3] != "import-image":
            return self.respond(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 8_000_000:
                return self.respond(413, {"error": "invalid_image_size"})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "image/png":
                return self.respond(415, {"error": "png_required"})
            result = import_png(parts[2], self.rfile.read(length))
            return self.respond(200, result)
        except KeyError:
            return self.respond(404, {"error": "scene_not_found"})
        except ValueError as exc:
            return self.respond(400, {"error": "invalid_png", "detail": str(exc)})
        except RuntimeError:
            return self.respond(503, {"error": "pillow_not_installed"})

    def do_POST(self):
        parts=urlparse(self.path).path.strip("/").split("/")
        if len(parts)==5 and parts[:3]==["v1","comfy","jobs"] and parts[4]=="cancel":
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<=length<=MAX_BODY:return self.respond(413,{"error":"invalid_body_length"})
                self.rfile.read(length)
                return self.respond(200,comfy_cancel(parts[3]))
            except KeyError:return self.respond(404,{"error":"job_not_found"})
            except ValueError:return self.respond(400,{"error":"invalid_job"})
        if self.path not in ("/v1/mnemonics/preview", "/v1/mnemonics", "/v1/learning/check", "/v1/learning/submit", "/v1/skills/record", "/v1/translate", "/v1/boards", "/v1/phonovision/metaphor", "/v1/phonovision/mesh", "/v1/speech-projects", "/v1/comfy/generate") and not self.path.startswith("/v1/documents/") and not (self.path.startswith("/v1/mnemonics/") and self.path.endswith("/generate")):
            return self.respond(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            max_body = MAX_BOARD_BODY if self.path in ("/v1/boards","/v1/phonovision/mesh") else MAX_BODY
            if length < 1 or length > max_body:
                return self.respond(413, {"error": "invalid_body_length"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            if self.path.startswith("/v1/documents/") and self.path.endswith("/process"):
                return self.respond(200,process_document(self.path.split("/")[3],data.get("batch",2),data.get("ocr",False),data.get("retry",False)))
            if self.path=="/v1/comfy/generate":
                if "contract_version" in data:
                    request = {k:v for k,v in data.items() if k != "request_id"}
                    return self.respond(200,consume_generation_request(request,data.get("request_id")))
                if set(data)-{"prompt","seed","request_id","width","height","steps"}:
                    raise ValueError("Unsupported generation fields")
                return self.respond(200,comfy_submit(data.get("prompt",""),data.get("seed",0),data.get("request_id"),width=data.get("width",512),height=data.get("height",512),steps=data.get("steps",20)))
            if self.path == "/v1/speech-projects":
                return self.respond(200,save_speech_project(data))
            if self.path == "/v1/phonovision/mesh":
                return self.respond(200,export_mesh(data.get("spectrogram"),data.get("shape","sphere"),
                   data.get("strength",.25),data.get("label",""),data.get("profile")))
            if self.path == "/v1/phonovision/metaphor":
                return self.respond(200,metaphor(data.get("fragment")))
            if self.path == "/v1/boards":
                result=save_board({"nodes":data.get("nodes"),"edges":data.get("edges")},
                                  board_id=data.get("id"),title=data.get("title","Моя доска"))
                return self.respond(200,result)
            if self.path == "/v1/translate":
                text = data.get("text")
                source = data.get("source","de")
                target = data.get("target","ru")
                result = translate_sentence(text,source,target)
                result["tokens"] = split_words(text)
                return self.respond(200,result)
            if self.path.startswith("/v1/mnemonics/") and self.path.endswith("/generate"):
                if not configured():
                    return self.respond(503, {"error": "image_provider_not_configured"})
                instruction = data.get("instruction", "")
                if not isinstance(instruction, str):
                    raise ValueError("instruction must be string")
                sid = self.path.split("/")[3]
                try:
                    result = generate(sid, instruction)
                except KeyError:
                    return self.respond(404, {"error": "scene_not_found"})
                except Exception:
                    return self.respond(502, {"error": "image_provider_failed", "detail": "Check provider settings and server logs"})
                return self.respond(200, result)
            if self.path in ("/v1/mnemonics/preview", "/v1/mnemonics"):
                word = data.get("word", "")
                if not isinstance(word, str):
                    raise ValueError("word must be string")
                item = SAMPLE.get(word.casefold().strip())
                if item is None:
                    translation = data.get("translation","")
                    article = data.get("article","")
                    if (not 1 <= len(word.strip()) <= 120 or not isinstance(translation,str)
                        or not 1 <= len(translation.strip()) <= 200 or
                        not isinstance(article,str) or article not in ("","der","die","das")):
                        raise ValueError("New words require a German lemma, a user-verified Russian meaning, and optional der/die/das")
                    item = LexicalItem(word.strip(),"de",translation.strip(),article,"")
                # User-authored translations are not claimed to be dictionary-verified.
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
            if self.path == "/v1/skills/record":
                try:
                    return self.respond(200, record_skill(data.get("scene_id",""),data.get("skill",""),data.get("response")))
                except KeyError:
                    return self.respond(404, {"error":"scene_not_found"})
            if self.path == "/v1/learning/submit":
                try:
                    result = submit(data.get("scene_id",""),data.get("response"))
                    return self.respond(200,result)
                except KeyError:
                    return self.respond(404, {"error":"scene_not_found"})
            expected, response = data.get("expected"), data.get("response")
            if not isinstance(expected, str) or not isinstance(response, str) or max(len(expected), len(response)) > 200:
                raise ValueError("invalid recall fields")
            # A real assessment must retrieve the expected answer from a trusted server-side item ID.
            return self.respond(200, check_recall(expected, response, cues_shown=bool(data.get("cues_shown", False))))
        except QueueFull:return self.respond(429,{"error":"comfy_queue_full","retryable":True})
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            return self.respond(400, {"error": "invalid_request", "detail": str(exc)})

def main():
    # Loopback only; no authentication or persistent storage.
    with ThreadingHTTPServer(("127.0.0.1", 8766), Handler) as server:
        print("Study demo API: http://127.0.0.1:8766")
        server.serve_forever()

if __name__ == "__main__":
    main()
