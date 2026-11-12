# DX Image Downloader - Baixador de imagens e videos de uma pagina (Windows)
# DX Labs - uso legitimo: baixe apenas midias que voce tem direito de baixar
# (seu proprio site/galeria, material com permissao, imagens livres, etc.)
# GUI em Tkinter puro + requests + BeautifulSoup para a varredura da pagina
# e yt-dlp como motor opcional para paginas de video (ex.: Instagram Reels,
# TikTok, YouTube, X, Facebook) - mesmo motor do DX Downloader.
#
# v1.0.4 - Instagram "Unable to extract data" mesmo com cookies.txt:
#   (1) yt-dlp agora imita o Chrome (impersonate, via curl_cffi ja embutido)
#   para Instagram/TikTok — sem isso o Instagram barra como robo desde 2026.07;
#   (2) nova opcao "cookies do navegador (Chrome/Firefox/Edge)": o cookies.txt
#   exportado por extensao muitas vezes nao traz os cookies de sessao, e o
#   yt-dlp lendo direto do navegador logado e mais confiavel para o Instagram.
# v1.0.3 - perfil/carrossel LISTA cada post: a busca usa yt-dlp extract_info
#   (flat) e preenche a lista com 1 item por post, em vez do placeholder unico
#   "post-perfil" da v1.0.2 — sem isso o usuario via "1 midia" num perfil cheio.
#   Se o Instagram pedir login, a lista vem vazia/erro e o app avisa cookies.txt.
# v1.0.2 - carrossel e perfil inteiro (Instagram/TikTok): post /p/ baixa todas
#   as midias do carrossel e perfil (instagram.com/<usuario>/, tiktok.com/@<usuario>)
#   baixa todos os posts via yt-dlp (noplaylist=False); precisa de cookies.txt se pedir login.
# v1.0.1 - botao Limpar (limpa link, lista e selecao para outra URL).
# v1.0.0 - primeira versao:
#  - Cola a URL de uma pagina e lista TODAS as imagens e videos encontrados
#  - Fotos: <img>, <picture>/<source>, srcset (maior versao), data-src,
#    links diretos .jpg/.png/.webp/.gif, og:image, fundo em CSS
#  - Videos: <video>/<source>, links .mp4/.mov/.webm, og:video
#  - Pagina de video (Reels etc.): baixa via yt-dlp, com cookies.txt se pedir login
#  - Filtros: tipo (Fotos/Videos/Todas), extensao, tamanho minimo, mesmo dominio,
#    ignorar imagens de interface (icones/logos)
#  - Download em lote das selecionadas, com progresso, Cancelar e log em arquivo
#  - Colar sem travar a tela (PowerShell Get-Clipboard primeiro, Win32 depois),
#    mesmo padrao do DX Downloader v1.3.0.

import os
import re
import sys
import time
import ctypes
import queue
import subprocess
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import requests

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

APP_NAME = "DX Image Downloader"
APP_VERSION = "1.0.4"

BG = "#0B0E13"
BG2 = "#151A22"
FG = "#E8ECF1"
ACCENT = "#2EC4B6"
ACCENT2 = "#E63946"
MUTED = "#8A94A6"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp", ".svg"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}

SOCIAL_VIDEO_RE = re.compile(
    r"(instagram\.com/(reel|reels|p)/|tiktok\.com/@[^/]+/video/|"
    r"(youtube\.com/watch|youtu\.be/|youtube\.com/shorts/)|"
    r"(x\.com|twitter\.com)/[^/]+/status/|facebook\.com/[^/]+/videos/|"
    r"facebook\.com/watch/)",
    re.IGNORECASE,
)

# Perfil inteiro (Instagram/TikTok): instagram.com/<usuario>/ ou tiktok.com/@<usuario>
# Carrossel ja cai no padrao acima (/p/<id>/): o yt-dlp baixa TODAS as midias
# do carrossel, nao so a primeira — por isso o noplaylist abaixo e False.
SOCIAL_PROFILE_RE = re.compile(
    r"(instagram\.com/[A-Za-z0-9._]+/?(\?.*)?$|tiktok\.com/@[A-Za-z0-9._]+/?(\?.*)?$)",
    re.IGNORECASE,
)

INTERFACE_WORDS = ("icon", "logo", "sprite", "favicon", "pixel", "tracking",
                   "1x1", "spacer", "blank", "placeholder")


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "DXImageDownloader"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = Path.home()
    return d


LOG_FILE = log_dir() / "dx-image-downloader.log"


def log_file(msg: str):
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:
        pass


# ------------------------- clipboard (mesmo padrao do DX Downloader) -------------------------

CF_UNICODETEXT = 13


def read_clipboard_text_windows(timeout_s: float = 2.0):
    if sys.platform != "win32":
        return None
    _com_ready = False
    try:
        hr = ctypes.windll.ole32.CoInitializeEx(None, 2)
        _com_ready = hr in (0, 1)
    except Exception:
        pass
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    deadline = time.monotonic() + timeout_s
    opened = False
    while time.monotonic() < deadline:
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        log_file("clipboard: OpenClipboard nao conseguiu dentro do limite")
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.c_wchar_p(ptr).value
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
        if _com_ready:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass


