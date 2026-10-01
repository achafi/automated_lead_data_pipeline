# Map-Based Business Data Collector

A small portfolio MVP for freelancers and business researchers who need a geographic starting point for business research. Select a category, draw a rectangle, preview OpenStreetMap records, and download them as CSV. No API key is required.

> This is an independent demonstration project built to show interactive geographic selection, API integration, geospatial data processing, error handling, data presentation, and CSV export. It is not commissioned client work.

## Screenshot

_Screenshot placeholder: the app with a search rectangle, demo markers, record count, table, and Download original CSV button._

## Workflow and features

1. Choose Dentists, Pharmacies, Restaurants, Cafés, or Hotels.
2. Move and zoom the OpenStreetMap map.
3. Select the rectangle tool, then drag a rectangle around a small region.
4. Set the maximum results (default 50; allowed range 1–200) and an optional CSV filename.
5. Click **Collect Data**. Moving the map does not send Overpass requests.
6. Inspect clustered markers, popups, search summary, and table; click **Download original CSV**.

A new rectangle replaces the previous one. Use the map's delete tool and its Save action, or **Clear selection**, to remove it. Drawing coordinates arrive as GeoJSON longitude/latitude pairs and are converted to Overpass's south, west, north, east order. Reversed drawing direction is supported; malformed, zero-size, out-of-range, and date-line-crossing rectangles are rejected.

If you change the category or rectangle after collection, the previous result summary remains labeled with its original search. Click Collect Data to update it. The map fits the search rectangle after collection. Ways and relations use their bounding-box centers, which can lie outside the selected region.

After a non-empty search, five summary cards show the number collected, records with any contact information (website, phone, or email), websites present, complete addresses (street, city, and postcode), and potential duplicate groups. Counts and percentages reflect only the collected fields; missing website data does not establish that a business has no website. These summaries do not change records or send requests.

By default, potential duplicate detection compares normalized phone numbers or website domains within 500 metres, or names with at least 90% RapidFuzz ratio similarity within 150 metres. All rules require valid coordinates. Distances use the Haversine formula. Matching pairs are connected into groups, so A–B and B–C count as one group of three affected records, even if A and C do not directly match. Normalization is used only for comparison; source records and CSV exports remain unchanged. This is a possible-duplicate count, not verification: nearby branches can still be flagged, and missing identifiers or coordinates can hide duplicates. Only explicit review decisions exclude records from a separate deduplicated export; the original remains unchanged. Records are never merged.

## Fine-tuning duplicate matching

The left sidebar provides three controls: **Phone / website distance** (25–2,000 metres, default 500), **Similar-name distance** (25–1,000 metres, default 150), and **Minimum name similarity** (70–100%, default 90%). Each rule uses its own distance limit. Larger distances and lower similarity can flag more pairs; location alone never makes a match. **Reset matching defaults** restores the original values.

Changes recalculate groups and evidence locally on existing results, without another API request or modifications to the records. Because group membership may change, all review decisions return to **Keep all records** and any generated deduplicated export is cleared. Confidence scores are unchanged; thresholds control whether a rule qualifies, not how many points it receives.

## Duplicate review and separate export

When groups are detected, **Potential Duplicate Review** shows only flagged records, with one expander per connected group. Record identifiers (`R0001`, etc.) refer to positions in the original search order and remain stable across reruns. Comparison tables show contact information, address, coordinates, completeness, and OSM identity. For larger groups, a pair-level table explains the connecting matches.

Confidence labels are transparent heuristics, not probabilities: a phone match scores 95, a website match 90, and a qualifying name-only match 80. Matching pairs with identical nonmissing OSM type and ID score 100. Scores of at least 90 are **High confidence**; scores of 70–89 are **Possible duplicate**. A group's label reflects its highest-scoring pair, not proof that every record is the same business.

Recommendations count populated name, street, house number, city, postcode, country, phone, website, email, and opening-hours fields. Ties prefer a website, then phone, then the earliest original row. The UI explains this recommendation; it does not remove anything automatically.

