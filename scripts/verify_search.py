import argparse
import os
import re
import csv
import glob
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description='Verify MPI search results against single-threaded oracle')
    parser.add_argument('--file', required=True,
                        help='Path to the input text file')
    parser.add_argument('--token', required=True,
                        help='Search token (whole word)')
    parser.add_argument('--mpi-output-dir', required=True,
                        help='Directory containing matches_rank_*.csv files')
    parser.add_argument('--oracle-output', default='check_results.csv',
                        help='Path to save oracle results CSV')
    return parser.parse_args()


def oracle_search(file_path, token):
    results = []
    pattern = re.compile(r'\b' + re.escape(token) + r'\b')

    with open(file_path, 'r', errors='replace') as f:
        for line_num, line in enumerate(f, start=1):
            for match in pattern.finditer(line):
                column = match.start() + 1
                results.append((line_num, column))

    return results


def load_mpi_results(mpi_output_dir):
    results = []
    pattern = os.path.join(mpi_output_dir, 'matches_rank_*.csv')
    csv_files = sorted(glob.glob(pattern))

    if not csv_files:
        print(f"[WARN] No MPI output files found matching: {pattern}")
        return results

    for csv_file in csv_files:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                line = int(row['global_line'])
                col = int(row['column'])
                results.append((line, col))

    # Sort by (line, column) for comparison
    results.sort()
    return results


def compare_results(oracle, mpi):
    if oracle == mpi:
        return True, "All results match perfectly."

    details = []

    # Find differences
    oracle_set = set(oracle)
    mpi_set = set(mpi)

    missing_from_mpi = oracle_set - mpi_set
    extra_in_mpi = mpi_set - oracle_set

    if missing_from_mpi:
        details.append(f"  Missing from MPI output ({len(missing_from_mpi)} matches):")
        for line, col in sorted(missing_from_mpi)[:20]:  # Show first 20
            details.append(f"    Line {line}, Column {col}")
        if len(missing_from_mpi) > 20:
            details.append(f"    ... and {len(missing_from_mpi) - 20} more")

    if extra_in_mpi:
        details.append(f"  Extra in MPI output ({len(extra_in_mpi)} matches):")
        for line, col in sorted(extra_in_mpi)[:20]:
            details.append(f"    Line {line}, Column {col}")
        if len(extra_in_mpi) > 20:
            details.append(f"    ... and {len(extra_in_mpi) - 20} more")

    # Check for duplicates in MPI output
    if len(mpi) != len(mpi_set):
        dup_count = len(mpi) - len(mpi_set)
        details.append(f"  Duplicates in MPI output: {dup_count}")

    return False, "\n".join(details)


def main():
    args = parse_args()

    print("")
    print("============================================================")
    print("  Oracle Verification")
    print("============================================================")
    print(f"  File:  {args.file}")
    print(f"  Token: \"{args.token}\"")
    print(f"  MPI:   {args.mpi_output_dir}")
    print("")

    print("  Running single-threaded oracle search...")
    oracle_results = oracle_search(args.file, args.token)
    print(f"  Oracle found {len(oracle_results)} matches.")

    os.makedirs(os.path.dirname(args.oracle_output) or '.', exist_ok=True)
    with open(args.oracle_output, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['global_line', 'column'])
        for line, col in oracle_results:
            writer.writerow([line, col])
    print(f"  Oracle results saved to {args.oracle_output}")

    print("  Loading MPI results...")
    mpi_results = load_mpi_results(args.mpi_output_dir)
    print(f"  MPI found {len(mpi_results)} matches.")

    print("")
    is_match, details = compare_results(oracle_results, mpi_results)

    if is_match:
        print("pass")
        print(f"Verified {len(oracle_results):>8} matches.")
    else:
        print("fail")
        print("MPI results differ from oracle.")
        print("")
        print("  Details:")
        print(details)
        sys.exit(1)

    print("")
    print("============================================================")


if __name__ == '__main__':
    main()
