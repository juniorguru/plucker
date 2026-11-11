# Agent instructions

## Parse strictly, fail loudly

Scrapers must never guess. Parse what you have seen and verified on real pages. When a page has something you haven't seen, raise an exception right away, so the run fails and someone fixes the scraper. Don't write fallbacks that silently produce a plausible-looking but possibly wrong value.

- Match known values exactly, for example a list of known location notes. Don't use broad regular expressions or keyword heuristics that also match things you've never seen.
- When a required piece of data is missing, or a known structure looks different, raise. Don't yield an item with an empty or made-up field.
- If a site has the data in structured form, prefer it over parsing free text. Examples: microdata, `<meta>` tags, or results of the site's own search filters.
- Skipping something on purpose is fine, for example ads in irrelevant languages. Make it an explicit, logged decision based on a reliable signal.
- Only support the languages junior.guru cares about: Czech, Slovak and English. Don't add parsing for other languages; skip such content instead.
- When unknown values are expected to come in several variants, such as the same note in three languages, the scraper may log each with `self.logger.error()` and skip the item instead of raising on the first one. The logged errors fail the run at the end, and the log has all the variants, so they can be added in one go. Log on the spider's own logger: on Apify, errors on `scrapy.*` loggers aren't counted. See the location notes in `jobs_profesiask`.

## Pure core, I/O shell

A function either computes or does I/O (HTTP requests, Apify storage, files, logging results), never both.

- Put data transformation in pure functions that take plain data and return plain data, such as the processors in `processors.py`. Cover them with unit tests.
- Spider callbacks, pipelines and actor code only fetch data, pass it to pure functions, and yield, store or send the results. A spider callback may take a response and yield items or requests, which tests can drive with saved HTML fixtures. Logic that doesn't need the response object belongs in a separate function that takes strings or dicts.
- Existing code doesn't always follow this. Don't copy a mixed pattern from surrounding code; split it in the code you add or change.
- Before finishing, check every function you added or changed: if it both transforms data and does I/O, split it.
