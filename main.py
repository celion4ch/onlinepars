"""
Stream proxy с CORS заголовками + player.html.
Для Railway.app деплоя.
"""
import asyncio
import logging
import os
from urllib.parse import unquote, quote
from aiohttp import web, ClientSession, ClientTimeout

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 8888))

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


async def handle_stream(request: web.Request):
    """Проксирует m3u8 поток, добавляя CORS заголовки."""
    m3u8_url = request.query.get("url", "")
    if not m3u8_url:
        return web.Response(text="Missing ?url=", status=400, headers=CORS_HEADERS)

    m3u8_url = unquote(m3u8_url)
    logger.info(f"Stream: {m3u8_url[:80]}...")

    try:
        timeout = ClientTimeout(total=30, sock_read=15)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(m3u8_url) as resp:
                content_type = resp.headers.get("Content-Type", "application/vnd.apple.mpegurl")
                body = await resp.read()

                # Если это m3u8 плейлист — переписываем URL сегментов через наш прокси
                if b"#EXTM3U" in body[:20]:
                    text = body.decode("utf-8", errors="replace")
                    base_url = m3u8_url.rsplit("/", 1)[0] + "/"
                    proxy_base = str(request.url.origin()) + "/stream?url="

                    new_lines = []
                    for line in text.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Это URL сегмента — проксируем
                            if line.startswith("http"):
                                seg_url = line
                            else:
                                seg_url = base_url + line
                            new_lines.append(proxy_base + quote(seg_url, safe=""))
                        else:
                            new_lines.append(line)

                    body = "\n".join(new_lines).encode("utf-8")
                    content_type = "application/vnd.apple.mpegurl"

                return web.Response(
                    body=body,
                    content_type=content_type,
                    headers=CORS_HEADERS,
                )

    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return web.Response(text=f"Proxy error: {e}", status=502, headers=CORS_HEADERS)


async def handle_player(request: web.Request):
    """Отдаём player.html."""
    player_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player.html")
    if os.path.exists(player_path):
        with open(player_path, "r", encoding="utf-8") as f:
            html = f.read()
        return web.Response(text=html, content_type="text/html", headers=CORS_HEADERS)
    return web.Response(text="player.html not found", status=404)


async def handle_cors(request: web.Request):
    return web.Response(headers=CORS_HEADERS)


async def handle_health(request: web.Request):
    return web.Response(text="OK", headers=CORS_HEADERS)


def main():
    app = web.Application()
    app.router.add_get("/stream", handle_stream)
    app.router.add_get("/player.html", handle_player)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_health)
    app.router.add_route("OPTIONS", "/{path:.*}", handle_cors)

    logger.info(f"🎬 Stream proxy on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)


if __name__ == "__main__":
    main()
