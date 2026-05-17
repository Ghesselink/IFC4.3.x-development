from __future__ import annotations

import argparse
import cProfile
import io
from pathlib import Path
import pstats

from .builder import StaticSiteBuilder
from .config import BuildConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the IFC static HTML site.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for the generated site. Defaults to output/html under the repo root.",
    )
    parser.add_argument(
        "-j",
        "--threads",
        type=int,
        default=None,
        help="Number of worker processes used to render HTML pages. Defaults to up to 4 cores.",
    )
    parser.add_argument(
        "--sample-percent",
        type=float,
        default=None,
        help="Render only a deterministic sample of generated pages. Static pages are always included.",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Run the build under cProfile. This forces in-process rendering so the profile captures real work.",
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        default=None,
        help="Optional path to write the cProfile summary report.",
    )
    parser.add_argument(
        "--shard",
        type=str,
        default=None,
        help="Render only a fraction of content pages, format 'i/N' (0-indexed i).",
    )
    parser.add_argument(
        "--collector-output",
        type=Path,
        default=None,
        help="After content pass, dump collector payloads to this JSON file and exit.",
    )
    parser.add_argument(
        "--collector-inputs",
        type=str,
        default=None,
        help="Comma-separated paths to collector JSON files from other shards, merged before listing pass.",
    )
    parser.add_argument(
        "--skip-content",
        action="store_true",
        help="Skip the content pass (assemble job uses this — content already rendered by shards).",
    )
    args = parser.parse_args()

    # Fail fast on malformed --shard values. Without this, "i/N" pairs outside
    # the valid range (e.g. a typo'd CI matrix index like 7/4 or 4/4) silently
    # render zero pages — the shard exits 0 with an empty collector and the
    # assemble step happily merges nothing.
    if args.shard is not None:
        parts = args.shard.split("/")
        if len(parts) != 2:
            parser.error(f"--shard must be 'i/N' with exactly one slash (got {args.shard!r})")
        try:
            shard_i, shard_n = int(parts[0]), int(parts[1])
        except ValueError:
            parser.error(f"--shard must be 'i/N' with integer i and N (got {args.shard!r})")
        if shard_n < 1 or shard_i < 0 or shard_i >= shard_n:
            parser.error(f"--shard {shard_i}/{shard_n}: need 0 <= i < N and N >= 1")

    repo_root = Path(__file__).resolve().parents[3]
    if args.profile:
        if args.profile_output is None:
            args.profile_output = repo_root / "output" / "profile" / "cprofile-summary.txt"

    collector_inputs = (
        [Path(p.strip()) for p in args.collector_inputs.split(",") if p.strip()]
        if args.collector_inputs
        else None
    )
    config = BuildConfig.from_repo_root(
        repo_root,
        args.output,
        args.threads,
        args.sample_percent,
        args.profile,
        shard=args.shard,
        collector_output=args.collector_output,
        collector_inputs=collector_inputs,
        skip_content=args.skip_content,
    )
    builder = StaticSiteBuilder(config)

    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()
        summary = builder.build()
        profiler.disable()

        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream).sort_stats("cumulative")
        stats.print_stats(50)
        report = stream.getvalue()

        if args.profile_output is not None:
            args.profile_output.parent.mkdir(parents=True, exist_ok=True)
            args.profile_output.write_text(report, encoding="utf-8")

        print(report)
    else:
        summary = builder.build()

    print(f"Output: {config.output_dir}")
    print(f"Errors: {summary['errors']}")
    print(f"Written: {summary['written']}")


if __name__ == "__main__":
    main()
