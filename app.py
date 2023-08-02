#!/usr/bin/env python

import asyncio
import http
import signal
import os
import re
from pathlib import PurePath
from urllib.parse import unquote
from mimetypes import guess_type

import websockets
from yt_dlp import YoutubeDL, parse_options


DOWNLOADS_DIR = "downloads"


async def echo(websocket):
    async for message in websocket:
        video_url = message

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
            "--no-colors",
            "--embed-thumbnail",
            "--embed-metadata",
            *("--parse-metadata", "%(uploader)s:%(album)s"),
            *("--output", output),
            *("--format", "m4a"),
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
                ydl.download([video_url])

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, download)

        if filepath:
            await websocket.send("@@@ " + PurePath("/", filepath).as_posix())

        await websocket.close()


def serve_file(path, headers):
    try:
        with open(path, "rb") as f:
            mime = guess_type(path)[0]

            # small hack:
            # `guess_type` gives `audio/mpeg` type which results into
            # a file being downloaded incorrectly with `.mp3` extension
            if path.endswith(".m4a"):
                mime = "audio/mp4"

            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            start = 0
            end = file_size

            range_header = headers.get_all("Range")
            if range_header:
                try:
                    m = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header[0])
                    if not m:
                        raise AssertionError()

                    start, end = [int(x) if x else None for x in m.groups()]

                    bad = start is None and end is None
                    bad_start = (start or False) >= (end or file_size)
                    bad_end = (end or False) > file_size
                    if bad or bad_start or bad_end:
                        raise AssertionError()

                    if start is None:
                        start = file_size - end
                        end = file_size

                    if end is None:
                        end = file_size
                except AssertionError:
                    return http.HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, [], b""

            f.seek(start)
            range_size = end - start

            headers = {
                "Content-Type": mime,
                "Content-Length": range_size,
                "Accept-Ranges": "bytes",
            }

            if range_header:
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

            status = (
                http.HTTPStatus.PARTIAL_CONTENT if range_header else http.HTTPStatus.OK
            )

            return status, headers, f.read(range_size)
    except FileNotFoundError:
        return http.HTTPStatus.NOT_FOUND, [], b""


async def process_request(path, request_headers):
    if path == "/healthz":
        return http.HTTPStatus.OK, [], b"OK\n"

    if path == "/":
        return serve_file("index.html", request_headers)

    if path.startswith("/" + DOWNLOADS_DIR):
        filepath = unquote(path[1:])
        return serve_file(filepath, request_headers)


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
