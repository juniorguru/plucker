# Read-only: last night's runs of scheduled actors
import os
import re
from datetime import datetime, timedelta, timezone

from apify_client import ApifyClient

client = ApifyClient(os.environ["APIFY_TOKEN"])
since = datetime.now(timezone.utc) - timedelta(hours=14)
for schedule in client.schedules().list().items:
    if not schedule.is_enabled:
        continue
    for action in schedule.actions:
        actor = client.actor(action.actor_id).get()
        for run in client.actor(action.actor_id).runs().list(desc=True, limit=3).items:
            if run.started_at < since:
                continue
            info = client.run(run.id).get()
            items = client.dataset(run.default_dataset_id).get().item_count
            secs = (info.finished_at - info.started_at).total_seconds() if info.finished_at else None
            print(f"RUN {actor.username}/{actor.name}: {info.status} items={items} secs={secs} started={run.started_at:%H:%M} id={run.id}", flush=True)
            if actor.name in ("jobs-jobscz", "followers") or info.status != "SUCCEEDED":
                log = client.run(run.id).log().get() or ""
                for line in log.splitlines():
                    if re.search(r"Proxy config|serialize|beta\.jobs|Gave up|ERROR|StatsError|response_status_count|item_scraped_count|finish_reason|elapsed_time|httpcache/|Skipping already seen|timed out|Run was rebooted", line):
                        print("    ", line[:220], flush=True)
