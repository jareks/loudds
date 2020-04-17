__version__ = "0.0.6"

import tarfile
import requests
import subprocess
import aiohttp
import aiofiles
import asyncio
import ujson
from pathlib import Path
from urllib.parse import urlsplit
from paramiko.pkey import PKey
import io
from contextlib import closing

import paramiko
import typing
import sshtunnel
import logging

LOUDDATA_URL = "http://cl-backend:8000"
SSH_HOST = 'localhost'
SSH_USERNAME = 'client'
SSH_PORT = 30022

LOCAL_SSH_BIND_HOST='localhost'

REMOTE_RSYNCD_PORT = 6873
DEFAULT_LOCAL_RSYNCD_BIND_PORT = 16873
KEY_CLASS = paramiko.ecdsakey.ECDSAKey

#TODO: this should be retrieved from backend user connects to via API
K8S_DOMAIN = 'cluster.local'


async def download_url_file(session, url, dir):
    response = await session.get(url)
    if response.status >= 400 and response.status < 500:
        return f"Incorrect url status code: {url} ({response.status})"
    body = await response.read()
    url_parts = urlsplit(url)
    parts = Path(url_parts.path).parts
    output_filename = parts[-1]
    async with aiofiles.open(dir / output_filename, "wb") as file:
        await file.write(body)
    #await session.close()
    return Path(output_filename)


async def download_url(session, url):
    response = await session.get(url)
    if response.status >= 400 and response.status < 500:
        return f"Incorrect url status code: {url} ({response.status})"
    body = await response.read()
    return body


class LoudData:
    def __init__(self, *, access_token, url=LOUDDATA_URL):
        self.access_token = access_token
        self.url = url
        self.session = aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar(),
            headers=dict(Authorization=f"Bearer {self.access_token}"),
        )

        self.setup_ssh_key()
        self.set_user_data()

    def __del__(self):
        loop = asyncio.get_event_loop()

        async def close_session():
            await self.session.close()

        loop.run_until_complete(close_session())


    def download_ssh_key(self):
        url = f"{self.url}/api1/ssh/key"
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(download_url(self.session, url))


    def set_user_data(self) -> None:
        url = f"{self.url}/me"
        loop = asyncio.get_event_loop()
        raw =  loop.run_until_complete(download_url(self.session, url))
        parsed = ujson.loads(raw)

        self.client_id = parsed["id"]
        self.organisation_id = parsed["organisation_id"]


    def parse_ssh_key(self, key: str):
        with closing(io.StringIO(key)) as strio:
            obj = KEY_CLASS.from_private_key(strio)
        return obj

    def setup_ssh_key(self):
        key = self.download_ssh_key()
        raw = ujson.loads(key.decode("utf-8"))["private_key"]
        self.ssh_key = self.parse_ssh_key(raw)


    def download_archive(self, url, dir, flatten=False):
        dir = Path(dir)
        loop = asyncio.get_event_loop()
        filename = loop.run_until_complete(
            download_url_file(self.session, url, Path(dir))
        )
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
        return requests.post(
            f"{self.url}/predictions/{dataset_id}",
            json=summary,
            headers={"Authorization": f"bearer {self.access_token}"},
        )

    def setup_ssh_tunnel(self, local: typing.Tuple[str,str], remote: typing.Tuple[str, str]) -> None:
        return sshtunnel.open_tunnel(
            ssh_address_or_host=(SSH_HOST, SSH_PORT),
            ssh_username=SSH_USERNAME,
            ssh_pkey=self.ssh_key,
            local_bind_address=local,
            remote_bind_address=remote,
            allow_agent=False,
            skip_tunnel_checkup=False,
            debug_level=logging.DEBUG
        )

    def rsyncd_svc(self, dataset_id):
        return f"classify-tensorboards-tensorboard-{self.organisation_id}-{dataset_id}-svc.org-{self.organisation_id}.svc.{K8S_DOMAIN}"

    def rsyncd_remote_url(self, rsyncd_port):
        return f"rsync://{LOCAL_SSH_BIND_HOST}:{rsyncd_port}/runs"

    def setup_tensorboard_tunnel(self, dataset_id, local_rsyncd_port=DEFAULT_LOCAL_RSYNCD_BIND_PORT):
        return self.setup_ssh_tunnel((LOCAL_SSH_BIND_HOST, local_rsyncd_port),(self.rsyncd_svc(dataset_id), REMOTE_RSYNCD_PORT))

    def upload_tensorboard_logs(self, rsync_url, dir="../runs/"):
        return subprocess.run(
            ["rsync", "-rv", "--inplace", dir, rsync_url],
            check=True,
            capture_output=True,
        )