def read_clipboard_via_powershell(timeout_s: float = 6.0):
    if sys.platform != "win32":
        return None
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, timeout=timeout_s,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = r.stdout.decode("utf-8", errors="replace").rstrip("\r\n")
        log_file(f"powershell Get-Clipboard: rc={r.returncode} len={len(out)}")
        return out or None
    except Exception as e:
        log_file(f"powershell Get-Clipboard falhou: {e}")
        return None


def read_clipboard_text():
    txt = read_clipboard_via_powershell()
    if txt:
        return txt
    return read_clipboard_text_windows()


def default_download_dir() -> Path:
    d = Path.home() / "Downloads" / "DX Image Downloader"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = Path.home()
    return d


def bundled_ffmpeg():
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys._MEIPASS) / "ffmpeg.exe")  # type: ignore[attr-defined]
        candidates.append(Path(sys.executable).parent / "ffmpeg.exe")
    candidates.append(Path(__file__).parent / "ffmpeg.exe")
    for c in candidates:
        if c.exists():
            return str(c)
    return None


# ------------------------- extracao de midias (testavel sem GUI) -------------------------

def _clean_url(raw: str, base_url: str):
    if not raw:
        return None
    raw = raw.strip()
    if not raw or raw.startswith("data:") or raw.startswith("javascript:") or raw == "#":
        return None
    if raw.startswith("//"):
        raw = "https:" + raw
    abs_url = urljoin(base_url, raw)
    p = urlparse(abs_url)
    if p.scheme not in ("http", "https"):
        return None
    return abs_url


