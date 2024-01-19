from datetime import date

import pytest
from scrapy import Spider

from juniorguru_plucker.items import Job


@pytest.fixture
def item() -> Job:
    return Job(
        title="Junior Python Engineer",
        first_seen_on=date.today(),
        url="https://example.com/jobs/123",
        company_name="Mergado",
        employment_types=["full-time"],
        description_html="...",
        source="jobs-startupjobs",
        source_urls=[
            "https://www.startupjobs.cz/nabidka/38100/python-backend-developer-brno"
        ],
    )


@pytest.fixture
def spider() -> Spider:
    return Spider(name="sample")
