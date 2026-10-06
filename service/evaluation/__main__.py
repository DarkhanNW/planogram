"""Recognition evaluation harness: runs the real pipeline over labelled sets of real Shelf
Photos (people blurred, then Extraction and, where labelled, a Compliance Check) and reports
the MVP recognition metrics against their targets. A measurement, not a test: it exits
non-zero only when a set is invalid or a smoke case breaks.

    python -m evaluation <set-dir> [<set-dir> ...] [--json results.json]

Thresholds and models come from the same PLANOGRAM_* environment variables as the service."""

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from planogram.blurring import OpenCvPersonBlurrer, PersonBlurrer, blur_people
from planogram.catalogue import import_catalogue
from planogram.compliance import check_bay
from planogram.extraction import extract_shelves
from planogram.images import LocalImageStore
from planogram.models import BayLayout, Block, Product, Shelf
from planogram.photos import decode_image
from planogram.recognition import Recognizer
from planogram.repository import Repository, new_id
from planogram.settings import Settings
from planogram.vision import TwoStageRecognizer

from evaluation.labels import Case, InvalidSet, LabelledSet, LabelledShelf, load_set
from evaluation.scoring import Counts, rates, score_deviations, score_extraction, shelf_of


@dataclass
class PhotoResult:
    photo: str
    smoke: bool
    counts: Counts = field(default_factory=Counts)
    broken: str | None = None
    """Why the photo did not run through the pipeline, or why a smoke case is broken."""
    extracted: list[dict[str, Any]] = field(default_factory=list)
    """The extracted Shelves: number, and Blocks with SKU and facing count."""
    deviations: list[dict[str, Any]] | None = None
    """None when the photo has no reference Planogram to check against."""
    compliance_score: float | None = None
    coverage: float | None = None
    seconds: float = 0.0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evaluation", description=__doc__.split("\n\n")[0])
    parser.add_argument("sets", nargs="+", type=Path, help="labelled set directories (see evaluation/README.md)")
    parser.add_argument("--json", type=Path, help="also write the per-photo results and totals here")
    args = parser.parse_args()

    try:
        sets = [load_set(root) for root in args.sets]
    except InvalidSet as e:
        print(f"Invalid labelled set: {e}", file=sys.stderr)
        return 2

    os.environ.setdefault("PLANOGRAM_API_KEY", "evaluation")  # Settings needs one; nothing is served
    settings = Settings.from_env()
    print(", ".join(f"{name} {value}" for name, value in settings_used(settings).items()) + "\n")

    total, results = Counts(), []
    for labelled_set in sets:
        for result in evaluate_set(labelled_set, settings):
            results.append(result)
            print_result(result)
            if not result.smoke:
                total += result.counts

    summary = print_summary(total, sum(1 for r in results if not r.smoke))
    if args.json:
        output = {"settings": settings_used(settings), "totals": summary, "photos": [asdict(r) for r in results]}
        args.json.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"\nResults written to {args.json}")
    if any(r.smoke and r.broken for r in results):
        sys.stdout.flush()
        print("\nA smoke case is broken (see above).", file=sys.stderr)
        return 1
    return 0


def evaluate_set(labelled_set: LabelledSet, settings: Settings) -> list[PhotoResult]:
    """Each set gets a fresh, temporary Product Catalogue imported from its catalogue.csv."""
    with tempfile.TemporaryDirectory(prefix="planogram-eval-") as tmp:
        settings = replace(settings, db_path=Path(tmp) / "planogram.sqlite", image_dir=Path(tmp) / "images")
        repo = Repository(settings.db_path)
        try:
            images = LocalImageStore(settings.image_dir)
            report = import_catalogue(repo, images, labelled_set.catalogue_csv, labelled_set.catalogue_files)
            for failure in report.failed:
                print(f"{labelled_set.root}: catalogue row {failure.row} ({failure.sku}) not imported: {failure.reason}")
            products = repo.list_products()
            recognizer = TwoStageRecognizer(settings, images)
            blurrer = OpenCvPersonBlurrer()
            return [evaluate_case(case, settings, recognizer, blurrer, products) for case in labelled_set.cases]
        finally:
            repo.close()