def _ext_of(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in IMAGE_EXTS | VIDEO_EXTS:
        if path.endswith(ext):
            return ext
    return ""


def _parse_srcset(value: str, base_url: str):
    """srcset: 'url1 300w, url2 800w' -> devolve a maior (ultima / maior largura)."""
    best = None
    best_w = -1
    for part in (value or "").split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        url = _clean_url(tokens[0], base_url)
        if not url:
            continue
        w = 0
        if len(tokens) > 1:
            m = re.match(r"(\d+)w", tokens[1])
            if m:
                w = int(m.group(1))
        if w >= best_w:
            best_w = w
            best = url
    return best


def _is_interface(url: str) -> bool:
    low = url.lower()
    return any(w in low for w in INTERFACE_WORDS)


def _to_int(value):
    try:
        return int(str(value).strip())
    except Exception:
        return None


def extract_media(html: str, base_url: str, only_same_domain: bool = False,
                  ignore_interface: bool = True, min_width: int = 0,
                  media_type: str = "all"):
    """Varre o HTML e devolve [{'url','kind','name','ext','width','height','source'}].
    kind: 'image' ou 'video'. Deduplica por URL. Nao faz rede."""
    if BeautifulSoup is None:
        raise RuntimeError("BeautifulSoup nao disponivel")
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc.lower()
    found = {}
    order = []

    def add(url, kind, source, width=None, height=None):
        if not url:
            return
        if only_same_domain and urlparse(url).netloc.lower() != base_host:
            return
        if ignore_interface and kind == "image" and _is_interface(url):
            return
        if min_width and width is not None and width < min_width:
            return
        ext = _ext_of(url)
        if kind == "image" and ext and ext not in IMAGE_EXTS:
            return
        if kind == "video" and ext and ext not in VIDEO_EXTS:
            return
        if url in found:
            prev = found[url]
            if width and not prev.get("width"):
                prev["width"] = width
            if height and not prev.get("height"):
                prev["height"] = height
            return
        name = unquote(Path(urlparse(url).path).name) or f"midia_{len(order)+1}{ext or ''}"
        item = {"url": url, "kind": kind, "name": name, "ext": ext,
                "width": width, "height": height, "source": source, "size": None}
        found[url] = item
        order.append(item)

    if media_type in ("all", "image"):
        for img in soup.find_all("img"):
            w = _to_int(img.get("width"))
            h = _to_int(img.get("height"))
            best = None
            for attr in ("srcset", "data-srcset", "data-lazy-srcset"):
                if img.get(attr):
                    best = _parse_srcset(img.get(attr), base_url)
                    if best:
                        break
            if best:
                # srcset ja deu a maior versao: nao listar o src (miniatura) junto
                add(best, "image", "img srcset", w, h)
                continue
            for attr in ("src", "data-src", "data-lazy-src", "data-original", "data-url"):
                u = _clean_url(img.get(attr) or "", base_url)
                if u:
                    add(u, "image", "img", w, h)
                    break
        for src in soup.find_all("source"):
            if src.parent and src.parent.name == "picture":
                u = _parse_srcset(src.get("srcset") or "", base_url) or _clean_url(src.get("src") or "", base_url)
                if u:
                    add(u, "image", "picture", None, None)
        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            if prop in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
                u = _clean_url(meta.get("content") or "", base_url)
                if u:
                    add(u, "image", "og:image", None, None)
        for link in soup.find_all("link", rel="image_src"):
            u = _clean_url(link.get("href") or "", base_url)
            if u:
                add(u, "image", "link", None, None)

    if media_type in ("all", "video"):
        for video in soup.find_all("video"):
            w = _to_int(video.get("width"))
            h = _to_int(video.get("height"))
            u = _clean_url(video.get("src") or "", base_url)
            if u:
                add(u, "video", "video", w, h)
            for src in video.find_all("source"):
                u2 = _clean_url(src.get("src") or "", base_url)
                if u2:
                    add(u2, "video", "video source", w, h)
            poster = _clean_url(video.get("poster") or "", base_url)
            if poster and media_type in ("all", "image"):
                add(poster, "image", "video poster", w, h)
        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            if prop in ("og:video", "og:video:url", "twitter:player:stream"):
                u = _clean_url(meta.get("content") or "", base_url)
                if u:
                    add(u, "video", "og:video", None, None)

    # Links diretos para arquivos de midia (<a href="...jpg/mp4">)
    for a in soup.find_all("a", href=True):
        u = _clean_url(a.get("href") or "", base_url)
        if not u:
            continue
        ext = _ext_of(u)
        if ext in IMAGE_EXTS and media_type in ("all", "image"):
            add(u, "image", "link", None, None)
        elif ext in VIDEO_EXTS and media_type in ("all", "video"):
            add(u, "video", "link", None, None)

    # background-image em style inline
    if media_type in ("all", "image"):
        for tag in soup.find_all(style=True):
            for m in re.finditer(r"background(?:-image)?\s*:\s*url\(['\"]?([^'\")]+)['\"]?\)",
                                 tag.get("style") or ""):
                u = _clean_url(m.group(1), base_url)
                if u:
                    add(u, "image", "css", None, None)

    return order


def is_social_video_url(url: str) -> bool:
    return bool(SOCIAL_VIDEO_RE.search(url or ""))


RESERVED_INSTAGRAM = {"explore", "reels", "reel", "p", "stories", "direct",
                      "accounts", "settings", "about", "developer", "legal"}


def is_social_profile_url(url: str) -> bool:
    """Perfil inteiro do Instagram/TikTok (sem /p/, /reel/ ou /video/ no caminho)."""
    if not url:
        return False
    if SOCIAL_VIDEO_RE.search(url):
        return False
    m = re.search(r"instagram\.com/([A-Za-z0-9._]+)/?", url.strip(), re.IGNORECASE)
    if m and m.group(1).lower() in RESERVED_INSTAGRAM:
        return False
    return bool(SOCIAL_PROFILE_RE.search(url.strip()))


def is_social_url(url: str) -> bool:
    return is_social_video_url(url) or is_social_profile_url(url)


def make_session(cookies_file: str | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*",
                      "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"})
    if cookies_file:
        try:
            import http.cookiejar
            jar = http.cookiejar.MozillaCookieJar(cookies_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            s.cookies.update(jar)  # type: ignore[arg-type]
            log_file(f"cookies.txt carregado: {cookies_file} ({len(jar)} cookies)")
        except Exception as e:
            log_file(f"cookies.txt falhou ({cookies_file}): {e}")
            raise
    return s


def fetch_page(url: str, session: requests.Session, timeout: int = 30):
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text, r.url


def sanitize_filename(name: str) -> str:
    name = unquote(name or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(" .")
    return name or "midia"


def unique_path(directory: Path, name: str) -> Path:
    name = sanitize_filename(name)
    p = directory / name
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    i = 1
    while True:
        cand = directory / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1


class CancelledError(Exception):
    pass


def download_direct(url: str, dest: Path, session: requests.Session,
                    progress_cb=None, cancel_flag=None):
    """Baixa um arquivo direto com streaming. progress_cb(downloaded, total)."""
    with session.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        # Extensao pelo Content-Type quando a URL nao tem extensao
        if not dest.suffix:
            ct = (r.headers.get("Content-Type") or "").lower()
            for ext, mime in ((".jpg", "jpeg"), (".png", "png"), (".webp", "webp"),
                              (".gif", "gif"), (".mp4", "mp4"), (".webm", "webm")):
                if mime in ct:
                    dest = dest.with_suffix(ext)
                    break
        downloaded = 0
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=256 * 1024):
                if cancel_flag and cancel_flag.is_set():
                    raise CancelledError("Cancelado pelo usuario")
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)
    return dest


