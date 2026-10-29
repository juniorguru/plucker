# Agent instructions

## Parse strictly, fail loudly

Scrapers must never guess. Parse what you have seen and verified on real pages. When a page has something you haven't seen, raise an exception right away, so the run fails and someone fixes the scraper. Don't write fallbacks that silently produce a plausible-looking but possibly wrong value.

- Match known values exactly, for example a list of known location notes. Don't use broad regular expressions or keyword heuristics that also match things you've never seen.
- When a required piece of data is missing, or a known structure looks different, raise. Don't yield an item with an empty or made-up field.
- If a site has the data in structured form, prefer it over parsing free text. Examples: microdata, `<meta>` tags, or results of the site's own search filters.
- Skipping something on purpose is fine, for example ads in irrelevant languages. Make it an explicit, logged decision based on a reliable signal.
- Only support the languages junior.guru cares about: Czech, Slovak and English. Don't add parsing for other languages; skip such content instead.
