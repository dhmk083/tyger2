#!/usr/bin/env python

import asyncio
import http
import signal
import os

import websockets
import requests


async def echo(websocket):
    async for message in websocket:
        await websocket.send(message)


async def process_request(path, request_headers):
    if path == "/healthz":
        return http.HTTPStatus.OK, [], b"OK\n"

    if path == "/test":
        r = requests.get("http://worldtimeapi.org/api/ip")
        with open("test.json", "wb") as f:
            f.write(r.content)
        return http.HTTPStatus.OK, [], b"OK\n"

    if path == "/ls":
        return http.HTTPStatus.OK, [], "\n".join(os.listdir()).encode()


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
