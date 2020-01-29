__version__ = "0.0.5"

import requests
import subprocess

LOUDDATA_HOST = "cl-backend:8000"


class LoudData:
    def __init__(self, *, access_token):
        self.access_token = access_token

    def send_predictions(self, dataset_id, summary):
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
