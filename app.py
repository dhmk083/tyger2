#!/usr/bin/env python

import asyncio
import http
import signal
import os
from pathlib import PurePath
from urllib.parse import unquote

import websockets
from yt_dlp import YoutubeDL, parse_options


DOWNLOADS_DIR = "downloads"


async def echo(websocket):
    async for message in websocket:

        class Logger:
            def debug(self, msg):
                # For compatibility with youtube-dl, both debug and info are passed into debug
                # You can distinguish them by the prefix '[debug] '
                if msg.startswith("[debug] "):
                    pass
                else:
                    self.info(msg)

            def info(self, msg):
                self._send(msg)

            def warning(self, msg):
                self._send(msg)

            def error(self, msg):
                self._send(msg)

            def _send(self, msg):
                asyncio.run(websocket.send(msg))

        filepath = ""

        def pp_hook(d):
            nonlocal filepath

            fp = d["info_dict"].get("filepath")
            if fp:
                filepath = fp

        output = os.path.join(DOWNLOADS_DIR, "%(channel)s - %(title)s.%(ext)s")

        argv = [
            "--embed-thumbnail",
            "--embed-metadata",
            *("--parse-metadata", "%(uploader)s:%(album)s"),
            *("--output", output),
            *("--format", "140"),
        ]

        opts = parse_options(argv)[3]

        opts.update(
            {
                "logger": Logger(),
                "postprocessor_hooks": [pp_hook],
            }
        )

        def download():
            with YoutubeDL(opts) as ydl:
                ydl.download(["https://www.youtube.com/watch?v=zGDzdps75ns"])

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, download)

        await websocket.send(PurePath("/", filepath).as_posix())


async def process_request(path, request_headers):
    if path == "/healthz":
        return http.HTTPStatus.OK, [], b"OK\n"

    if path.startswith("/" + DOWNLOADS_DIR):
        filepath = unquote(path[1:])

        try:
            with open(filepath, "rb") as f:
                return http.HTTPStatus.OK, [], f.read()
        except FileNotFoundError:
            return http.HTTPStatus.NOT_FOUND, [], b""


async def main():
    # Set the stop condition when receiving SIGTERM.
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    async with websockets.serve(
        echo,
        host="",
        port=8080,
        process_request=process_request,
    ):
        await stop


if __name__ == "__main__":
    asyncio.run(main())