def evaluate_case(
    case: Case, settings: Settings, recognizer: Recognizer, blurrer: PersonBlurrer, products: list[Product]
) -> PhotoResult:
    labels = case.labels
    result = PhotoResult(photo=str(case.photo), smoke=labels.smoke)
    started = time.perf_counter()
    try:
        original = decode_image(case.photo.read_bytes())
        image = blur_people(original, blurrer.find_people(original))
        extracted = extract_shelves(recognizer, image, products)
        result.extracted = [s.model_dump(include={"number": True, "blocks": {"__all__": {"sku", "facings"}}}) for s in extracted]
        if labels.shelves is not None:
            result.counts += score_extraction(labels.shelves, extracted)
        if labels.reference is not None:
            # The Bay number plays no part in the comparison; a labelled photo shows one Bay.
            planned = BayLayout(bay=1, shelf_photo_id=None, shelves=planned_shelves(labels.reference.shelves))
            comparison = check_bay(recognizer, image, planned, products, settings.verification_threshold)
            result.deviations = [
                {"kind": d.kind.value, "sku": d.sku, "shelf": shelf_of(d), "facings": d.facings,
                 "confidence": round(d.confidence, 3)}
                for d in comparison.deviations
            ]
            result.compliance_score, result.coverage = comparison.compliance_score, comparison.coverage
            result.counts += score_deviations(labels.reference.deviations, comparison.deviations)
        if labels.smoke and not any(s.blocks for s in extracted):
            result.broken = "no Blocks extracted"
    except Exception as e:  # noqa: BLE001 - a broken photo is reported, not fatal to the run
        result.broken = f"{type(e).__name__}: {e}"
    result.seconds = round(time.perf_counter() - started, 1)
    return result


def planned_shelves(shelves: list[LabelledShelf]) -> list[Shelf]:
    return [
        Shelf(number=s.number, blocks=[Block(id=new_id(), sku=b.sku, facings=b.facings) for b in s.blocks])
        for s in shelves
    ]


def print_result(result: PhotoResult) -> None:
    print(f"{result.photo}{' [smoke]' if result.smoke else ''} ({result.seconds} s)")
    if result.broken:
        print(f"  BROKEN: {result.broken}")
    for shelf in sorted(result.extracted, key=lambda s: s["number"]):
        blocks = ", ".join(f"{b['sku'] or 'Unknown'} x{b['facings']}" for b in shelf["blocks"])
        print(f"  Shelf {shelf['number']}: {blocks or '(empty)'}")
    if result.deviations is not None:
        score = result.compliance_score
        print(f"  Compliance Score {'n/a' if score is None else f'{score:.0%}'}, Coverage {result.coverage:.0%}")
        for d in result.deviations:
            print(f"  {d['kind']}: {d['sku'] or 'Unknown'} on Shelf {d['shelf']} ({d['facings']} Facings)")
    c = result.counts
    if not result.smoke and not result.broken:
        print(
            f"  identified {c.identified_blocks}/{c.labelled_blocks} Blocks, confidently wrong "
            f"{c.confidently_wrong}/{c.named_blocks}, exact facing count {c.exact_facing_counts}/"
            f"{c.identified_blocks}, Deviations matched {c.matched_deviations} of {c.reported_deviations} "
            f"reported / {c.expected_deviations} expected"
        )
    print()


def print_summary(total: Counts, photos: int) -> dict[str, Any]:
    print(f"MVP targets over {photos} labelled photo(s), smoke cases excluded:")
    summary: dict[str, Any] = {"photos": photos, "counts": asdict(total), "metrics": {}}
    for metric, (value, measured_on) in rates(total).items():
        target = f"{'>=' if metric.higher_is_better else '<='} {metric.target:.0%}"
        met = None if value is None else metric.met(value)
        verdict = "n/a" if met is None else "MET" if met else "MISSED"
        shown = "n/a" if value is None else f"{value:.1%}"
        print(f"  {metric.name:<22} {shown:>7}  target {target:<6} {verdict:<6} (of {measured_on})")
        summary["metrics"][metric.name] = {"value": value, "target": metric.target, "met": met, "of": measured_on}
    return summary


def settings_used(settings: Settings) -> dict[str, Any]:
    return {
        "detector_model": settings.detector_model, "embedding_model": settings.embedding_model,
        "match_threshold": settings.match_threshold, "match_margin": settings.match_margin,
        "detection_threshold": settings.detection_threshold, "verification_threshold": settings.verification_threshold,
    }


if __name__ == "__main__":
    sys.exit(main())
