# Build jobs-jobscz from perf/jobscz-throttle and run it for 10 minutes
import os
import re
from datetime import timedelta

from apify_client import ApifyClient

client = ApifyClient(os.environ["APIFY_TOKEN"])
NAME = "jobs-jobscz-debug"
for actor_info in client.actors().list(my=True).items:
    if actor_info.name == NAME:
        client.actor(actor_info.id).delete()
actor_info = client.actors().create(
    name=NAME, title=NAME, is_public=False,
    versions=[dict(versionNumber="0.0", sourceType="GIT_REPO",
                   gitRepoUrl="https://github.com/juniorguru/plucker#perf/jobscz-throttle:src/jg/plucker/jobs_jobscz")],
)
actor = client.actor(actor_info.id)
try:
    build = actor.build(version_number="0.0", wait_for_finish=600)
    print("BUILD", build.status, flush=True)
    run = actor.call(run_timeout=timedelta(seconds=600), wait_duration=timedelta(seconds=720), logger=None)
    log = client.run(run.id).log().get() or ""
    items = client.dataset(run.default_dataset_id).get().item_count
    print(f"RUN {run.status} items={items} run={run.id}", flush=True)
    for line in log.splitlines():
        if re.search(r"Proxy config|Crawled \d+ pages|Gave up|403|429| ERROR |StatsError|TunnelError", line) and "RETRY_HTTP_CODES" not in line:
            print("    ", line[:200], flush=True)
finally:
    actor.delete()
