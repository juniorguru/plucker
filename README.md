## Plucker

---

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
    If setting the actor name and title, use the `name` value of `Spider` class, e.g. `honzajavorek/gravel-bikes`.
1.  Go to the <kbd>Source</kbd> tab. Set branch to `main` and folder to `juniorguru_plucker/gravel_bikes`.
1.  Go to the <kbd>Builds</kbd> tab and start a build.
1.  Go to the <kbd>Runs</kbd> tab and try a first run.
1.  Go to the <kbd>Monitoring</kbd> tab and set some alert rules at the bottom of the page.
    Look at existing actors and follow conventions.
1.  Go to the <kbd>Schedules</kbd> page and assign your new actor to an existing schedule or create a new one.

---

How to run:

- `poetry run apify run`
- `poetry run python -m juniorguru_plucker`

---

A template example built with Scrapy to scrape page titles from URLs defined in the input parameter. It shows how to use Apify SDK for Python and Scrapy pipelines to save results.

## Included features

- **[Apify SDK](https://docs.apify.com/sdk/python/)** for Python - a toolkit for building Apify [Actors](https://apify.com/actors) and scrapers in Python
- **[Input schema](https://docs.apify.com/platform/actors/development/input-schema)** - define and easily validate a schema for your Actor's input
- **[Request queue](https://docs.apify.com/sdk/python/docs/concepts/storages#working-with-request-queues)** - queues into which you can put the URLs you want to scrape
- **[Dataset](https://docs.apify.com/sdk/python/docs/concepts/storages#working-with-datasets)** - store structured data where each object stored has the same attributes
- **[Scrapy](https://scrapy.org/)** - a fast high-level web scraping framework

## How it works

This code is a Python script that uses Scrapy to scrape web pages and extract data from them. Here's a brief overview of how it works:

- The script reads the input data from the Actor instance, which is expected to contain a `start_urls` key with a list of URLs to scrape.
- The script then creates a Scrapy spider that will scrape the URLs. This Spider (class `TitleSpider`) is storing URLs and titles.
- Scrapy pipeline is used to save the results to the default dataset associated with the Actor run using the `push_data` method of the Actor instance.
- The script catches any exceptions that occur during the [web scraping](https://apify.com/web-scraping) process and logs an error message using the `Actor.log.exception` method.

## Resources

- [Web scraping with Scrapy](https://blog.apify.com/web-scraping-with-scrapy/)
- [Python tutorials in Academy](https://docs.apify.com/academy/python)
- [Alternatives to Scrapy for web scraping in 2023](https://blog.apify.com/alternatives-scrapy-web-scraping/)
- [Beautiful Soup vs. Scrapy for web scraping](https://blog.apify.com/beautiful-soup-vs-scrapy-web-scraping/)
- [Integration with Zapier](https://apify.com/integrations), Make, Google Drive, and others
- [Video guide on getting scraped data using Apify API](https://www.youtube.com/watch?v=ViYYDHSBAKM)
- A short guide on how to build web scrapers using code templates:

[web scraper template](https://www.youtube.com/watch?v=u-i-Korzf8w)


## Getting started

For complete information [see this article](https://docs.apify.com/platform/actors/development#build-actor-locally). To run the actor use the following command:

```
apify run
```

## Deploy to Apify

### Connect Git repository to Apify

If you've created a Git repository for the project, you can easily connect to Apify:

1. Go to [Actor creation page](https://console.apify.com/actors/new)
2. Click on **Link Git Repository** button

### Push project on your local machine to Apify

You can also deploy the project on your local machine to Apify without the need for the Git repository.

1. Log in to Apify. You will need to provide your [Apify API Token](https://console.apify.com/account/integrations) to complete this action.

    ```
    apify login
    ```

2. Deploy your Actor. This command will deploy and build the Actor on the Apify Platform. You can find your newly created Actor under [Actors -> My Actors](https://console.apify.com/actors?tab=my).

    ```
    apify push
    ```

## Documentation reference

To learn more about Apify and Actors, take a look at the following resources:

- [Apify SDK for JavaScript documentation](https://docs.apify.com/sdk/js)
- [Apify SDK for Python documentation](https://docs.apify.com/sdk/python)
- [Apify Platform documentation](https://docs.apify.com/platform)
- [Join our developer community on Discord](https://discord.com/invite/jyEM2PRvMU)
