from __future__ import annotations

import argparse
from pathlib import Path

from .models import VendorProfile
from .scanner import scan_archive, summary_to_dict, write_json_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edefter-denetim")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Klasor tarar ve ozet cikarir.")
    scan_parser.add_argument("root", type=Path, help="Tarama yapilacak klasor")
    scan_parser.add_argument(
        "--profile",
        choices=[item.value for item in VendorProfile],
        default=VendorProfile.AUTO.value,
        help="Arsiv profili",
    )
    scan_parser.add_argument("--json-out", type=Path, help="JSON ozet cikti yolu")
    return parser


def print_summary(summary_dict: dict[str, object]) -> None:
    print(f"Root: {summary_dict['root_path']}")
    print(f"Profile: {summary_dict['profile']}")
    print(f"Files: {summary_dict['scanned_files']} scanned / {summary_dict['total_files']} total")
    print(f"Findings: {len(summary_dict['findings'])}")
    for finding in summary_dict["findings"][:20]:
        print(f"  - {finding}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "scan":
        summary = scan_archive(args.root, VendorProfile(args.profile))
        summary_dict = summary_to_dict(summary)
        print_summary(summary_dict)
        if args.json_out:
            write_json_summary(summary, args.json_out)
            print(f"JSON saved: {args.json_out}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
