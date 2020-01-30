__version__ = "0.0.6"

import tarfile
import requests
import subprocess
import aiohttp
import aiofiles
import asyncio
from pathlib import Path
from urllib.parse import urlsplit

LOUDDATA_HOST = "cl-backend:8000"


async def get_url(session, url, dir):
    response = await session.get(url)
    if response.status >= 400 and response.status < 500:
        return f"Incorrect url status code: {url} ({response.status})"
    body = await response.read()
    url_parts = urlsplit(url)
    parts = Path(url_parts.path).parts
    output_filename = parts[-1]
    async with aiofiles.open(dir / output_filename, "wb") as file:
        await file.write(body)
    await session.close()
    return Path(output_filename)


class LoudData:
    def __init__(self, *, access_token):
        self.access_token = access_token
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar())

    def __del__(self):
        loop = asyncio.get_event_loop()

        async def close_session():
            await self.session.close()

        loop.run_until_complete(close_session())

    def download_archive(self, url, dir, flatten=False):
        dir = Path(dir)
        loop = asyncio.get_event_loop()
        filename = loop.run_until_complete(get_url(self.session, url, Path(dir)))
        self.untar_archive(dir / filename, dir, flatten=flatten)

    def untar_archive(self, filename, dir, flatten=False):
        dir = Path(dir)
        filename = Path(filename)
        if flatten:
            (dir / filename.stem).mkdir(mode=0o700, parents=True, exist_ok=True)

        tar = tarfile.open(filename, mode="r:*")
        for f in tar.getmembers():
            buf = tar.extractfile(f)
            data = buf.read()
            path = Path(f.path)
            if path.is_absolute() or "../" in str(path):
                raise Exception(f"Incorrect path in archive: {path}")

            if not flatten and f.isdir():
                path.mkdir(mode=0o700, parents=True, exist_ok=True)
            elif f.isreg():
                if flatten:
                    output = dir / filename.stem / path.name
                else:
                    output = dir / path
                    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

                with open(output, "wb") as out:
                    out.write(data)

    def send_predictions(self, dataset_id, summary):
        # TODO: Replace with aiohttp
        requests.post(
            f"http://{LOUDDATA_HOST}/predictions/{dataset_id}",
            json=summary,
            headers={"Authorization": f"bearer {self.access_token}"},
        )

    def upload_runs(self, tb_host, tb_port, dir="../runs/"):
        return subprocess.run(
            ["rsync", "-rv", "--inplace", dir, f"rsync://{tb_host}:{tb_port}/runs"],
            check=True,
            capture_output=True,
        )