def _ytdlp_auth_opts(url: str, cookies_file: str | None, cookies_browser: str | None):
    """Opcoes de autenticacao/impersonacao do yt-dlp para redes sociais.
    Instagram/TikTok exigem imitar o Chrome desde 2026.07 (curl_cffi) — sem
    impersonate o Instagram devolve 'Unable to extract data' mesmo com cookies.
    cookies do navegador sao mais confiaveis que cookies.txt: o arquivo
    exportado muitas vezes nao traz os cookies de sessao (sessionid)."""
    opts: dict = {}
    if "instagram.com" in (url or "") or "tiktok.com" in (url or ""):
        opts["impersonate"] = "chrome"
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
        log_file(f"yt-dlp: cookies do navegador {cookies_browser}")
    elif cookies_file:
        if not Path(cookies_file).exists():
            log_file(f"yt-dlp: cookies.txt NAO encontrado: {cookies_file}")
        else:
            log_file(f"yt-dlp: cookies.txt {cookies_file}")
        opts["cookiefile"] = cookies_file
    return opts


def list_social_media(url: str, cookies_file: str | None = None,
                      cookies_browser: str | None = None):
    """Lista as midias de um post/carrossel/perfil via yt-dlp, sem baixar.
    Devolve [{'url','kind','name','ext','width','height','source','size','social'}],
    1 item por post (carrossel conta como 1 post aqui; o download dele baixa
    todas as fotos/videos do carrossel). Levanta excecao se o site pedir login
    ou nao devolver nada — o chamador mostra a dica dos cookies."""
    from yt_dlp import YoutubeDL
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "extract_flat": True,
        "skip_download": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    opts.update(_ytdlp_auth_opts(url, cookies_file, cookies_browser))
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        # Sem impersonate disponivel (curl_cffi ausente): tenta sem imitar
        if "impersonat" in str(e).lower():
            log_file(f"list_social_media: impersonate falhou ({e}), tentando sem")
            opts.pop("impersonate", None)
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        else:
            raise
    if not info:
        raise RuntimeError("yt-dlp nao devolveu informacoes da pagina")
    entries = info.get("entries")
    items = []
    if entries:
        for e in entries:
            if not e:
                continue
            eid = str(e.get("id") or "")
            title = (e.get("title") or eid or "post").strip()
            page = e.get("webpage_url") or e.get("url") or url
            ext = ("." + str(e.get("ext") or "").lower()) if e.get("ext") else ""
            kind = "video"
            if ext in IMAGE_EXTS:
                kind = "image"
            name = f"{title} [{eid}]" if eid else title
            if ext and not name.lower().endswith(ext):
                name += ext
            items.append({"url": page, "kind": kind, "name": sanitize_filename(name),
                          "ext": ext, "width": None, "height": None,
                          "source": "yt-dlp", "size": None, "social": True})
        if not items:
            raise RuntimeError("yt-dlp listou 0 posts — o site pode estar pedindo login")
        return items
    # Post unico (sem entries): 1 item com a propria URL
    eid = str(info.get("id") or "")
    title = (info.get("title") or eid or "post").strip()
    ext = ("." + str(info.get("ext") or "").lower()) if info.get("ext") else ""
    kind = "image" if ext in IMAGE_EXTS else "video"
    name = f"{title} [{eid}]" if eid else title
    if ext and not name.lower().endswith(ext):
        name += ext
    return [{"url": url, "kind": kind, "name": sanitize_filename(name),
             "ext": ext, "width": None, "height": None,
             "source": "yt-dlp", "size": None, "social": True}]


def download_with_ytdlp(url: str, out_dir: str, cookies_file: str | None,
                        progress_hook, ffmpeg_path: str | None,
                        cookies_browser: str | None = None):
    """Baixa pagina de video (Reels/TikTok/YouTube etc.), carrossel ou perfil
    inteiro via yt-dlp. Devolve a lista de arquivos baixados.
    noplaylist=False de proposito: um carrossel (/p/<id>/) tem varias midias
    e um perfil tem varios posts — com True o yt-dlp baixaria so a primeira.
    Levanta a excecao original em caso de erro."""
    from yt_dlp import YoutubeDL
    opts = {
        "outtmpl": str(Path(out_dir) / "%(title)s [%(id)s].%(ext)s"),
        "noplaylist": False,
        "retries": 10,
        "socket_timeout": 30,
        "continuedl": True,
        "windowsfilenames": True,
        "format": "bv*+ba/b/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
        "writethumbnail": True,
    }
    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path
    opts.update(_ytdlp_auth_opts(url, cookies_file, cookies_browser))
    downloaded = []

    def _hook(d):
        if d.get("status") == "finished":
            downloaded.append(d.get("filename"))
        progress_hook(d)

    opts["progress_hooks"] = [_hook]
    with YoutubeDL(opts) as ydl:
        ydl.download([url])
    return downloaded