- Every group defaults to **Keep all records**.
- Choose **Keep the recommended record only**, or **Keep a specific record** and select its identifier and name.
- **Use all recommendations** selects recommendations and reports the prospective exclusion count. **Reset duplicate decisions** restores keep-all decisions.
- Click **Create deduplicated results** to create a separate DataFrame and review original, reviewed-group, excluded, and final counts.
- **Download original CSV** always exports the unchanged collected records. **Download deduplicated CSV** appears only after creation, with a `_deduplicated.csv` suffix. Both use UTF-8 without an index.

Non-duplicate records are always retained. Decisions survive ordinary Streamlit reruns and are reset when the result dataset changes. Changing a decision hides the previous deduplicated export until it is recreated. The map and main table always show the original data. All review work happens locally, without additional API requests. If there are no duplicate groups, the app reports this and offers only the original export.

## Automatic filling when retaining one duplicate record

Choose **Keep the recommended record only** or **Keep a specific record**, then click **Create deduplicated results**. That retention decision also authorizes filling missing fields in the retained record from the other records in its group. There are no separate confirmation checkboxes or completion buttons. **Keep all records** never fills or changes a group.

The deduplicated CSV includes the filled values. The app shows the number of fields filled, affected records, source identifiers, and skipped conflicts. **Download fill report** provides that provenance. Original collected data stays unchanged. Select **Deduplicated results** in Cleaning or Validation to continue processing the filled result.

Filling copies existing name, address, phone, website, email, and opening-hours values only when all populated donor values agree exactly. Formatting differences are conservatively treated as conflicts. Existing populated values are never overwritten. Invalid phone/email/website donor formats are skipped. Coordinates and OSM identifiers are never copied; no information is inferred or fetched externally.

For a demo, choose R0001 in Group 1 and create deduplicated results. Its missing address and email fields are filled from the other group records where values agree. Recommendations may already contain every available field, so retaining the recommended record can legitimately fill zero fields. Changing a review decision clears generated results until they are recreated.

## Optional data cleaning

After a non-empty search, the sidebar contains tuning options only. Choose any of four **Data Cleaning** options:

- Collapse extra whitespace in business names and address fields, without changing capitalization or punctuation.
- Convert missing values and whitespace-only strings to consistent blanks, preserving valid `0` and `False` values.
- Trim only surrounding whitespace in phone numbers, websites, and emails. Internal phone formatting, URL paths, and email capitalization remain unchanged.
- Convert explicit country aliases to ISO alpha-2 codes. The mapping in `data_cleaning.py` covers GB, US, FR, DE, ES, IT, BE, NL, IE, PT, CH, CA, and AU with selected aliases. Unknown countries remain unchanged.

Click **Create deduplicated results** in the main page after reviewing duplicates. This single action applies your decisions, fills agreed missing fields from confirmed groups, applies the selected cleaning options, and validates the final copy. With no duplicate groups, use **Create processed results** instead. A final table and CSV appear together; the original records and original CSV stay unchanged. No additional API requests are made.

Changing a decision or processing option clears the old output. Click the same create button to regenerate it. No records are removed just because validation flags them.

## Data validation

**Check resulting data for invalid values** in the sidebar enables automatic validation after cleaning (enabled by default). There is no separate validation command or source selector. The main page shows the report alongside the final results.

Only populated values are checked. Missing columns, nulls, empty strings, and whitespace-only values are ignored and never counted as invalid. Completeness remains visible separately in the summary cards.

- Populated latitude and longitude must be finite numeric values, and within −90 to 90 and −180 to 180 respectively. Numeric strings are accepted; booleans are invalid coordinates.
- Email must be a single address with a practical local-part/domain format. This intentionally does not implement every RFC-permitted address, and does not verify delivery.
- Website accepts HTTP(S) URLs or bare domains; missing/unusable hosts, unsupported protocols, whitespace, credentials, and malformed ports are flagged. No DNS or reachability check occurs.
- Phone uses a basic single-number format check: 7–15 digits, optional leading plus, spaces, dots, hyphens, balanced parentheses, and an optional numeric extension. This is not country-specific validation or proof that a number works.
- Missing business names and addresses are not validation errors.

