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

## Running scrapers

Just use Scrapy's [crawl command](https://docs.scrapy.org/en/latest/topics/commands.html#crawl) or its [shell](https://docs.scrapy.org/en/latest/topics/shell.html).
Plucker has a `crawl` CLI command, which you can also use, but it's more useful for integrating with Apify than for the actual development of the scraper.

## How to add new scraper

Creating new scraper, e.g. `gravel-bikes`:

1.  Create new package, i.e. new directory `juniorguru_plucker/gravel_bikes` with `__init__.py` inside.
    If the name has multiple words, be use underscores, but only for the directory name.
1.  Configure Apify actor, i.e. new `juniorguru_plucker/gravel_bikes/.actor` directory with `actor.json` file inside.
    If the actor name has multiple words, be sure to use dashes and not underscores.
    Look at existing actor configurations and follow conventions.
1.  If the new scraper should produce items already known to this codebase, such as jobs, find corresponding schema in `juniorguru_plucker/schemas` and link it as a `dataset` schema.
    Look at existing actor configurations how it's done.
1.  If the new scraper should produce something new, such as bikes, go to `juniorguru_plucker/items.py` and add a new Scrapy [Item](https://docs.scrapy.org/en/latest/topics/items.html) class, e.g. `GravelBike`.
    Look at existing items and follow conventions.
    Run `jgp schemas` to generate schema for Apify, then link it as a `dataset` schema in the actor configuration.
    Look at existing actor configurations how it's done.
1.  Create Scrapy spider, i.e. new `juniorguru_plucker/bikes/spider.py` file with `Spider` class inside.
    If the spider name has multiple words, be sure to use dashes and not underscores.
    Look at existing spiders and follow conventions.
1.  Run the spider with `scrapy crawl gravel-bikes`.
    Learn about Scrapy's [crawl command](https://docs.scrapy.org/en/latest/topics/commands.html#crawl) or its [shell](https://docs.scrapy.org/en/latest/topics/shell.html).
    Develop and debug.
1.  Test the spider, i.e. create `tests/gravel_bikes` directory with `test_spider.py` inside and optionally with some test fixtures (static HTML files etc.) around.
    Look at existing tests and follow conventions.

Deploying to Apify:

1.  As an admin, go to [Apify Console](https://console.apify.com/) and add a new actor by linking a GitHub repository.
1.  Change both actor's <kbd>Title</kbd> and <kbd>Unique name</kbd> to the `name` value of `Spider` class, e.g. `honzajavorek/gravel-bikes`.
1.  Go to the <kbd>Source</kbd> tab. Set branch to `main` and folder to `juniorguru_plucker/gravel_bikes`.
1.  Go to the <kbd>Builds</kbd> tab and start a build.
1.  Go to the <kbd>Runs</kbd> tab and try a first run.
1.  Go to the <kbd>Schedules</kbd> page and assign your new actor to an existing schedule or create a new one.

There is a nightly GitHub Action which re-builds all actors based on current code in the `main` branch.
This is because the automatic builds didn't work properly, but also because it would be undesirable to waste resources when committing code often.

## Notes on development

-   Use [Poetry](https://python-poetry.org/) for dependency management.
-   It is preferred to pin exact versions of dependencies, without `^`, and let GitHub's Dependabot to upgrade dependencies in Pull Requests.
    Unfortunately there is no setting in pyproject.toml, which would force this behavior, so once new dependencies are added, one needs to go and manually remove the `^` characters.
-   Run `pytest` to see if your code has any issues.
-   Run `ruff check --fix` and `ruff format` to fix your code.

## Dictionary

-   _scraper_ - Generic name for a program which downloads data from web pages (or APIs). This repository uses the word scraper to refer to a spider & actor combo.
-   _spider_ - This is how [Scrapy](https://scrapy.org/) framework calls implementation of a scraper.
-   _actor_ - This is how the [Apify](https://apify.com) platform calls implementation of a scraper.
-   _plucker_ - Repository of Junior Guru scrapers. In English, a plucker is one who or that which plucks. Naming in Junior Guru is usually poultry-themed, and Honza felt that plucking is a nice analogy to web scraping.