# ------------------------- GUI -------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        log_file(f"=== app iniciou v{APP_VERSION} ===")
        self.title(f"{APP_NAME}  v{APP_VERSION} — DX Labs")
        self.geometry("860x720")
        self.minsize(720, 600)
        self.configure(bg=BG)

        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_flag = threading.Event()
        self.media = []          # lista de dicts de extract_media
        self.selected = set()    # indices selecionados (posicao na lista exibida)
        self.out_dir = str(default_download_dir())
        self.cookies_file = ""
        self.cookies_browser = ""
        self.last_url = ""

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", background="#1E2530", foreground=FG, borderwidth=0, padding=6)
        style.map("TButton", background=[("active", "#2A3342")])
        style.configure("TEntry", fieldbackground=BG2, foreground=FG, borderwidth=0)
        style.configure("TCombobox", fieldbackground=BG2, foreground=FG, borderwidth=0)
        style.configure("Treeview", background=BG2, foreground=FG, fieldbackground=BG2,
                        borderwidth=0, rowheight=22)
        style.configure("Treeview.Heading", background="#1E2530", foreground=FG, borderwidth=0)
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BG2, borderwidth=0)

        pad = {"padx": 8, "pady": 4}

        tk.Label(self, text=APP_NAME, bg=BG, fg=FG, font=("Segoe UI", 16, "bold")).pack(anchor="w", **pad)
        tk.Label(self, text="Cole a URL de uma página e baixe as imagens e vídeos dela em lote.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=8)

        # URL
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", **pad)
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(row, textvariable=self.url_var, bg=BG2, fg=FG,
                                  insertbackground=FG, font=("Segoe UI", 11))
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.url_entry.bind("<Control-v>", self._on_paste)
        self.url_entry.bind("<Shift-Insert>", self._on_paste)
        tk.Button(row, text="Colar", bg="#1E2530", fg=FG, relief="flat",
                  command=self._paste).pack(side="left", padx=(6, 0))
        tk.Button(row, text="Buscar mídias", bg=ACCENT, fg="#0B0E13", relief="flat",
                  font=("Segoe UI", 11, "bold"),
                  command=self._start_scan).pack(side="left", padx=(6, 0))
        tk.Button(row, text="Limpar", bg="#1E2530", fg=FG, relief="flat",
                  command=self._clear_all).pack(side="left", padx=(6, 0))

        # Filtros
        frow = tk.Frame(self, bg=BG)
        frow.pack(fill="x", **pad)
        tk.Label(frow, text="Tipo:", bg=BG, fg=MUTED).pack(side="left")
        self.type_var = tk.StringVar(value="Todas")
        ttk.Combobox(frow, textvariable=self.type_var, values=["Todas", "Fotos", "Vídeos"],
                     width=9, state="readonly").pack(side="left", padx=(4, 12))
        tk.Label(frow, text="Largura mín.:", bg=BG, fg=MUTED).pack(side="left")
        self.minw_var = tk.StringVar(value="Sem mínimo")
        ttk.Combobox(frow, textvariable=self.minw_var,
                     values=["Sem mínimo", "200 px", "500 px", "800 px"],
                     width=11, state="readonly").pack(side="left", padx=(4, 12))
        self.same_domain_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frow, text="Só mesmo domínio", variable=self.same_domain_var,
                       bg=BG, fg=FG, selectcolor=BG2, activebackground=BG).pack(side="left")
        self.ignore_ui_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frow, text="Ignorar ícones/logos", variable=self.ignore_ui_var,
                       bg=BG, fg=FG, selectcolor=BG2, activebackground=BG).pack(side="left", padx=(8, 0))

        # Pasta + cookies
        drow = tk.Frame(self, bg=BG)
        drow.pack(fill="x", **pad)
        tk.Label(drow, text="Pasta:", bg=BG, fg=MUTED).pack(side="left")
        self.dir_var = tk.StringVar(value=self.out_dir)
        tk.Entry(drow, textvariable=self.dir_var, bg=BG2, fg=FG, width=52).pack(side="left", fill="x", expand=True, padx=(4, 0))
        tk.Button(drow, text="Trocar", bg="#1E2530", fg=FG, relief="flat",
                  command=self._choose_dir).pack(side="left", padx=(6, 0))
        tk.Button(drow, text="Abrir pasta", bg="#1E2530", fg=FG, relief="flat",
                  command=self._open_dir).pack(side="left")

        crow = tk.Frame(self, bg=BG)
        crow.pack(fill="x", **pad)
        tk.Label(crow, text="Cookies (só se a página pedir login):", bg=BG, fg=MUTED).pack(side="left")
        self.cookies_browser = ""
        self.cookies_var = tk.StringVar(value="Sem cookies (páginas públicas)")
        ttk.Combobox(crow, textvariable=self.cookies_var,
                     values=["Sem cookies (páginas públicas)", "cookies.txt",
                             "Cookies do Chrome", "Cookies do Firefox", "Cookies do Edge"],
                     width=32, state="readonly").pack(side="left", padx=(4, 6))
        self.cookies_btn = tk.Button(crow, text="Escolher cookies.txt", bg="#1E2530", fg=FG,
                                     relief="flat", command=self._choose_cookies)
        self.cookies_btn.pack(side="left")
        self.cookies_btn.pack_forget()
        self.cookies_var.trace_add("write", self._on_cookies_choice)
        tk.Label(crow, text="Instagram: prefira Cookies do Chrome (logado) — cookies.txt nem sempre traz a sessão.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))

        # Lista
        self.count_var = tk.StringVar(value="Nenhuma mídia encontrada ainda. Cole uma URL e clique em Buscar mídias.")
        tk.Label(self, textvariable=self.count_var, bg=BG, fg=MUTED).pack(anchor="w", padx=8)
        cols = ("sel", "tipo", "nome", "tamanho", "origem")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended")
        for c, w, t in (("sel", 40, "✓"), ("tipo", 70, "Tipo"), ("nome", 380, "Arquivo"),
                        ("tamanho", 100, "Tamanho"), ("origem", 130, "Origem")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c == "nome" else "center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.tree.bind("<Double-1>", self._toggle_selected)
        self.tree.bind("<space>", self._toggle_selected)

        brow = tk.Frame(self, bg=BG)
        brow.pack(fill="x", **pad)
        tk.Button(brow, text="Selecionar todas", bg="#1E2530", fg=FG, relief="flat",
                  command=self._select_all).pack(side="left")
        tk.Button(brow, text="Desmarcar todas", bg="#1E2530", fg=FG, relief="flat",
                  command=self._select_none).pack(side="left", padx=(6, 0))
        self.download_btn = tk.Button(brow, text="Baixar selecionadas", bg=ACCENT, fg="#0B0E13",
                                      relief="flat", font=("Segoe UI", 11, "bold"),
                                      command=self._start_download)
        self.download_btn.pack(side="left", padx=(12, 0))
        tk.Button(brow, text="Cancelar", bg=ACCENT2, fg="white", relief="flat",
                  command=self._cancel).pack(side="left", padx=(6, 0))

        self.progress = ttk.Progressbar(self, mode="determinate", style="Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=8, pady=(2, 0))
        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(self, textvariable=self.status_var, bg=BG, fg=MUTED).pack(anchor="w", padx=8)

        self.log_text = tk.Text(self, height=7, bg=BG2, fg=FG, font=("Consolas", 9))
        self.log_text.pack(fill="x", padx=8, pady=4)
        self.log_text.configure(state="disabled")

        tk.Label(self, text="Use apenas para mídias que você tem direito de baixar.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9, "italic")).pack(anchor="w", padx=8, pady=(0, 6))

        self.after(100, self._pump_events)

    # ---------- helpers de tela ----------
    def _log(self, msg: str):
        log_file(msg)
        self.events.put(("log", msg))

    def _set_status(self, msg: str):
        self.events.put(("status", msg))

    def _pump_events(self):
        n = 0
        while not self.events.empty() and n < 50:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            n += 1
            if kind == "log":
                self.log_text.configure(state="normal")
                self.log_text.insert("end", payload + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            elif kind == "status":
                self.status_var.set(payload)
            elif kind == "progress":
                self.progress["value"] = payload
            elif kind == "refresh":
                self._refresh_tree()
            elif kind == "count":
                self.count_var.set(payload)
        self.after(100, self._pump_events)

    def _on_cookies_choice(self, *args):
        choice = self.cookies_var.get()
        browsers = {"Cookies do Chrome": "chrome", "Cookies do Firefox": "firefox",
                    "Cookies do Edge": "edge"}
        if choice == "cookies.txt":
            self.cookies_browser = ""
            self.cookies_btn.pack(side="left")
            self._choose_cookies()
        elif choice in browsers:
            # Cookies direto do navegador logado (fecha o navegador antes? nao —
            # o yt-dlp le o banco; Chrome aberto pode travar a leitura, e o
            # erro aparece no registro; nesse caso use cookies.txt).
            self.cookies_browser = browsers[choice]
            self.cookies_file = ""
            self.cookies_btn.pack_forget()
            self._log(f"Cookies do navegador: {self.cookies_browser} (feche o navegador se der erro de leitura)")
        else:
            self.cookies_btn.pack_forget()
            self.cookies_file = ""
            self.cookies_browser = ""

    def _choose_cookies(self):
        path = filedialog.askopenfilename(title="Escolher cookies.txt",
                                          filetypes=[("cookies.txt", "*.txt"), ("Todos", "*.*")])
        if path:
            self.cookies_file = path
            self._log(f"cookies.txt: {path}")

    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir)
        if d:
            self.out_dir = d
            self.dir_var.set(d)

    def _open_dir(self):
        try:
            os.startfile(self.out_dir)  # type: ignore[attr-defined]
        except Exception:
            webbrowser.open(Path(self.out_dir).as_uri())

    def _paste(self):
        # Botao Colar: mesmo caminho do Ctrl+V, sem bloquear a tela
        self._on_paste()

    def _on_paste(self, event=None):
        # Ctrl+V / Shift+Insert: le o clipboard numa thread, nunca na tela
        self._log("Lendo a área de transferência…")
        def _read():
            txt = read_clipboard_text()
            if txt:
                cleaned = txt.strip().splitlines()[0].strip() if txt.strip() else ""
                self.after(0, lambda: self.url_var.set(cleaned))
                self._log(f"Colado: {cleaned[:80]}")
            else:
                self._log("Área de transferência vazia.")
        threading.Thread(target=_read, daemon=True).start()
        return "break"

    # ---------- lista ----------
    def _refresh_tree(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, item in enumerate(self.media):
            mark = "✔" if i in self.selected else ""
            size = item.get("size")
            size_txt = f"{size/1024:.0f} KB" if size else "—"
            tipo = "Foto" if item["kind"] == "image" else "Vídeo"
            self.tree.insert("", "end", iid=str(i),
                             values=(mark, tipo, item["name"], size_txt, item["source"]))
        sel = len(self.selected)
        self.count_var.set(f"{len(self.media)} mídias encontradas — {sel} selecionadas. "
                           "Duplo clique (ou Espaço) marca/desmarca.")

    def _toggle_selected(self, event=None):
        row = self.tree.identify_row(event.y) if event else None
        if row is None and self.tree.selection():
            row = self.tree.selection()[0]
        if row is None:
            return
        i = int(row)
        if i in self.selected:
            self.selected.discard(i)
        else:
            self.selected.add(i)
        self._refresh_tree()

    def _select_all(self):
        self.selected = set(range(len(self.media)))
        self._refresh_tree()

    def _select_none(self):
        self.selected = set()
        self._refresh_tree()

    def _min_width(self):
        v = self.minw_var.get()
        return {"200 px": 200, "500 px": 500, "800 px": 800}.get(v, 0)

    def _media_type(self):
        return {"Todas": "all", "Fotos": "image", "Vídeos": "video"}.get(self.type_var.get(), "all")

    def _clear_all(self):
        """Botao Limpar: limpa o link, a lista e a selecao para colar outra URL.
        Se houver busca/download rodando, cancela primeiro. Nao apaga arquivos
        ja baixados nem o registro."""
        self.cancel_flag.set()
        self.url_var.set("")
        self.media = []
        self.selected = set()
        self.last_url = ""
        self._refresh_tree()
        self.progress["value"] = 0
        self.count_var.set("Nenhuma mídia encontrada ainda. Cole uma URL e clique em Buscar mídias.")
        self._set_status("Pronto.")
        self._log("Limpo — pronto para outra URL.")
        self.url_entry.focus_set()

    # ---------- varredura ----------
    def _start_scan(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Cole a URL de uma página primeiro.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME, "Já há uma tarefa rodando. Aguarde ou cancele.")
            return
        self.cancel_flag.clear()
        self.last_url = url
        self.media = []
        self.selected = set()
        self._refresh_tree()
        self.progress["value"] = 0
        self._set_status("Buscando mídias…")
        self.worker = threading.Thread(target=self._scan_worker, args=(url,), daemon=True)
        self.worker.start()

    def _scan_worker(self, url: str):
        try:
            # Pagina de video (Reels etc.), carrossel ou perfil inteiro:
            # lista CADA post via yt-dlp (flat), para a lista mostrar o total
            # real — na v1.0.2 aparecia so 1 item "post-perfil" e parecia que
            # so tinha 1 video num perfil cheio.
            if is_social_url(url):
                kind = "Perfil" if is_social_profile_url(url) else "Post/vídeo"
                self._log(f"{kind} detectado: {url}")
                self._log("Listando os posts via yt-dlp (pode demorar num perfil cheio)…")
                try:
                    items = list_social_media(url, self.cookies_file or None,
                                              getattr(self, "cookies_browser", "") or None)
                except Exception as e:
                    self._log(f"Nao consegui listar os posts: {e}")
                    self._log("Dica: tente 'Cookies do Chrome' em Cookies (com o Instagram logado "
                              "no Chrome) — o cookies.txt muitas vezes nao traz a sessao. "
                              "Se usar cookies.txt, exporte de novo com o Instagram aberto e "
                              "logado, depois clique em Buscar midias de novo.")
                    self._set_status("Falha ao listar — Instagram pode estar pedindo login. Veja o registro.")
                    # Mantem o item unico como plano B: Baixar selecionadas
                    # tenta baixar o perfil/post inteiro via yt-dlp mesmo assim.
                    self.media = [{"url": url, "kind": "video", "name": "post-perfil",
                                   "ext": "", "width": None, "height": None,
                                   "source": "yt-dlp", "size": None, "social": True}]
                    self.selected = {0}
                    self.events.put(("refresh", None))
                    return
                self.media = items
                self.selected = set(range(len(items)))
                self.events.put(("refresh", None))
                self._log(f"{len(items)} posts encontrados.")
                self._set_status(f"{len(items)} posts encontrados — revise a seleção e clique em Baixar selecionadas.")
                return
            session = make_session(self.cookies_file or None)
            html, final_url = fetch_page(url, session)
            if self.cancel_flag.is_set():
                # Limpar foi clicado durante a busca: nao repovoar a lista
                self._log("Busca cancelada pelo Limpar.")
                return
            self._log(f"Página carregada: {final_url} ({len(html)} caracteres)")
            media = extract_media(html, final_url,
                                  only_same_domain=self.same_domain_var.get(),
                                  ignore_interface=self.ignore_ui_var.get(),
                                  min_width=self._min_width(),
                                  media_type=self._media_type())
            # Tamanho via HEAD (melhor esforço, sem travar a lista se falhar)
            self.media = media
            self.selected = set(range(len(media)))
            self.events.put(("refresh", None))
            self._log(f"{len(media)} mídias encontradas.")
            self._set_status(f"{len(media)} mídias encontradas — revise a seleção e clique em Baixar selecionadas.")
            # HEAD em segundo plano, so para preencher o tamanho
            def _heads():
                s = make_session(self.cookies_file or None)
                for i, item in enumerate(self.media):
                    try:
                        r = s.head(item["url"], timeout=10, allow_redirects=True)
                        if r.ok and r.headers.get("Content-Length"):
                            item["size"] = int(r.headers["Content-Length"])
                    except Exception:
                        pass
                self.events.put(("refresh", None))
            threading.Thread(target=_heads, daemon=True).start()
        except Exception as e:
            log_file(f"scan falhou: {e}")
            self._log(f"Falha ao buscar a página: {e}")
            self._set_status("Falha ao buscar a página. Veja o registro.")
            if "cookies" in str(e).lower() or "login" in str(e).lower() or "403" in str(e):
                self._log("Dica: se a página pedir login, exporte os cookies com a extensão "
                          "Get cookies.txt LOCALLY e escolha o arquivo em Cookies.")

    # ---------- download ----------
    def _start_download(self):
        if not self.media:
            messagebox.showwarning(APP_NAME, "Busque as mídias primeiro.")
            return
        if not self.selected:
            messagebox.showwarning(APP_NAME, "Selecione ao menos uma mídia na lista.")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME, "Já há uma tarefa rodando.")
            return
        self.cancel_flag.clear()
        self.out_dir = self.dir_var.get().strip() or str(default_download_dir())
        Path(self.out_dir).mkdir(parents=True, exist_ok=True)
        items = [self.media[i] for i in sorted(self.selected)]
        self.worker = threading.Thread(target=self._download_worker, args=(items,), daemon=True)
        self.worker.start()

    def _download_worker(self, items):
        # Subpasta com o nome da pagina (titulo/host + data), para nao misturar lotes
        host = urlparse(self.last_url).netloc.replace("www.", "") if self.last_url else "midias"
        sub = Path(self.out_dir) / f"{sanitize_filename(host)}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        try:
            sub.mkdir(parents=True, exist_ok=True)
        except Exception:
            sub = Path(self.out_dir)
        total = len(items)
        done = 0
        failed = []
        session = make_session(self.cookies_file or None)
        ffmpeg = bundled_ffmpeg()
        for idx, item in enumerate(items):
            if self.cancel_flag.is_set():
                self._log("Download cancelado.")
                break
            self._set_status(f"Baixando {idx+1}/{total}: {item['name']}")
            try:
                if item.get("social"):
                    def _hook(d):
                        if d.get("status") == "downloading":
                            dl = d.get("downloaded_bytes") or 0
                            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                            if tot:
                                self.events.put(("progress", (idx + dl / tot) / total * 100))
                    files = download_with_ytdlp(item["url"], str(sub), self.cookies_file or None,
                                                _hook, ffmpeg,
                                                getattr(self, "cookies_browser", "") or None)
                    self._log(f"Vídeo baixado: {files}")
                else:
                    name = sanitize_filename(item["name"])
                    if not Path(name).suffix and item.get("ext"):
                        name += item["ext"]
                    dest = unique_path(sub, name)
                    def _prog(downloaded, total_bytes):
                        if total_bytes:
                            self.events.put(("progress", (idx + downloaded / total_bytes) / total * 100))
                    dest = download_direct(item["url"], dest, session, _prog, self.cancel_flag)
                    self._log(f"Baixado: {dest.name}")
                done += 1
            except CancelledError:
                self._log("Download cancelado.")
                break
            except Exception as e:
                failed.append(item["name"])
                self._log(f"Falhou {item['name']}: {e}")
            self.events.put(("progress", (idx + 1) / total * 100))
        self._set_status(f"Concluído: {done} de {total} baixados em {sub}."
                         + (f" Falhas: {len(failed)}." if failed else ""))
        self._log(f"Concluído: {done}/{total} em {sub}")
        if done:
            self.events.put(("status", f"Concluído: {done} de {total} baixados em {sub}."))

    def _cancel(self):
        self.cancel_flag.set()
        self._log("Cancelando…")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
