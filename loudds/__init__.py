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
import io
from contextlib import closing

import paramiko
import typing
import sshtunnel
import logging

LOUDDATA_URL = "http://cl-backend:8000"
SSH_USERNAME = "client"
LOCAL_SSH_BIND_HOST = "localhost"

REMOTE_RSYNCD_PORT = 6873
DEFAULT_LOCAL_RSYNCD_BIND_PORT = 16873
KEY_CLASS = paramiko.ecdsakey.ECDSAKey


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
    # await session.close()
    return Path(output_filename)


async def download_url(session: aiohttp.ClientSession, url: str) -> str:
    response = await session.get(url)
    if response.status != 200:
        return f"Incorrect url status code: {url} ({response.status})"
    body = await response.read()
    return body


class LoudData:
    def __init__(
        self, *, access_token: str, url: str = LOUDDATA_URL, dataset_id: int = None, tunnel_bind_host: str = LOCAL_SSH_BIND_HOST
    ) -> None:

        self.dataset_id = dataset_id
        self.access_token = access_token
        self.tunnel_bind_host = tunnel_bind_host
        self.url = url
        self.session = aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar(),
            headers=dict(Authorization=f"Bearer {self.access_token}"),
        )

        self.setup_ssh_key()
        self.setup_instance_data()
        self.set_user_data()


    def download_ssh_key(self) -> str:
        url = f"{self.url}/api1/ssh/key"
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(download_url(self.session, url))

    def set_user_data(self) -> None:
        url = f"{self.url}/me"
        loop = asyncio.get_event_loop()
        raw = loop.run_until_complete(download_url(self.session, url))
        parsed = ujson.loads(raw)

        self.client_id = parsed["id"]
        self.organisation_id = parsed["organisation_id"]

    def parse_ssh_key(self, key: str) -> KEY_CLASS:
        with closing(io.StringIO(key)) as strio:
            obj = KEY_CLASS.from_private_key(strio)
        return obj

    def setup_ssh_key(self) -> None:
        key = self.download_ssh_key()
        raw = ujson.loads(key.decode("utf-8"))["private_key"]
        self.ssh_key = self.parse_ssh_key(raw)

    def setup_instance_data(self) -> None:
        url = f"{self.url}/api1/info"
        loop = asyncio.get_event_loop()
        data = loop.run_until_complete(download_url(self.session, url))
        raw = ujson.loads(data.decode("utf-8"))
        self.k8s_domain = raw["k8s_domain"]
        self.proxy_ssh_host = raw["proxy_ssh_host"]
        self.proxy_ssh_port = raw["proxy_ssh_port"]

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

    def send_predictions(self, summary, dataset_id=None):

        dataset_id = self._require_value(dataset_id or self.dataset_id)

        # TODO: Replace with aiohttp
        return requests.post(
            f"{self.url}/predictions/{dataset_id}",
            json=summary,
            headers={"Authorization": f"bearer {self.access_token}"},
        )

    def setup_ssh_tunnel(
        self, local: typing.Tuple[str, int], remote: typing.Tuple[str, int]
    ) -> sshtunnel.SSHTunnelForwarder:
        return sshtunnel.open_tunnel(
            ssh_address_or_host=(self.proxy_ssh_host, self.proxy_ssh_port),
            ssh_username=SSH_USERNAME,
            ssh_pkey=self.ssh_key,
            local_bind_address=local,
            remote_bind_address=remote,
            allow_agent=False,
            skip_tunnel_checkup=False,
            debug_level=logging.DEBUG,
        )

    def rsyncd_svc(self, dataset_id: int) -> str:
        dataset_id = self._require_value(dataset_id or self.dataset_id)
        return f"classify-tensorboards-tensorboard-{self.organisation_id}-{dataset_id}-svc.org-{self.organisation_id}.svc.{self.k8s_domain}"

    def rsyncd_remote_url(self, rsyncd_port: int = DEFAULT_LOCAL_RSYNCD_BIND_PORT) -> str:
        return f"rsync://{self.tunnel_bind_host}:{rsyncd_port}/runs"

    @staticmethod
    def _require_value(val: typing.Any) -> typing.Any:
        if val is None:
            raise ValueError("value is None")
        return val

    def setup_tensorboard_tunnel(
        self,
        local_rsyncd_port: int = DEFAULT_LOCAL_RSYNCD_BIND_PORT,
        dataset_id: typing.Tuple[None, int] = None,
    ) -> sshtunnel.SSHTunnelForwarder:
        dataset_id = self._require_value(dataset_id or self.dataset_id)
        return self.setup_ssh_tunnel(
            (self.tunnel_bind_host, local_rsyncd_port),
            (self.rsyncd_svc(dataset_id), REMOTE_RSYNCD_PORT),
        )

    def upload_tensorboard_logs(
        self, rsync_url: str, dir: str = "../runs/"
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["rsync", "-rv", "--inplace", dir, rsync_url],
                check=True,
                capture_output=True,
            )

        # default exception handler does not print sdout/stderr from failed process
        except subprocess.CalledProcessError as e:
            print("rsync stdout:")
            print(e.stdout.decode("utf-8"))
            print("rsync stderr:")
            print(e.stderr.decode("utf-8"))
            raise

    async def __aexit__(self, *err):
        await self.session.close()
        self.session = None
