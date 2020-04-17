#!/usr/bin/env python

from loudds import LoudData,DEFAULT_LOCAL_RSYNCD_BIND_PORT
louddata = LoudData(access_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxLCJvcmlnaW4iOiIqIn0.aTfwJWQP0C6xmdgzydxfAuotpC--8Ls29lU1cdYqwI0")

tun = louddata.setup_tensorboard_tunnel(dataset_id=1)
print(tun)
tun.start()
print(tun)

input("press something before sending data via rsync...")
#louddata.download_archive('https://staging-b.louddata.space/assets/f5Isrpkw.tgz', '../data')
# a tu jest uplaod do tesnorboarda po rsyncu, czyli tu chcemy dodac tunel ssh:
louddata.upload_tensorboard_logs(louddata.rsyncd_remote_url(DEFAULT_LOCAL_RSYNCD_BIND_PORT))

tun.stop()
