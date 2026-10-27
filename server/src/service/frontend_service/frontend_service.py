"""
Shared frontend registration utilities.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.engine_utils.directory_info import DirectoryInfo

InitConfigSource = Union[Dict[str, Any], Callable[[], Dict[str, Any]]]


@dataclass
class FrontendRegistrationOptions:
    """
    Options that control how the shared frontend is mounted.
    """

    mount_path: str = "/ui"
    root_route: str = "/"
    redirect_target: str = "/ui/index.html"
    init_config_route: str = "/openavatarchat/initconfig"
    frontend_dist_relative_path: str = "../../web/dist"


def _resolve_frontend_path(options: FrontendRegistrationOptions) -> Path:
    return Path(DirectoryInfo.get_src_dir()) / options.frontend_dist_relative_path


def _materialize_init_config(init_config: InitConfigSource) -> Dict[str, Any]:
    if callable(init_config):
        config = init_config()
    else:
        config = copy.deepcopy(init_config)

    if not isinstance(config, dict):
        raise ValueError("init_config must resolve to a dictionary.")

    return config


def register_frontend(
    app: FastAPI,
    init_config: InitConfigSource,
    options: Optional[FrontendRegistrationOptions] = None,
):
    """
    Register the web app and its init config endpoint.
    """

    opts = options or FrontendRegistrationOptions()
    frontend_path = _resolve_frontend_path(opts)

    @app.get(opts.init_config_route)
    async def init_config_endpoint():
        config = _materialize_init_config(init_config)
        return JSONResponse(status_code=200, content=config)

    @app.middleware("http")
    async def cross_origin_isolation(request, call_next):
        # BwithU: the 3D avatar's sorter uses shared WebAssembly memory, which Safari/WebKit only
        # allows on cross-origin isolated pages. Everything we load is same-origin.
        response = await call_next(request)
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response

    if frontend_path.exists():
        logger.info(f"Serving frontend from {frontend_path}")
        app.mount(opts.mount_path, StaticFiles(directory=frontend_path), name="static")

        # BwithU: serve the app at "/" itself; <base> keeps its relative asset URLs under the mount.
        index_file = frontend_path / "index.html"

        async def index(_request):
            html = index_file.read_text(encoding="utf-8")
            html = html.replace("<head>", f'<head><base href="{opts.mount_path.rstrip("/")}/">', 1)
            return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

        app.add_route(opts.root_route, index)
    else:
        logger.warning(f"Frontend directory {frontend_path} does not exist; run `npx vite build` in web/")

