# Plucker 🪶

Junior Guru scrapers

## How does it work

This repository contains a source code of all scrapers Junior Guru needs for its functioning.
The scrapers are implemented using the [Scrapy framework](https://scrapy.org/) and albeit there are some customizations, most Scrapy conventions should work out of the box.
Contributing new scraper shouldn't be hard if you have some knowledge of how Scrapy works.

The scrapers are then deployed to the [Apify](https://apify.com) platform as so called _actors_.
The code here works as a monorepo for Apify actors and diverges quite significantly from the [Scrapy template](https://github.com/apify/actor-templates/tree/master/templates/python-scrapy) Apify provides.
Deploying new scraper to Apify is a manual process and it is documented below.

Code in this repository is executed by Apify, on their infrastructure.
The [main Junior Guru codebase](https://github.com/juniorguru/junior.guru) then gets the scraped data in form of [datasets](https://docs.apify.com/platform/storage/dataset) available through the Apify API.

## Installation

Have [uv](https://docs.astral.sh/uv/), run `uv sync`.
Use the `exchange-rates` scraper to test out whether everything works.
It's a minimal scraper performing just one request.
Try all of the following:

-   Run `uv run scrapy crawl exchange-rates` to run it by the **Scrapy CLI** as a pure **Scrapy spider**.
-   Run `uv run plucker crawl exchange-rates` to run it by the **CLI of this project** as a pure **Scrapy spider**.
-   Run `uv run plucker crawl exchange-rates --apify` to run it by the **CLI of this project** as a local **Apify actor**.

If you get no errors, you have the project correctly set up.

## Running scrapers

Use Scrapy's [crawl command](https://docs.scrapy.org/en/latest/topics/commands.html#crawl) or its [shell](https://docs.scrapy.org/en/latest/topics/shell.html).
Plucker has a `crawl` CLI command, which you can also use, but it's more useful for integrating with Apify than for the actual development of the scraper.

After each scraper run you can check the contents of the `items.json` file to see if your scraper works correctly.

## Passing parameters

Sometimes scrapers need input data.
Plucker's `crawl` CLI command can pass parameters to your scraper through the `--params` option. Use shell to pass ad-hoc data:

```
$ echo '{"links": [{"url": "https://junior.guru"}]}' | uv run plucker crawl job-checks --params
```

Use file for more complex input:

```
$ uv run plucker crawl job-links --params < params.json
```

You can also run it simply as `uv run plucker crawl job-links --params` and type the JSON manually as a standard input of the command.

At Apify, whatever is set as the [actor input](https://docs.apify.com/platform/actors/running/input-and-output) gets passed down as params (except for the proxy settings). Don't forget to add [input schema](https://docs.apify.com/platform/actors/development/actor-definition/input-schema) in your `actor.json`.

You can access the params inside the spider class as `self.settings.get("SPIDER_PARAMS")`.

## How to add new scraper

Look at existing code and follow conventions.
Creating new scraper, e.g. `gravel-bikes`:

1.  Should the new scraper produce items not yet known to this codebase, such as bikes, go to `src/jg/plucker/items.py` and add a new Scrapy [Item](https://docs.scrapy.org/en/latest/topics/items.html) class, e.g. `GravelBike`.
    Run `uv run plucker schemas` to generate schema for Apify.
    Should the new scraper produce items already known to this codebase, such as jobs, you can skip this step.
1.  Run `uv run plucker new`, answer questions.
    It is a [cookiecutter](https://github.com/cookiecutter/cookiecutter).
    It takes the `scraper_template` directory and creates a scaffolding of a new scraper for you.
1.  Fill the newly created `src/jg/plucker/gravel_bikes/spider.py` file with implementation of your scraper.
    See Scrapy documentation: [Tutorial](https://docs.scrapy.org/en/latest/intro/tutorial.html#our-first-spider), [Spiders](https://docs.scrapy.org/en/latest/topics/spiders.html) You can also learn scraping from the Apify's [Web scraping basics](https://docs.apify.com/academy/scraping-basics-python) course.
1.  Make sure the spider produces instances of the selected [Item](https://docs.scrapy.org/en/latest/topics/items.html) subclass, e.g. `GravelBike`.
1.  Run the spider with `uv run scrapy crawl gravel-bikes`.
    Learn about Scrapy's [crawl command](https://docs.scrapy.org/en/latest/topics/commands.html#crawl) or its [shell](https://docs.scrapy.org/en/latest/topics/shell.html).
    Develop and debug.
1.  Test the spider, i.e. create `tests/gravel_bikes` directory with `test_spider.py` inside and optionally with some test fixtures (static HTML files etc.) around.

## Deploying to Apify (you need to be admin)

1.  Push all your code to GitHub.
1.  Run `uv run plucker deploy gravel-bikes`.
1.  Go to [Apify Console](https://console.apify.com/actors) and verify everything went well.
1.  Go to the <kbd>Builds</kbd> tab and start a build.
1.  Go to the <kbd>Runs</kbd> tab and try a first run.
1.  Go to the <kbd>Schedules</kbd> page and assign your new actor to an existing schedule or create a new one.

## Automatic builds

There is a nightly GitHub Action which re-builds all actors based on current code in the `main` branch.
This is because Apify's built-in automatic builds didn't work properly, but also because it would be undesirable to waste resources when committing code often.

## Monitoring

There is a nightly GitHub Action which checks whether each actor's last run finished with success.
In case they didn't, the GitHub Action fails, which causes an e-mail notification.
Apify used to send summary e-mail about actor runs, but they removed that feature and there was no equivalent at the time.
Maybe there is now, but the monitoring is already implemented, so…

## Notes on development

-   It is preferred to pin exact versions of dependencies, without `^`, and let GitHub's Dependabot to upgrade dependencies in Pull Requests.
    Unfortunately there is no setting in pyproject.toml, which would force this behavior, so once new dependencies are added, one needs to go and manually remove the `^` characters.
-   Run `pytest` to see if your code has any issues.
-   Run `ruff check --fix` and `ruff format` to fix your code.

## Dictionary

-   _scraper_ - Generic name for a program which downloads data from web pages (or APIs). This repository uses the word scraper to refer to a spider & actor combo.
-   _spider_ - This is how [Scrapy](https://scrapy.org/) framework calls implementation of a scraper.
-   _actor_ - This is how the [Apify](https://apify.com) platform calls implementation and deployment of a scraper.
-   _plucker_ - Repository of Junior Guru scrapers. In English, a plucker is one who or that which plucks. Naming in Junior Guru is usually poultry-themed, and Honza felt that plucking is a nice analogy to web scraping.

## License
[AGPL-3.0-only](LICENSE), copyright (c) 2024 Jan Javorek, and contributors.
