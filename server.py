#!/usr/bin/env python3
"""VideoGrab — backend Flask sobre yt-dlp.

Endpoints:
  POST /api/info      {url, playlist?}        -> metadatos de un video o de una lista
  POST /api/download  {url|items, mode, height} -> {job_id}
  GET  /api/progress/<job_id>                 -> estado del trabajo
  GET  /api/file/<job_id>                     -> archivo final (o ZIP de la lista)
  GET  /api/item/<job_id>/<idx>               -> un archivo suelto de la lista
  GET  /api/jobs                              -> historial de la sesion
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
import webbrowser
import zipfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import yt_dlp

BASE_DIR = Path(__file__).parent.resolve()
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_ITEMS = 100  # tope de videos por lista en una sola tanda

app = Flask(__name__)
CORS(app)

JOBS: dict[str, dict] = {}
LOCK = threading.Lock()

VIDEO_EXT = {"mp4", "webm", "mkv", "avi", "mov", "flv", "ogv", "m4v", "ts", "3gp"}
AUDIO_EXT = {"m4a", "mp3", "opus", "ogg", "aac", "wav", "flac"}
SUB_EXT = {".srt", ".vtt", ".ass", ".ssa", ".lrc", ".ttml", ".srv1", ".srv2", ".srv3", ".json3"}

LANG_NAMES = {
    "es": "Espa\u00f1ol",
    "es-419": "Espa\u00f1ol (Latinoam\u00e9rica)",
    "es-ES": "Espa\u00f1ol (Espa\u00f1a)",
    "en": "Ingl\u00e9s",
    "en-US": "Ingl\u00e9s (EE. UU.)",
    "en-GB": "Ingl\u00e9s (Reino Unido)",
    "pt": "Portugu\u00e9s",
    "pt-BR": "Portugu\u00e9s (Brasil)",
    "fr": "Franc\u00e9s",
    "de": "Alem\u00e1n",
    "it": "Italiano",
    "ja": "Japon\u00e9s",
    "ko": "Coreano",
    "zh": "Chino",
    "zh-Hans": "Chino (simplificado)",
    "zh-Hant": "Chino (tradicional)",
    "ru": "Ruso",
    "ar": "\u00c1rabe",
    "hi": "Hindi",
    "nl": "Neerland\u00e9s",
    "pl": "Polaco",
    "tr": "Turco",
    "sv": "Sueco",
    "da": "Dan\u00e9s",
    "no": "Noruego",
    "fi": "Finland\u00e9s",
    "el": "Griego",
    "he": "Hebreo",
    "id": "Indonesio",
    "th": "Tailand\u00e9s",
    "vi": "Vietnamita",
    "uk": "Ucraniano",
    "cs": "Checo",
    "ro": "Rumano",
    "hu": "H\u00fangaro",
    "ca": "Catal\u00e1n",
    "eu": "Euskera",
    "gl": "Gallego",
}


def lang_name(code: str, tracks: list | None = None) -> str:
    if code in LANG_NAMES:
        return LANG_NAMES[code]
    for t in tracks or []:
        if t.get("name"):
            return t["name"]
    base = code.split("-")[0]
    return f"{LANG_NAMES[base]} ({code})" if base in LANG_NAMES else code


# --------------------------------------------------------------------------- #
# utilidades
# --------------------------------------------------------------------------- #
def visitor(req) -> str:
    return req.headers.get("X-Visitor-Id", "local")


def human_size(n) -> str | None:
    if not n:
        return None
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_time(s) -> str | None:
    if s is None:
        return None
    try:
        s = int(s)
    except (TypeError, ValueError):
        return None
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def base_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "ignoreconfig": True,
        "retries": 3,
        "socket_timeout": 20,
    }


def friendly_error(msg: str) -> str:
    m = msg.lower()
    if "drm" in m or "protected" in m:
        return "El contenido está protegido con DRM y no se puede descargar."
    if "sign in" in m or "login" in m or "private" in m or "members-only" in m:
        return "El video requiere iniciar sesión o es privado."
    if "unsupported url" in m or "no video" in m:
        return "No se encontró ningún video en esa dirección."
    if "geo" in m and "restrict" in m:
        return "El video está bloqueado en esta región."
    if "unavailable" in m or "removed" in m:
        return "El video ya no está disponible."
    if "404" in m or "not found" in m:
        return "La página no existe o ya no está disponible (error 404)."
    if "403" in m or "forbidden" in m:
        return "El sitio bloqueó el acceso a ese archivo (error 403)."
    if "429" in m or "too many requests" in m:
        return "El sitio limitó las peticiones. Espera unos minutos e intenta de nuevo."
    if "timed out" in m or "timeout" in m:
        return "El sitio tardó demasiado en responder. Intenta de nuevo."
    if "captcha" in m or "bot" in m:
        return "El sitio pidió verificación anti-robot. Intenta más tarde."
    if "unable to download webpage" in m or "name or service not known" in m:
        return "No se pudo abrir esa dirección. Revisa que el enlace sea correcto."
    if "ffmpeg" in m:
        return "Falló la conversión del archivo. Intenta con otra calidad."
    clean = re.sub(r"^ERROR:\s*", "", msg).strip()
    clean = re.sub(r"^\[[^\]]+\]\s*[^:]*:\s*", "", clean)
    clean = clean.split("(caused by")[0].strip().rstrip(".")
    return (clean[:200] + ".") if clean else "No se pudo procesar el enlace."


# --------------------------------------------------------------------------- #
# /api/info
# --------------------------------------------------------------------------- #
def classify_formats(data: dict) -> tuple[list, list]:
    videos, audios = [], []
    for f in data.get("formats") or []:
        vcodec, acodec = f.get("vcodec"), f.get("acodec")
        ext = (f.get("ext") or "").lower()
        size = f.get("filesize") or f.get("filesize_approx")
        if f.get("protocol") == "mhtml" or ext == "mhtml":
            continue

        # algunos extractores no reportan codecs: inferir por extensión/altura
        if vcodec in (None, "unknown") and acodec in (None, "unknown"):
            is_video = bool(f.get("height")) or ext in VIDEO_EXT
            is_audio = not is_video and ext in AUDIO_EXT
        else:
            is_video = (vcodec or "none") != "none"
            is_audio = not is_video and (acodec or "none") != "none"
        if not is_video and not is_audio:
            continue

        row = {
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "size": human_size(size),
            "size_bytes": size,
            "note": f.get("format_note") or "",
        }
        if is_video:
            h = f.get("height")
            row["label"] = f"{h}p" if h else (ext.upper() or "original")
            row["fps"] = f.get("fps")
            row["height"] = h or 0
            videos.append(row)
        else:
            abr = f.get("abr") or 0
            row["label"] = f"{abr:.0f} kbps" if abr else (f.get("format_note") or "audio")
            row["abr"] = abr
            audios.append(row)

    best: dict[str, dict] = {}
    for v in videos:
        cur = best.get(v["label"])
        if cur is None or (v["size_bytes"] or 0) > (cur["size_bytes"] or 0):
            best[v["label"]] = v
    videos = sorted(best.values(), key=lambda v: (-v["height"], v["label"]))
    audios = sorted(audios, key=lambda a: -(a.get("abr") or 0))[:4]
    return videos, audios


def subtitle_tracks(data: dict) -> dict:
    """Pistas de subtitulos disponibles, separando manuales de automaticas."""
    def collect(raw: dict | None) -> list[dict]:
        out = []
        for code, tracks in (raw or {}).items():
            if code in ("live_chat", "rechat") or not code:
                continue
            out.append({"code": code, "name": lang_name(code, tracks)})
        return sorted(out, key=lambda s: s["name"].lower())

    manual = collect(data.get("subtitles"))
    manual_codes = {s["code"] for s in manual}
    auto = [s for s in collect(data.get("automatic_captions")) if s["code"] not in manual_codes]
    return {"manual": manual, "auto": auto}


def playlist_payload(data: dict, url: str) -> dict:
    entries, seen = [], set()
    for e in data.get("entries") or []:
        if not e:
            continue
        if e.get("_type") == "playlist":  # canales con pestañas anidadas
            for sub in e.get("entries") or []:
                if sub:
                    entries.append(sub)
            continue
        entries.append(e)

    items = []
    for e in entries:
        link = e.get("url") or e.get("webpage_url") or e.get("id")
        if not link or link in seen:
            continue
        seen.add(link)
        items.append(
            {
                "url": link,
                "title": e.get("title") or "Sin título",
                "duration": human_time(e.get("duration")),
                "thumbnail": (e.get("thumbnails") or [{}])[0].get("url") if e.get("thumbnails") else e.get("thumbnail"),
                "unavailable": bool(e.get("title") in ("[Private video]", "[Deleted video]")),
            }
        )

    return {
        "type": "playlist",
        "url": data.get("webpage_url") or url,
        "title": data.get("title") or "Lista sin título",
        "uploader": data.get("uploader") or data.get("channel") or data.get("extractor_key"),
        "site": data.get("extractor_key"),
        "total": len(items),
        "max_items": MAX_ITEMS,
        "items": items[:MAX_ITEMS],
    }


@app.post("/api/info")
def info():
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    want_playlist = bool(body.get("playlist"))
    if not url:
        return jsonify({"error": "Pega una dirección de video."}), 400
    if not re.match(r"^https?://", url):
        url = "https://" + url

    opts = base_opts() | {
        "noplaylist": not want_playlist,
        "extract_flat": "in_playlist",  # las listas se leen sin abrir cada video
        "playlistend": MAX_ITEMS,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": friendly_error(str(exc))}), 400

    if data.get("_type") == "playlist":
        payload = playlist_payload(data, url)
        if payload["total"] == 0:
            return jsonify({"error": "La lista está vacía o no se pudo leer."}), 400
        return jsonify(payload)

    videos, audios = classify_formats(data)
    return jsonify(
        {
            "type": "video",
            "url": data.get("webpage_url") or url,
            "title": data.get("title") or "Sin título",
            "uploader": data.get("uploader") or data.get("channel") or data.get("extractor_key"),
            "site": data.get("extractor_key"),
            "duration": human_time(data.get("duration")),
            "thumbnail": data.get("thumbnail"),
            "is_live": bool(data.get("is_live")),
            "in_playlist": bool(re.search(r"[?&]list=", url)),
            "videos": videos,
            "audios": audios,
            "subtitles": subtitle_tracks(data),
        }
    )


# --------------------------------------------------------------------------- #
# descarga
# --------------------------------------------------------------------------- #
def clean_subs(subs: dict | None, mode: str) -> dict | None:
    """Normaliza la peticion de subtitulos; se ignoran en modo solo audio."""
    if not subs or mode == "audio":
        return None
    langs = [str(c).strip() for c in (subs.get("langs") or []) if str(c).strip()][:12]
    if not langs:
        return None
    return {
        "langs": langs,
        "auto": bool(subs.get("auto")),
        "mode": "embed" if subs.get("mode") == "embed" else "file",
    }


def dl_opts(out_dir: Path, tmpl: str, mode: str, height: int | None, hook, subs=None) -> dict:
    opts = base_opts() | {
        "noplaylist": True,
        "outtmpl": str(out_dir / tmpl),
        "progress_hooks": [hook],
        "restrictfilenames": True,
    }
    pps: list[dict] = []
    if mode == "audio":
        opts["format"] = "bestaudio/best"
        pps.append(
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        )
    else:
        opts["format"] = (
            f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
            if height
            else "bestvideo+bestaudio/best"
        )
        opts["merge_output_format"] = "mp4"

    if subs:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = subs["auto"]
        opts["subtitleslangs"] = subs["langs"]
        opts["subtitlesformat"] = "srt/vtt/best"
        pps.append({"key": "FFmpegSubtitlesConvertor", "format": "srt"})
        if subs["mode"] == "embed":
            pps.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})

    if pps:
        opts["postprocessors"] = pps
    return opts


def split_files(out_dir: Path, prefix: str = "") -> tuple[Path | None, list[Path]]:
    """Devuelve (archivo principal, pistas de subtitulos) para un prefijo dado."""
    files = [
        p
        for p in out_dir.iterdir()
        if p.is_file()
        and not p.name.endswith(".part")
        and p.suffix != ".zip"
        and p.name.startswith(prefix)
    ]
    subs = sorted(p for p in files if p.suffix.lower() in SUB_EXT)
    media = [p for p in files if p not in subs]
    main = max(media, key=lambda p: p.stat().st_size) if media else None
    return main, subs


def make_zip(out_dir: Path, name: str, paths: list[Path]) -> Path:
    safe = re.sub(r"[^\w\-]+", "_", name)[:60].strip("_") or "videograb"
    zip_path = out_dir / f"{safe}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for p in paths:
            zf.write(p, arcname=p.name)
    return zip_path


def run_single(job_id: str, url: str, mode: str, height: int | None, subs=None):
    job = JOBS[job_id]
    out_dir = DOWNLOAD_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            with LOCK:
                job["status"] = "downloading"
                job["percent"] = round(done / total * 100, 1) if total else None
                job["speed"] = f"{human_size(d.get('speed'))}/s" if d.get("speed") else None
                job["eta"] = human_time(d.get("eta"))
                job["downloaded"] = human_size(done)
                job["total_size"] = human_size(total)
        elif d.get("status") == "finished":
            with LOCK:
                job["status"] = "processing"
                job["percent"] = 100.0
                job["speed"] = job["eta"] = None

    try:
        opts = dl_opts(out_dir, "%(title).120B.%(ext)s", mode, height, hook, subs)
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            job["status"] = "error"
            job["error"] = friendly_error(str(exc))
        return

    main, sub_files = split_files(out_dir)
    if not main:
        with LOCK:
            job["status"] = "error"
            job["error"] = "La descarga terminó sin generar archivo."
        return

    found = len(sub_files) if subs else 0
    with LOCK:
        job["subs_found"] = found

    # con los subtitulos ya incrustados, las pistas sueltas no hacen falta
    if subs and subs["mode"] == "embed":
        for p in sub_files:
            p.unlink(missing_ok=True)
        sub_files = []

    if sub_files:
        final = make_zip(out_dir, main.stem, [main, *sub_files])
        is_zip = True
    else:
        final = main
        is_zip = False

    with LOCK:
        job["status"] = "done"
        job["percent"] = 100.0
        job["filename"] = final.name
        job["path"] = str(final)
        job["size"] = human_size(final.stat().st_size)
        job["is_zip"] = is_zip


def run_playlist(job_id: str, items: list[dict], mode: str, height: int | None, subs=None):
    job = JOBS[job_id]
    out_dir = DOWNLOAD_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(items)
    paths: list[Path] = []

    for i, item in enumerate(items):
        prefix = f"{i + 1:03d}-"
        with LOCK:
            job["status"] = "downloading"
            job["index"] = i + 1
            job["current"] = item.get("title") or item["url"]
            job["items"][i]["status"] = "downloading"
        share = {"frac": 0.0}

        def hook(d, i=i, share=share):
            if d.get("status") == "downloading":
                tb = d.get("total_bytes") or d.get("total_bytes_estimate")
                if tb:
                    share["frac"] = min((d.get("downloaded_bytes") or 0) / tb, 1.0)
                with LOCK:
                    job["percent"] = round((i + share["frac"]) / total * 100, 1)
                    job["speed"] = f"{human_size(d.get('speed'))}/s" if d.get("speed") else None
                    job["eta"] = human_time(d.get("eta"))
            elif d.get("status") == "finished":
                with LOCK:
                    job["items"][i]["status"] = "processing"
                    job["speed"] = job["eta"] = None

        try:
            opts = dl_opts(out_dir, prefix + "%(title).100B.%(ext)s", mode, height, hook, subs)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(item["url"], download=True)
            got, sub_files = split_files(out_dir, prefix)
            if not got:
                raise RuntimeError("sin archivo")
            found = len(sub_files)
            if subs and subs["mode"] == "embed":
                for p in sub_files:
                    p.unlink(missing_ok=True)
                sub_files = []
            paths.append(got)
            paths.extend(sub_files)
            with LOCK:
                job["items"][i].update(
                    status="done",
                    filename=got.name,
                    size=human_size(got.stat().st_size),
                    path=str(got),
                    subs=found,
                )
                job["ok"] = job.get("ok", 0) + 1
                job["subs_found"] = job.get("subs_found", 0) + found
        except Exception as exc:  # noqa: BLE001
            with LOCK:
                job["items"][i].update(status="error", error=friendly_error(str(exc)))
                job["failed"] = job.get("failed", 0) + 1
        finally:
            with LOCK:
                job["percent"] = round((i + 1) / total * 100, 1)

    with LOCK:
        if not paths:
            job["status"] = "error"
            job["error"] = "Ningún video de la lista se pudo descargar."
            return
        job["status"] = "packing"
        job["current"] = None
        job["speed"] = job["eta"] = None

    if len(paths) == 1:
        final = paths[0]
        with LOCK:
            job["status"] = "done"
            job["filename"] = final.name
            job["path"] = str(final)
            job["size"] = human_size(final.stat().st_size)
        return

    try:
        zip_path = make_zip(out_dir, job.get("title") or "lista", paths)
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            job["status"] = "done"
            job["zip_error"] = friendly_error(str(exc))
            job["filename"] = None
        return

    with LOCK:
        job["status"] = "done"
        job["percent"] = 100.0
        job["filename"] = zip_path.name
        job["path"] = str(zip_path)
        job["size"] = human_size(zip_path.stat().st_size)
        job["is_zip"] = True


@app.post("/api/download")
def download():
    body = request.get_json(silent=True) or {}
    mode = "audio" if body.get("mode") == "audio" else "video"
    try:
        height = int(body.get("height")) or None
    except (TypeError, ValueError):
        height = None

    subs = clean_subs(body.get("subs"), mode)
    raw_items = body.get("items")
    job_id = uuid.uuid4().hex[:12]
    quality = "MP3 192 kbps" if mode == "audio" else (f"{height}p" if height else "Máxima")
    subs_info = (
        {
            "langs": subs["langs"],
            "mode": subs["mode"],
            "auto": subs["auto"],
        }
        if subs
        else None
    )

    if raw_items:
        items = [
            {"url": (it.get("url") or "").strip(), "title": it.get("title") or ""}
            for it in raw_items
            if (it.get("url") or "").strip()
        ][:MAX_ITEMS]
        if not items:
            return jsonify({"error": "No seleccionaste ningún video."}), 400
        JOBS[job_id] = {
            "id": job_id,
            "kind": "playlist",
            "visitor": visitor(request),
            "title": body.get("title") or "Lista de reproducción",
            "mode": mode,
            "quality": quality,
            "status": "queued",
            "percent": 0.0,
            "index": 0,
            "count": len(items),
            "ok": 0,
            "failed": 0,
            "subs": subs_info,
            "items": [{"title": it["title"], "status": "queued"} for it in items],
            "created": time.time(),
        }
        threading.Thread(
            target=run_playlist, args=(job_id, items, mode, height, subs), daemon=True
        ).start()
        return jsonify({"job_id": job_id})

    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Falta la dirección del video."}), 400
    JOBS[job_id] = {
        "id": job_id,
        "kind": "single",
        "visitor": visitor(request),
        "title": body.get("title") or url,
        "mode": mode,
        "quality": quality,
        "status": "queued",
        "percent": 0.0,
        "subs": subs_info,
        "created": time.time(),
    }
    threading.Thread(target=run_single, args=(job_id, url, mode, height, subs), daemon=True).start()
    return jsonify({"job_id": job_id})


def public_job(job: dict) -> dict:
    out = {k: v for k, v in job.items() if k != "path"}
    if "items" in job:
        out["items"] = [{k: v for k, v in it.items() if k != "path"} for it in job["items"]]
    return out


@app.get("/api/progress/<job_id>")
def progress(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Trabajo no encontrado."}), 404
    with LOCK:
        return jsonify(public_job(job))


@app.get("/api/jobs")
def jobs():
    vid = visitor(request)
    with LOCK:
        rows = [public_job(j) for j in JOBS.values() if j.get("visitor") == vid]
    return jsonify(sorted(rows, key=lambda j: -j["created"]))


@app.get("/api/file/<job_id>")
def file(job_id):
    job = JOBS.get(job_id)
    if not job or job.get("status") != "done" or not job.get("path"):
        return jsonify({"error": "El archivo todavía no está listo."}), 404
    return send_file(job["path"], as_attachment=True, download_name=job["filename"])


@app.get("/api/item/<job_id>/<int:idx>")
def item_file(job_id, idx):
    job = JOBS.get(job_id)
    if not job or idx >= len(job.get("items") or []):
        return jsonify({"error": "Archivo no encontrado."}), 404
    it = job["items"][idx]
    if it.get("status") != "done" or not it.get("path"):
        return jsonify({"error": "Ese archivo no está listo."}), 404
    return send_file(it["path"], as_attachment=True, download_name=it["filename"])


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "yt_dlp": yt_dlp.version.__version__, "max_items": MAX_ITEMS})


# --------------------------------------------------------------------------- #
# interfaz (para uso local: todo se sirve desde el mismo puerto)
# --------------------------------------------------------------------------- #
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def home():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/<path:filename>")
def assets(filename: str):
    return send_from_directory(STATIC_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # por omision solo escucha en tu equipo; HOST=0.0.0.0 la abre a la red local
    host = os.environ.get("HOST", "127.0.0.1")
    url = f"http://localhost:{port}"
    print(f"\n  VideoGrab en marcha: {url}")
    print("  Deja esta ventana abierta mientras uses la app. Ctrl+C para cerrarla.\n")
    if os.environ.get("VIDEOGRAB_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, threaded=True)
