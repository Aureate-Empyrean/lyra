"""Disposable real-HTTP Lyra/P1 host and loopback TMDB fixture. Never uses aetest.

Started/stopped by privacy_search.cjs; temporary synthetic data only. All provider
traffic is forced through a real loopback HTTP server, including image requests.
"""

import base64
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from lyra.app import ROOT, create_app  # noqa: E402
from lyra.library import now_iso, upsert_movie, upsert_series  # noqa: E402
from lyra.tmdb import Credential  # noqa: E402

KEY = "synthetic-gateway-" * 3
os.environ["NEXUS_RESOLVER_KEY"] = KEY
COUNTS = {"search": 0, "images": 0, "details": 0, "recommendations": 0}
MODE = {"fail": False, "slow": False}
MOVIE = {
    "id": 101,
    "title": "Synthetic Orbit",
    "original_title": "Synthetic Orbit",
    "release_date": "2026-01-01",
    "overview": "Synthetic fixture only.",
    "poster_path": "/orbit.jpg",
    "genres": [],
    "credits": {},
}
REMOTE = {**MOVIE, "id": 202, "title": "Synthetic Discovery", "poster_path": "/remote.jpg"}
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def serve(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Disposable server did not start")
        time.sleep(0.01)
    return server, thread, sock.getsockname()[1]


provider = FastAPI()


@provider.get("/{path:path}")
def provider_request(path: str):
    if path.startswith("t/p/"):
        COUNTS["images"] += 1
        return Response(PIXEL, media_type="image/png")
    if path == "3/search/multi":
        COUNTS["search"] += 1
        if MODE["slow"]:
            time.sleep(0.8)
        if MODE["fail"]:
            return Response(status_code=503)
        return {"results": [{**REMOTE, "media_type": "movie"}]}
    if path == "3/movie/202":
        COUNTS["details"] += 1
        return REMOTE
    if path in ("3/trending/all/week", "3/movie/upcoming", "3/tv/on_the_air"):
        COUNTS["recommendations"] += 1
        return {"results": [{**REMOTE, "media_type": "movie"}]}
    return Response(status_code=404)


class LoopbackProvider(httpx.BaseTransport):
    """Real socket transport; no provider request can escape to the Internet."""

    def __init__(self, port):
        self.port = port

    def handle_request(self, request):
        if request.url.host not in {"api.themoviedb.org", "image.tmdb.org"}:
            raise AssertionError("Unexpected provider destination")
        url = request.url.copy_with(scheme="http", host="127.0.0.1", port=self.port)
        with httpx.Client(trust_env=False) as client:
            result = client.get(url, headers=request.headers)
            return httpx.Response(
                result.status_code, content=result.content, headers=result.headers
            )


class NoNexus:
    def request(self, method, path, body=None, params=None):
        # Never inherit a developer's live Nexus URL/token from the environment.
        return {"references": []}


HOST = """<!doctype html><html lang="en"><title>Disposable Lyra search test</title>
<style>body{margin:0}iframe{border:0;width:100%;height:100vh}</style>
<div id="host-error" role="alert"></div><iframe id="lyra" title="Lyra" sandbox="allow-scripts" src="/lyra/"></iframe>
<script src="/navigation-sdk.js"></script><script>
const frame=document.querySelector('iframe');
const host=EmpyreanNavigation.createHost({active:()=>true,
 current:()=>({navigationRoute:new URL(location.href).searchParams.get('route')||'/'}),
 commit:()=>{},report:value=>document.querySelector('#host-error').textContent=value,
 owner:()=> 'synthetic-owner'});
host.bind(frame,'lyra');
addEventListener('popstate',()=>host.restore('traversal'));
addEventListener('message',async event=>{
 if(event.source!==frame.contentWindow)return;
 if(event.data?.channel==='empyrean-navigation-v1')return host.receive(event);
 const m=event.data;if(m?.channel!=='empyrean-v1')return;
 try{
  let result;
  if(m.action==='context')result={locale:'en',applications:[],navigation:{versions:[1]}};
  else if(m.action==='request'){
   const response=await fetch('/lyra'+m.path,{method:m.method,headers:{'Content-Type':'application/json','X-Nexus-Gateway-Key':KEY},...(m.body===undefined?{}:{body:JSON.stringify(m.body)})});
   result=await response.json();if(!response.ok)throw Error(result.detail||'Request failed');
  }else throw Error('Unexpected test bridge action');
  frame.contentWindow.postMessage({channel:m.channel,id:m.id,result},'*');
 }catch(error){frame.contentWindow.postMessage({channel:m.channel,id:m.id,error:error.message},'*');}
});
</script></html>""".replace("KEY", json.dumps(KEY))


def main():
    provider_server, provider_thread, provider_port = serve(provider)
    with tempfile.TemporaryDirectory(prefix="lyra-wp01-synthetic-") as temporary:
        lyra = create_app(
            temporary,
            nexus=NoNexus(),
            workers=False,
            tmdb_transport=LoopbackProvider(provider_port),
        )
        Credential(Path(temporary)).set(".".join(["synthetic"] * 3))
        with lyra.state.db.connect() as conn:
            mid = upsert_movie(conn, MOVIE)
            conn.execute(
                "INSERT INTO library(resource_type,resource_id,status,notes,added_at,updated_at) "
                "VALUES('movie',?,'planned','synthetic private note',?,?)",
                (mid, now_iso(), now_iso()),
            )
            conn.execute("INSERT INTO settings(key,value) VALUES('defaults_set','true')")
            sid = upsert_series(
                conn,
                {
                    "id": 303,
                    "name": "Synthetic Series",
                    "first_air_date": "2020-01-01",
                    "status": "Ended",
                    "seasons": [{"season_number": 1, "episode_count": 2}],
                },
                {
                    1: {
                        "id": 404,
                        "episodes": [
                            {
                                "id": 501,
                                "episode_number": 1,
                                "name": "Synthetic One",
                                "air_date": "2020-01-01",
                            },
                            {
                                "id": 502,
                                "episode_number": 2,
                                "name": "Synthetic Two",
                                "air_date": "2020-01-02",
                            },
                        ],
                    }
                },
                complete=True,
            )
            conn.execute(
                "INSERT INTO library(resource_type,resource_id,status,added_at,updated_at) VALUES('series',?,'planned',?,?)",
                (sid, now_iso(), now_iso()),
            )
        app = FastAPI()

        @app.get("/", response_class=HTMLResponse)
        def host():
            return HOST

        @app.get("/navigation-sdk.js")
        def sdk():
            return Response(
                (ROOT / "frontend/vendor/nexus-navigation.js").read_text(),
                media_type="text/javascript",
            )

        @app.get("/__fixture/counts")
        def counts():
            return COUNTS

        @app.get("/__fixture/ids")
        def ids():
            return {"movie": mid, "series": sid}

        @app.post("/__fixture/mode")
        async def mode(request: Request):
            body = await request.json()
            MODE.update(fail=bool(body.get("fail")), slow=bool(body.get("slow")))
            return MODE

        app.mount("/lyra", lyra)
        app_server, app_thread, app_port = serve(app)
        print(json.dumps({"url": f"http://127.0.0.1:{app_port}"}), flush=True)
        try:
            sys.stdin.readline()
        finally:
            app_server.should_exit = provider_server.should_exit = True
            app_thread.join(5)
            provider_thread.join(5)


if __name__ == "__main__":
    main()
