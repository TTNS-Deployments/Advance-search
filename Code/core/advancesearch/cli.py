"""Command line: ``python -m advancesearch <command>``.

    seed              upload and index the sample documents in Data/sample_docs
    ingest <path>     upload and index one file or every supported file in a folder
    search "<query>"  run a search and print the top documents
    status            list documents and their status
    reindex           rebuild the index and process every document again (text and images)
    reindex --keep-index
                      process every document again without dropping the index first (search keeps working)
    eval              run Data/sample_docs/queries.yaml: top-3 accuracy, precision, unrelated and image queries
    reset --yes       delete every document, the index and the settings overrides
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import get_settings
from .extract import FILE_TYPES


def _service():
    from .ingest import get_document_service

    return get_document_service()


def _upload_paths(paths: list[Path]) -> int:
    from .ingest import UploadError

    service = _service()
    service.index.ensure()
    failures = 0
    for path in paths:
        try:
            with path.open("rb") as fh:
                result = service.upload(path.name, fh, path.stat().st_size, uploaded_by="cli")
        except UploadError as exc:
            print(f"  skipped {path.name}: {exc}")
            continue
        status = service.process(result.name)
        doc = service.get(result.name)
        print(f"  {result.name}: {status} ({doc.chunks if doc else 0} passages, {doc.images if doc else 0} images)"
              f"{' - ' + doc.error if doc and doc.error else ''}")
        failures += status not in ("indexed", "no_text")
    return failures


def _files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() in FILE_TYPES)
    return [path]


def cmd_seed(args) -> int:
    folder = (get_settings().data_dir or Path("Data")) / "sample_docs"
    files = _files(folder)
    if not files:
        print(f"No sample documents in {folder}. Generate them with: python Data/sample_docs/generate.py")
        return 1
    print(f"Seeding {len(files)} sample documents from {folder}")
    return 1 if _upload_paths(files) else 0


def cmd_ingest(args) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Not found: {path}")
        return 1
    return 1 if _upload_paths(_files(path)) else 0


def cmd_search(args) -> int:
    from .search import search

    response = search(args.query, top_n=args.top)
    print(f'{len(response.results)} documents in {response.elapsed_seconds:.2f} s for "{response.query}"')
    for r in response.results:
        snippet = "".join(f"[{t}]" if h else t for t, h in r.snippet)
        exact = ", exact" if r.exact_match else ""
        print(f"{r.rank}. {r.file_name}  {r.match_percent}% ({r.score_source}{exact})  {r.location}\n   {snippet}")
        for image in r.images:
            print(f"   image {image.image_id}  {image.match_percent}%  {image.location}  {image.label}")
    if not response.results:
        print("No matching documents found.")
    if response.hidden:
        print(f"({response.hidden} weaker matches hidden: below {response.min_match_percent}% or below "
              f"{response.relative_cutoff_percent}% of the best match)")
    return 0


def cmd_status(args) -> int:
    docs = _service().list()
    for d in docs:
        print(f"{d.status:<10} {d.chunks:>4} {d.images:>3}  {d.name}{'  - ' + d.error if d.error else ''}")
    print(f"{len(docs)} documents")
    return 0


def cmd_reindex(args) -> int:
    service = _service()
    if args.keep_index:
        service.index.ensure()
        names = [d.name for d in service.list() if d.file_type]
        for name in names:
            service.mark_queued(name)
        print(f"Processing {len(names)} documents again (text and images)")
    else:
        names = service.rebuild_index()
        print(f"Index rebuilt; processing {len(names)} documents")
    for name in names:
        status = service.process(name)
        doc = service.get(name)
        print(f"  {name}: {status} ({doc.chunks if doc else 0} passages, {doc.images if doc else 0} images)")
    return 0


def cmd_eval(args) -> int:
    from .evaluation import evaluate

    report = evaluate()
    for row in report["rows"]:
        mark = "ok " if row["hit"] else "MISS"
        print(f"{mark} {row['kind']:<10} {row['query']!r} -> expected {row['expected']}, got {row['got']}")
    for row in report["unrelated"]:
        print(f"{'ok ' if row['ok'] else 'MISS'} unrelated  {row['query']!r} -> expected nothing, got {row['got']}")
    for row in report["images"]:
        print(f"{'ok ' if row['ok'] else 'MISS'} image      {row['query']!r} -> expected {row['expected']} with "
              f"{row['caption']!r}, got {row['got']} {row['captions']}")
    print(f"Top-3 accuracy: {report['hits']}/{report['total']} ({report['accuracy']:.0%}); precision: "
          f"{report['hits']}/{report['shown']} shown documents are the expected one ({report['precision']:.0%})")
    failed = [r for r in report["unrelated"] + report["images"] if not r["ok"]]
    print(f"Unrelated queries with no result: {sum(r['ok'] for r in report['unrelated'])}/{len(report['unrelated'])}; "
          f"image queries: {sum(r['ok'] for r in report['images'])}/{len(report['images'])}")
    return 0 if report["hits"] == report["total"] and not failed else 1


def cmd_reset(args) -> int:
    if not args.yes:
        print("This deletes every document, the index and the settings overrides. Re-run with --yes.")
        return 1
    from . import factory

    service = _service()
    for doc in service.list():
        service.blobs.delete(service.container, doc.name)
    service.images.clear()
    service.index.reset()
    factory.get_settings_store().reset()
    print("All documents, the index and the settings overrides were deleted.")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="advancesearch", description="Advance Search command line")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="index the sample documents").set_defaults(fn=cmd_seed)
    p = sub.add_parser("ingest", help="index a file or folder")
    p.add_argument("path")
    p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("search", help="search")
    p.add_argument("query")
    p.add_argument("--top", type=int, default=None)
    p.set_defaults(fn=cmd_search)
    sub.add_parser("status", help="list documents").set_defaults(fn=cmd_status)
    p = sub.add_parser("reindex", help="process every document again (text and images)")
    p.add_argument("--keep-index", action="store_true", help="do not drop the index first")
    p.set_defaults(fn=cmd_reindex)
    sub.add_parser("eval", help="top-3 accuracy on the sample queries").set_defaults(fn=cmd_eval)
    p = sub.add_parser("reset", help="delete everything")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_reset)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