The report shows counts by field and issue type, then only flagged records, with one row per field issue. A record with several issues appears several times; the total flagged-record count counts it once. Identifiers refer to original search order even for filtered or cleaned datasets. **Download validation report** exports UTF-8 CSV without an index. A report with no issues still offers a headers-only CSV.

Changing settings or the result dataset clears the old output and report until you create results again. These are deterministic field checks, not anomaly detection or proof that a business exists or can be contacted.

## Architecture

```text
app.py                          Streamlit UI, session state, 5-minute search cache
categories.py                   Single category-to-OSM-tag mapping
data_summary.py                 Read-only field-presence counts and percentages
data_cleaning.py                Optional formatting on a separate DataFrame
data_completion.py              Retention-authorized fills and provenance on a separate copy
data_validation.py              Read-only populated-value format reports
duplicate_detection.py          Normalization, distance, pair matching, connected groups
duplicate_review.py             Evidence, recommendations, review state, separate results
map_utils.py                    Bounding boxes, area guard, map, popups, filenames
overpass_client.py              Bounded HTTP request and OSM response mapping
sample_data/demo_businesses.json Fictional examples for every category
tests/test_overpass_client.py    Mocked HTTP and mapping tests
tests/test_map_utils.py          Geometry, filenames, map safety tests
tests/test_app.py                Streamlit workflow tests with map component mocked
pyproject.toml                  Python 3.12 and dependency definitions
uv.lock                         Exact dependency lock
.python-version                 Python version selection
requirements.txt                Generated runtime compatibility export
.gitignore
README.md
```

One synchronous POST goes to `https://overpass-api.de/api/interpreter`. Each category maps to a fixed key/value pair. The query selects nodes, ways, and relations and uses `out body center <maximum>` so node coordinates and way/relation centers are available. There is no pagination, automatic retry, or provider fallback.

The table contains business name, selected category, latitude, longitude, street, house number, city, postcode, country, phone, website, email, opening hours, OSM element type and ID, OSM URL, and data source. Primary `phone`, `website`, and `email` tags take precedence over their `contact:*` fallback. Missing values remain blank. Every returned element becomes a row, including unnamed businesses and duplicate representations. Only rows with usable coordinates get markers.

## Local installation and running

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from this directory:

```bash
uv python install 3.12
uv sync
uv run streamlit run app.py
```

Open http://localhost:8501. `uv sync` creates the virtual environment and installs runtime and test dependencies from `uv.lock`.

No credentials or `.env` file are needed. The default maximum rectangle area is **25 km²**. Configure a smaller or otherwise appropriate demonstration limit with a positive finite number:

```bash
MAX_RECTANGLE_AREA_KM2=10 uv run streamlit run app.py
```

Area is calculated on a spherical Earth. The limit is enforced again in the API client, before any request. Keep it conservative: a record cap limits response output, but does not eliminate the server's work finding matches.

`pyproject.toml` and `uv.lock` are authoritative. To update the compatibility export:

```bash
uv export --no-dev --no-hashes --format requirements-txt --output-file requirements.txt
```

## Demo mode

Check **Use demo data**. A predefined rectangle in central London appears. Select any supported category and click **Collect Data** to show its 20 fictional businesses (or fewer if you lower the maximum). Demo collection always uses this fixed region; drawn rectangles do not filter the sample. Clear selection requires a new rectangle or toggling demo mode to restore the predefined selection.

The fixture has 20 records per category (100 total), covering nodes, ways, and relations. It deliberately includes:

- A three-record phone/domain chain, a two-record domain match, and a nearby similar-name pair.
- Two distant branches sharing contact details that remain separate under default thresholds.
- Fully populated control records and `contact:*` fallback fields.
- Extra whitespace and a country alias for cleaning.
- A malformed email, unsupported website scheme, and non-numeric phone that cleaning cannot repair.
- Out-of-range latitude, out-of-range longitude, non-numeric latitude, and missing coordinates.
- Absent and whitespace-only name, address, and contact fields.

