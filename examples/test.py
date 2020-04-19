#!/usr/bin/env python

import os
from loudds import LoudData


louddata = LoudData(
    access_token=os.environ["ACCESS_TOKEN"], url="http://cl-backend:8000", dataset_id=1,
)

tun = louddata.setup_tensorboard_tunnel()
tun.start()

# louddata.download_archive('https://staging-b.louddata.space/assets/f5Isrpkw.tgz', '../data')
# a tu jest uplaod do tesnorboarda po rsyncu, czyli tu chcemy dodac tunel ssh:
louddata.upload_tensorboard_logs(louddata.rsyncd_remote_url())

tun.stop()
