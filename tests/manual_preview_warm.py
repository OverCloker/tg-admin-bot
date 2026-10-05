"""Read-only local preview of the production Abstergo HTML with demo data.

Run from the bot repository with its virtual environment:
    .venv\\Scripts\\python.exe tests\\manual_preview_warm.py

This server binds to 127.0.0.1:4174 and never starts the bot or uses real keys.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.admin_api import ADMIN_PANEL_HTML, ADMIN_THEME_ASSETS, ADMIN_WARM_ICON_NAMES  # noqa: E402


BOOTSTRAP = """
<script>
localStorage.removeItem('adminApiKey');
localStorage.removeItem('adminSessionToken');
localStorage.setItem('appSettings', JSON.stringify({theme: 'warm'}));
</script>
"""

FIXTURE = """
<script>
const demoChats = [
  {chat_id: -1001, title: 'Ровнее Ровного'},
  {chat_id: -1002, title: 'Фильмы на блекаут'}
];
const demoReplies = Array.from({length: 12}, (_, index) => ({username: 'ответ' + (index + 1), text: 'Демо-ответ'}));
api = async path => {
  if (path.includes('/overview')) {
    const chat = demoChats.find(item => path.includes(String(item.chat_id))) || demoChats[0];
    return {chat, replies: demoReplies, triggers: [], permissions: {}, featurePermissions: {}};
  }
  return {};
};
selectedChatId = demoChats[0].chat_id;
// The fixture represents the owner so the production menu's permission filter
// can render every action without changing real access checks.
ownerActionsAllowed = true;
overview = {chat: demoChats[0], replies: demoReplies, triggers: [], permissions: {}, featurePermissions: {}};
document.getElementById('status').textContent = 'Демо-предпросмотр оформления · реальные данные и ключи не используются';
document.getElementById('warmGroupName').textContent = demoChats[0].title;
document.getElementById('chatTitle').textContent = demoChats[0].title;
document.getElementById('adminCard').classList.remove('hidden');
renderChats(demoChats);
showMenu();
</script>
"""

MOBILE_FRAME = b"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Abstergo Warm mobile preview</title>
<style>body{margin:0;padding:16px;display:grid;justify-content:center;background:#e9e1d9}
iframe{width:393px;height:852px;border:1px solid #b8aaa0;border-radius:20px;background:#fbf8f3}
@media(max-width:425px){body{padding:0}iframe{border:0;border-radius:0;max-width:100vw}}</style></head>
<body><iframe title="Abstergo mobile preview 393 by 852" src="/"></iframe></body></html>"""


def preview_html() -> bytes:
    page = ADMIN_PANEL_HTML.replace("  <script>\n    let selectedChatId", BOOTSTRAP + "  <script>\n    let selectedChatId", 1)
    return page.replace("</body>", FIXTURE + "</body>", 1).encode("utf-8")


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            body, content_type = preview_html(), "text/html; charset=utf-8"
        elif self.path == "/mobile":
            body, content_type = MOBILE_FRAME, "text/html; charset=utf-8"
        elif self.path.startswith("/admin/theme-assets/"):
            filename = self.path.removeprefix("/admin/theme-assets/")
            if filename in {"winter-forest.png", "autumn-courtyard.png"}:
                asset = ADMIN_THEME_ASSETS / "themes" / filename
                content_type = "image/png"
            elif filename in {"abstergo-copper-mark.png", "warm-paper-texture.png"}:
                asset = ADMIN_THEME_ASSETS / filename
                content_type = "image/png"
            elif filename.endswith(".svg") and filename[:-4] in ADMIN_WARM_ICON_NAMES:
                asset = ADMIN_THEME_ASSETS / "abstergo-warm-icons" / filename
                content_type = "image/svg+xml"
            else:
                self.send_error(404)
                return
            if not asset.is_file():
                self.send_error(404)
                return
            body = asset.read_bytes()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 4174), PreviewHandler).serve_forever()
