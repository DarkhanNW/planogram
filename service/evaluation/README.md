# Recognition evaluation harness

Runs the real recognition pipeline over a labelled set of real Shelf Photos and reports the
MVP recognition metrics against their targets. Use it to measure every change to the models
or thresholds. It is a measurement, not a test: `pytest` runs only the unit tests of its
scoring (`tests/test_scoring.py`), never the harness itself. It needs the vision dependencies
(`pip install -e ".[dev,vision]"`).

```sh
cd service
.venv/Scripts/python -m evaluation path/to/set [path/to/another-set ...] [--json results.json]
```

For each photo it prints the extracted Shelves, with empty space shown as `(empty)` runs,
and, for photos with a reference Planogram, the Compliance Check's Deviations, Compliance
Score and Coverage. Then it prints the pooled metrics. `--json` also saves the settings,
per-photo results and totals, so you can compare runs. Thresholds and models come from the
same `PLANOGRAM_*` environment variables as the service (see the top-level README), so you
can try a change without editing code:

```sh
PLANOGRAM_MATCH_THRESHOLD=0.75 .venv/Scripts/python -m evaluation path/to/set
```

Run it from `service/`, because the `evaluation` package is not installed. The exit code is 0 after a measurement, whether the targets are met or not. It is 1 when a
smoke case is broken and 2 when a labelled set is invalid.

## What runs

Each photo goes through the service's own pipeline:

1. The Person Blurrer blurs it.
2. Extraction runs on the blurred photo, matching against the whole Product Catalogue.
3. If the photo has a reference Planogram, a Compliance Check against it follows. The
   reference's Products are matched first and the rest of the Product Catalogue is the fallback.

Each set gets a fresh temporary Product Catalogue, imported from its own `catalogue.csv`.

## Smoke test

`tests/fixtures/mockup/` is a smoke set: a mock-up grocery Bay, fully stocked and partly
emptied, run with the real Recognizer to catch gross breakage of the detector, Shelf
assignment, matching and Layout Builder. It is not a measurement.

```sh
cd service
.venv/Scripts/python -m evaluation tests/fixtures/mockup
```

Read the printed Draft Planograms by eye. The exit code is 1 if either photo raises an error,
finds no Shelves or extracts no Blocks. `source/` holds the original two-Bay images. The
photos are their left Bays, and the catalogue images are single Facings cropped from
`source/full.jpeg`. Only those seven Products are in the catalogue, so everything else
should come out as Unknown Product or, for a lookalike such as
Barilla Fusilli, as the catalogued Product it resembles.

## Labelled set format

```
my-set/
  catalogue.csv          # the Product Catalogue: same format as the service's bulk import
  catalogue/             # the reference images named in catalogue.csv
    coke-330-front.jpg
  photos/
    store1-drinks-bay2-2026-10-01.jpg     # a Shelf Photo of one whole Bay (.jpg .jpeg .png .webp)
    store1-drinks-bay2-2026-10-01.json    # its labels: same name, .json
```

`catalogue.csv` has the columns `sku`, `name` and `images`. `images` holds the reference
image file names, separated by `;`.

Each photo's `.json` holds its labels:

```json
{
  "shelves": [
    { "number": 1, "blocks": [ { "sku": "COKE-330", "facings": 4 }, { "sku": null, "facings": 1 } ] },
    { "number": 2, "blocks": [ { "sku": "FANTA-330", "facings": 6 } ] }
  ],
  "reference": {
    "shelves": [
      { "number": 1, "blocks": [ { "sku": "COKE-330", "facings": 4 }, { "sku": "SPRITE-330", "facings": 2 } ] },
      { "number": 2, "blocks": [ { "sku": "FANTA-330", "facings": 6 } ] }
    ],
    "deviations": [
      { "kind": "Missing", "sku": "SPRITE-330", "shelf": 1 },
      { "kind": "Unexpected", "sku": null, "shelf": 1 }
    ]
  }
}
```

- `shelves` is required. It is the hand-checked Planogram of the Bay as it stands in the
  photo. Shelves are counted from the bottom (1 is the bottom Shelf), and Blocks run in
  order from the left, each with its facing count. Give `"sku": null` for a product that
  is not in the catalogue, because the right answer for it is an Unknown Product. Since
  nothing says two such Facings are the same product, label each one as its own Block with
  1 Facing. Leave empty Shelf space out. A Shelf with nothing on it can be left out or
  given with no Blocks.
- `reference` is optional. Its `shelves` are a Planogram to run a Compliance Check against,
  in the same form. Its `deviations` list every Deviation the check should report; give
  `[]` if none. A Deviation has a `kind` (`Gap`, `Missing`, `Wrong Facing Count`,
  `Misplaced` or `Unexpected`), a `sku` (the planned Product, or for Unexpected what is on
  the Shelf, `null` for an Unknown Product) and a `shelf`. The shelf is the planned Shelf,
  or for Unexpected the Shelf it was found on. Follow "one cause, one Deviation" as the
  glossary defines the kinds. A planned Product whose space is taken by something else is
  one Missing, plus one Unexpected for what took the space if that is not in the reference.
  A planned Block's empty space split into separate runs by other Shelf contents, such as an
  Unknown Facing, is one Gap per run, as the Compliance Check reports it: give one expected
  Gap for each run.
- `"smoke": true` marks a smoke case, such as the mock-up Bay (see Smoke test). It runs
  through the pipeline but is left out of the metrics, and `shelves` may be left out. It is
  broken when it raises an error, finds no Shelves or extracts no Blocks.

## Metrics

The counts are pooled over all labelled photos, smoke cases excluded, and each rate is
taken over the pooled counts. The output shows what each rate was measured on.

On each Shelf, the extracted Blocks are paired in order with the labelled Blocks of the
same Product (or both Unknown Product). The pairing used is the longest one possible.

| Metric | Target | Definition |
| --- | --- | --- |
| Block identification | >= 90% | Paired labelled Blocks / labelled Blocks |
| Confidently wrong | <= 2% | Extracted Blocks naming a Product the labelled Shelf does not hold at that place / extracted Blocks naming a Product |
| Exact facing count | >= 85% | Paired Blocks with the labelled facing count / paired Blocks |
| Deviation precision | >= 90% | Reported Deviations matching an expected one / reported Deviations |
| Deviation recall | >= 80% | Expected Deviations matched / expected Deviations |

- "At that place" means the Block is not a fragment. A fragment is an unpaired Block split
  off a paired Block by Unknown Facings: it names the same Product, sits next to that Block
  with only Unknown Products (or other fragments) between them, and the paired Block is
  short of its labelled Facings. A fragment costs the facing count, not identity. A Block
  misread as its neighbour's Product is not a fragment, so it is confidently wrong.
- Exact facing count is measured on identified Blocks only. A Block the Recognizer did not
  identify has no facing count to compare, and it already counts against Block
  identification.
- Shelves are compared by number, counted from the bottom. If the Recognizer misses a Shelf,
  every Shelf above it is numbered one lower. That whole Bay then scores as unidentified and
  confidently wrong, so check the printed Shelves before reading a bad photo as a
  matching problem.
- An Unknown Product is never confidently wrong. It costs identification only.
- Deviations are matched one to one on kind, Product and Shelf. Every expected and every
  reported Deviation counts, and each reported Deviation matches at most one expected
  Deviation of the same kind, Product and Shelf. Reporting one cause as several Deviations
  therefore costs precision, and reporting fewer than expected costs recall.
- Unverified areas are not Deviations, so they never count against precision. They can
  cost recall.
