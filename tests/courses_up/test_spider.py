from pathlib import Path
from typing import cast

from scrapy import Request
from scrapy.http import TextResponse

from jg.plucker.courses_up.spider import Spider
from jg.plucker.items import CourseProvider


FIXTURES_DIR = Path(__file__).parent


def test_parse_courses():
    spider = Spider()
    response = TextResponse(
        "https://www.uradprace.cz/api/rekvalifikace/rest/kurz/query",
        body=Path(FIXTURES_DIR / "courses.json").read_bytes(),
    )
    results = list(spider.parse_courses(response, 100))

    assert len(results) == 101
    assert all(isinstance(result, CourseProvider) for result in results[:100])
    assert isinstance(results[100], Request)

    course = cast(CourseProvider, results[0])

    assert course["id"] == 17834
    assert (
        course["url"]
        == "https://www.uradprace.cz/web/cz/vyhledani-rekvalifikacniho-kurzu#/rekvalifikacni-kurz-detail/17834"
    )
    assert (
        course["name"]
        == "Účetnictví a daňová evidence (s využitím výpočetní techniky, v rozsahu 170 hodin teoretické výuky, z toho 170 hodin distanční formou) - živé vysílání se záznamem"
    )
    assert (
        course["description"]
        == "Finanční účetnictví a daňová evidence podnikatele - kompletní účtování, zaznamenávání, evidence, výkazy a povinné tiskopisy s důrazem na praxi. Nenutná přítomnost na živém vysílání, tzn. lze zhlédnout jen videonahrávku.\nVíce informací na mých internet. stránkách: www.martinsimacek.cz"
    )
    assert course["company_name"] == "Martin Šimáček"
    assert course["cz_business_id"] == 7653115