For a portfolio walkthrough, keep the default matching settings and request at least 20 records. Open **Demo scenario guide** for record identifiers and expected behavior. Each category yields **3 groups / 7 affected records**; **Use all recommendations** followed by **Create deduplicated results** produces **16 rows**. Validation of the original 20 records yields **8 invalid-field issues** across 6 records; missing values are excluded. Cleaning changes two rows and fixes the whitespace example, without repairing invalid coordinates or malformed contacts. Four records cannot be plotted because their coordinates are invalid or absent; they remain in the table and CSV.

Validation flags issues without removing records. Only explicit duplicate-review decisions exclude records from a separate export. These invalid-coordinate cases are intentionally artificial and do not represent normal OSM output.

 Demo results are labeled prominently; downloads have a `demo_` prefix and a fictional-data source value. OSM IDs and links are blank in demo output to avoid implying fictional records are real listings. Live results use `OpenStreetMap contributors` as their source.

Demo collection makes **no Overpass request**. The interactive map still needs internet access for map tiles and Leaflet assets; this is not a fully offline application.

## Tests

```bash
uv run pytest
```

All HTTP responses are mocked. Tests cover rectangle extraction, reversed coordinates, invalid and oversized regions, category mapping, query generation, node/way/relation mapping, missing fields, fallback tags, result limits, empty searches, timeouts, rate limiting, server failures, malformed responses, safe popups, filenames, caching, and the demo workflow. Automated tests never call the live Overpass API. Browser and any small live smoke checks are performed separately.

## Attribution and fair use

Data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). OSM data is available under the Open Database License; comply with its attribution and other obligations when sharing exports. Tile attribution remains visible on the map, and data attribution appears above it.

Public Overpass capacity is shared and can be unavailable or rate limited. This MVP is intended for occasional, small, manually submitted demonstration searches, not bulk harvesting or a production service. It uses a 25-second server query timeout, 35-second HTTP timeout (10-second connect timeout), a 16 MiB server query-memory ceiling, a configurable area guard, and a 200-element output cap. There are no automatic retries. Identical successful searches, including empty ones, are cached in memory for five minutes, up to 32 cache entries. Failures are never cached as empty results. The cache can be shared across app sessions; it contains only public search data.

Use demo mode for a public portfolio presentation. A public instance is not a guaranteed backend for a deployed commercial application. Respect the [Overpass fair-use guidance](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html) and [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/). Do not remove attribution, bulk-download tiles, or repeatedly submit large searches.

Technical references: [Overpass output modes](https://dev.overpass-api.de/overpass-doc/en/targets/formats.html), [bounding boxes](https://dev.overpass-api.de/overpass-doc/en/full_data/bbox.html), and [streamlit-folium](https://github.com/randyzwitch/streamlit-folium).

## Data availability and MVP limitations

- Volunteer-maintained OSM coverage and contact details vary by area and category; records may be incomplete, outdated, or absent.
- Results are raw OSM elements, not verified leads. A business can appear more than once as different element types.
- No automatic record removal, merging, record verification, anomaly detection, accounts, database, workers, automation platform, or AI features. Duplicate confidence is a matching heuristic, not a record-quality score.
- Only the five mapped categories and one Overpass endpoint are supported.
- Results are not ranked; the record limit can truncate matches. Centers are approximate representative coordinates, not verified entrances.
- No date-line-crossing searches, strict geometry clipping, or partial result export after API failure.
- Data stays in session memory and the brief search cache; CSV downloads are generated in memory. CSV filenames are sanitized, UTF-8 encoded, and omit the DataFrame index.
- Popups escape external text and only make HTTP(S) websites clickable. CSV retains source values; use text-import mode when opening untrusted CSV content in a spreadsheet.

## Planned future work

- Additional optional cleaning transformations
- Further deduplication workflow improvements
- Record verification
- Manual lead selection
- Google Sheets delivery
- Additional permitted providers
