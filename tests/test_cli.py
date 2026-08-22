from jg.plucker.cli import dump_run_logs


class FakeLog:
    def __init__(self, text: str | None):
        self._text = text

    def get(self) -> str | None:
        return self._text


class FakeRun:
    def __init__(self, text: str | None):
        self._text = text

    def log(self) -> FakeLog:
        return FakeLog(self._text)


class FakeClient:
    def __init__(self, logs: dict[str, str | None]):
        self._logs = logs

    def run(self, run_id: str) -> FakeRun:
        return FakeRun(self._logs[run_id])


def test_dump_run_logs(tmp_path):
    client = FakeClient({"run1": "log one", "run2": "log two"})
    runs = [
        {"id": "run1", "status": "FAILED"},
        {"id": "run2", "status": "ABORTED"},
    ]

    paths = dump_run_logs(client, tmp_path, "apify/some-actor", runs)

    actor_dir = tmp_path / "apify__some-actor"
    assert [p.name for p in paths] == ["run1-FAILED.log", "run2-ABORTED.log"]
    assert (actor_dir / "run1-FAILED.log").read_text() == "log one"
    assert (actor_dir / "run2-ABORTED.log").read_text() == "log two"


def test_dump_run_logs_missing_log(tmp_path):
    client = FakeClient({"run1": None})
    runs = [{"id": "run1", "status": "FAILED"}]

    paths = dump_run_logs(client, tmp_path, "apify/some-actor", runs)

    assert paths[0].read_text() == ""


def test_dump_run_logs_fetch_error(tmp_path):
    class BoomClient:
        def run(self, run_id: str):
            raise RuntimeError("boom")

    runs = [{"id": "run1", "status": "FAILED"}]

    paths = dump_run_logs(BoomClient(), tmp_path, "apify/some-actor", runs)

    assert "failed to fetch log for run run1" in paths[0].read_text()
