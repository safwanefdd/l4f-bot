# api.py
import os
import threading
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn


def start_api(discord_client, command_stats: "CommandStats"):
    """
    Lance l'API FastAPI dans un thread séparé et expose /api/*.
    discord_client : instance de discord.Client ou commands.Bot
    command_stats  : instance de CommandStats (voir plus bas)
    """
    app = FastAPI()
    API_KEY = os.getenv("DASHBOARD_API_KEY", "dev-key")
    PORT = int(os.getenv("API_PORT", "3001"))

    # --- middleware auth simple via x-api-key
    async def require_key(request: Request):
        key = request.headers.get("x-api-key")
        if not key or key != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/api/health")
    async def health(request: Request):
        await require_key(request)
        ping = getattr(discord_client, "latency", None)
        ping_ms = int(ping * 1000) if ping is not None else -1
        return JSONResponse({
            "status": "online" if (ping_ms >= 0 and ping_ms < 1000) else "degraded",
            "ping": ping_ms,
            "uptimeSec": int(getattr(discord_client, "_uptime_seconds", 0)),
            "servers": len(discord_client.guilds) if getattr(discord_client, "guilds", None) is not None else 0,
            "version": os.getenv("BOT_VERSION", "dev"),
        })

    @app.get("/api/commands/stats")
    async def cmd_stats(request: Request):
        await require_key(request)
        return JSONResponse(command_stats.as_list())

    @app.get("/api/guilds")
    async def guilds(request: Request):
        await require_key(request)
        data = []
        for g in getattr(discord_client, "guilds", []):
            data.append({
                "id": str(g.id),
                "name": g.name,
                "icon": str(g.icon) if getattr(g, "icon", None) else None,
                "memberCount": g.member_count if hasattr(g, "member_count") else 0,
                "joinedAt": g.me.joined_at.isoformat() if getattr(g, "me", None) and g.me.joined_at else None,
                "locale": getattr(g, "preferred_locale", None),
            })
        return JSONResponse(data)

    def _run():
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
