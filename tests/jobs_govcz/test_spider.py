from datetime import date
from pathlib import Path
from typing import cast

from scrapy.http.response.html import HtmlResponse

from jg.plucker.items import Job
from jg.plucker.jobs_govcz.spider import Spider


FIXTURES_DIR = Path(__file__).parent


def test_spider_parse():
    response = HtmlResponse(
        "https://portal.isoss.gov.cz/irj/portal/...",
        body=Path(FIXTURES_DIR / "jobs.json").read_bytes(),
    )
    jobs = cast(list[Job], list(Spider().parse(response)))

    assert len(jobs) == 23

    assert jobs[0]["title"] == "Správce informačních systémů"
    assert (
        jobs[0]["url"]
        == "https://portal.isoss.gov.cz/irj/portal/anonymous/eosmlistpublic#/detail/30055211"
    )
    assert jobs[0]["company_name"] == "Generální finanční ředitelství"
    assert jobs[0]["locations_raw"] == ["Hradec Králové"]
    assert jobs[0]["posted_on"] == date(2025, 9, 15)
    assert jobs[0]["company_logo_urls"] == [
        "https://digitalnicesko.gov.cz/media/cache/b8/9e/b89e8e2d9063599378be731316c74393/statni-sprava-podklady-pro-media-16ku9-02.webp"
    ]
    assert jobs[0]["source"] == "jobs-govcz"
    assert jobs[0]["source_urls"] == ["https://portal.isoss.gov.cz/irj/portal/..."]
    assert jobs[0]["description_html"].startswith(
        "Správce informačních systémů vykonává tyto činnosti:  - zajišťování správy informačního systému service desku"
    )
