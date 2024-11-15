import json
from pathlib import Path

import pytest

from jg.plucker.jobs_linkedin.spider import (
    clean_proxied_url,
    clean_url,
    clean_validated_url,
    create_job,
    get_job_id,
)


FIXTURES_DIR = Path(__file__).parent


def test_create_job_nonexisting_company():
    with (FIXTURES_DIR / "job_nonexisting_company.json").open("rb") as f:
        job_data = json.load(f)

    with pytest.raises(NotImplementedError):
        create_job(job_data)


def test_create_job_company():
    with (FIXTURES_DIR / "job_company.json").open("rb") as f:
        job_data = json.load(f)
    job = create_job(job_data)

    assert job["company_name"] == "Honeywell"
    assert job["company_logo_urls"] == [
        "https://media.licdn.com/dms/image/v2/C560BAQFvcIh3UnA5zw/company-logo_200_200/company-logo_200_200/0/1630621634841/honeywell_logo?e=1740009600&v=beta&t=8LT9QPeKKRNGocRhbCD1ldZyAmsQyqZ5DH0iUJR47Q8",
        "https://media.licdn.com/dms/image/v2/C560BAQFvcIh3UnA5zw/company-logo_100_100/company-logo_100_100/0/1630621634841/honeywell_logo?e=1740009600&v=beta&t=3bNJkbz4MKfMjWhpsMZYROtO30XN4a31WkJCZzl9Tt0",
        "https://media.licdn.com/dms/image/v2/C560BAQFvcIh3UnA5zw/company-logo_400_400/company-logo_400_400/0/1630621634841/honeywell_logo?e=1740009600&v=beta&t=MF61uButsIoHsy8S9hflXbLv96dEKBJg2t12xk3wovE",
    ]


def test_create_job_no_logo():
    with (FIXTURES_DIR / "job_no_logo.json").open("rb") as f:
        job_data = json.load(f)
    job = create_job(job_data)

    assert job["company_name"] == "Sinop a.s."
    assert job["company_logo_urls"] == []


def test_create_job_company_name():
    with (FIXTURES_DIR / "job_company_name.json").open("rb") as f:
        job_data = json.load(f)
    job = create_job(job_data)

    assert job["company_name"] == "Marmon Foodservice Manufacturing s.r.o."
    assert job["company_logo_urls"] == []


def test_create_job_offsite_apply():
    with (FIXTURES_DIR / "job_offsite_apply.json").open("rb") as f:
        job_data = json.load(f)
    job = create_job(job_data)

    assert (
        job["apply_url"]
        == "https://careers.honeywell.com/us/en/job/HONEUSHRD247602EXTERNALENUS/Software-Engineer-I"
    )


def test_create_job_no_offsite_apply():
    with (FIXTURES_DIR / "job_no_offsite_apply.json").open("rb") as f:
        job_data = json.load(f)
    job = create_job(job_data)

    assert job["apply_url"] is None


def test_clean_proxied_url():
    url = (
        "https://cz.linkedin.com/jobs/view/externalApply/2006390996"
        "?url=https%3A%2F%2Fjobs%2Egecareers%2Ecom%2Fglobal%2Fen%2Fjob%2FGE11GLOBAL32262%2FEngineering-Trainee%3Futm_source%3Dlinkedin%26codes%3DLinkedIn%26utm_medium%3Dphenom-feeds"
        "&urlHash=AAbh&refId=94017428-1cc1-48ad-bda2-d9ddabeb1c55&trk=public_jobs_apply-link-offsite"
    )

    assert (
        clean_proxied_url(url)
        == "https://jobs.gecareers.com/global/en/job/GE11GLOBAL32262/Engineering-Trainee?codes=juniorguru"
    )


def test_clean_validated_url():
    url = (
        "http://validate.perfdrive.com/4708da524564ee0915d03f8ef0481f9d/"
        "?ssa=c1b11acc-f3fd-4db6-9dcf-4c36cddb0133&ssb=08429203719"
        "&ssc=http%3A%2F%2Fred-hat-1.talentify.io%2Fjob%2Fjunior-software-engineer-package-maintainer-part-time-brno-southeast-red-hat-89305"
        "&ssi=c942d48f-bgon-0847-364d-4dae40d0c40b"
        "&ssk=support@shieldsquare.com"
        "&ssm=48230879602575515162700730631252"
        "&ssn=c03a60a5bd22f3c8753a9d199da7f997d879aaabcc26-21f7-46d1-ae5b73&sso=29ce95d2-fabf1b301fcbafb1da0f5201be83bcd10b904ffc649c3938"
        "&ssp=71823123601634260373163420895431754"
        "&ssq=26200217335195395023172872720195943237649"
        "&ssr=My44OC4yMTguMTEx&sst=Mozilla/5.0%20(iPhone;%20CPU%20OS%2014_0_1%20like%20Mac%20OS%20X)%20AppleWebKit/605.1.15%20(KHTML,%20like%20Gecko)%20FxiOS/29.0%20Mobile/15E148%20Safari/605.1.15"
        "&ssv=aWFiM2hlMHVzMTMwZ2dqc2R1NHZha203MGE="
        "&ssw=iab3he0us130ggjsdu4vakm70a"
    )

    assert (
        clean_validated_url(url)
        == "http://red-hat-1.talentify.io/job/junior-software-engineer-package-maintainer-part-time-brno-southeast-red-hat-89305"
    )


def test_get_job_id():
    url = (
        "https://cz.linkedin.com/jobs/view/"
        "junior-software-engineer-at-cimpress-technology-2247016723"
    )

    assert get_job_id(url) == "2247016723"


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://uk.linkedin.com/company/adaptavist?trk=public_jobs_topcard_logo",
            "https://uk.linkedin.com/company/adaptavist",
        ),
        ("https://example.com?trk=123", "https://example.com?trk=123"),
        (
            "https://pipedrive.talentify.io/job/junior-software-engineer-prague-prague-pipedrive-015b84ef-3956-4a28-877f-0385379d40c2?tdd=dDEsaDM1LGozdXFlZSxlcHJvNjA3ZjBhOTA2ZDVkNjE2OTQ4ODk3OA",
            "https://pipedrive.talentify.io/job/junior-software-engineer-prague-prague-pipedrive-015b84ef-3956-4a28-877f-0385379d40c2",
        ),
        (
            "https://neuvoo.cz/job.php?id=b5f15b6eeadc&source=juniorguru&puid=aadegddb8adaeddfeddb9ade7ddafadbaadbfadf3aeccacdfec3ddcg3e",
            "https://neuvoo.cz/job.php?id=b5f15b6eeadc&source=juniorguru",
        ),
        (
            "https://jobs.lever.co/pipedrive/015b84ef-3956-4a28-877f-0385379d40c2/apply",
            "https://jobs.lever.co/pipedrive/015b84ef-3956-4a28-877f-0385379d40c2/",
        ),
        (
            "https://erstegroup-careers.com/csas/job/Hlavn%C3%AD-m%C4%9Bsto-Praha-Tester-EOM/667861301/?locale=cs_CZ&utm_campaign=lilimitedlistings&utm_source=lilimitedlistings&applySourceOverride=Linkedin%20Limited%20Listings",
            "https://erstegroup-careers.com/csas/job/Hlavn%C3%AD-m%C4%9Bsto-Praha-Tester-EOM/667861301/?locale=cs_CZ&applySourceOverride=juniorguru+Limited+Listings",
        ),
    ],
)
def test_clean_url(url, expected):
    assert clean_url(url) == expected
