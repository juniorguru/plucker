# Read-only: full stats of last night's jobs-jobscz run, and who started the 20:43 run
import os
import re

from apify_client import ApifyClient

client = ApifyClient(os.environ["APIFY_TOKEN"])
for run_id in ["IMnLPw5WXshEOEO8b", "UQbFv5z0a3lGi4zaR"]:
    info = client.run(run_id).get()
    print(f"RUN {run_id} origin={info.meta.origin} status={info.status}", flush=True)
    log = client.run(run_id).log().get() or ""
    m = re.search(r"Dumping Scrapy stats:(.*?)\}\s*\(\{", log, re.S)
    if m:
        for line in m.group(1).splitlines():
            line = re.sub(r"^\S+Z\s?", "", line).strip()
            if line:
                print("    ", line[:200], flush=True)
    for line in log.splitlines():
        if re.search(r"WARN|Dropped|dropped", line):
            print("  W ", line[:220], flush=True)
