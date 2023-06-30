#!/usr/bin/env python

import asyncio
import http
import signal
import os
from urllib.parse import urlparse, parse_qs

import websockets
from yt_dlp import YoutubeDL


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

        opts = {"outtmpl": os.path.join(DOWNLOADS_DIR, "1.webm"), "logger": Logger()}

        def download():
            with YoutubeDL(opts) as ydl:
                ydl.download(["https://www.youtube.com/watch?v=zGDzdps75ns"])

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, download)

        await websocket.send(message)


async def process_request(path, request_headers):
    if path == "/healthz":
        return http.HTTPStatus.OK, [], b"OK\n"

    if path == "/test":
        opts = {"outtmpl": os.path.join(DOWNLOADS_DIR, "1.webm")}

        with YoutubeDL(opts) as ydl:
            ydl.download(["https://www.youtube.com/watch?v=zGDzdps75ns"])

        return http.HTTPStatus.OK, [], b"OK\n"

    if path == "/ls":
        return http.HTTPStatus.OK, [], "\n".join(os.listdir()).encode()

    if path.startswith("/get"):
        q = urlparse(path).query
        file = parse_qs(q)["file"][0]

        with open(os.path.join(DOWNLOADS_DIR, file), "rb") as f:
            return http.HTTPStatus.OK, [], f.read()


async def main():
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

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
