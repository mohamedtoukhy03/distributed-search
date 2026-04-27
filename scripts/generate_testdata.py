import argparse
import os
import random
import sys
import time
import io


# Common English words
COMMON_WORDS = [
    # Short
    "the", "a", "an", "is", "it", "to", "in", "on", "at", "by",
    "or", "as", "if", "we", "do", "no", "up", "so", "of", "my",
    # Medium
    "and", "for", "but", "not", "you", "all", "can", "had", "her",
    "was", "one", "our", "out", "are", "has", "his", "how", "its",
    "may", "new", "now", "old", "see", "way", "who", "did", "get",
    "let", "say", "she", "too", "use", "run", "set", "try", "ask",
    # Longer common
    "that", "with", "have", "this", "will", "your", "from", "they",
    "been", "call", "come", "each", "make", "like", "long", "look",
    "many", "some", "than", "them", "then", "what", "when", "more",
    "over", "such", "take", "year", "also", "back", "work", "just",
    "only", "very", "even", "most", "much", "well", "here", "must",
]

# Technical / computing words 
TECH_WORDS = [
    "algorithm", "search", "compute", "parallel", "process", "system",
    "network", "buffer", "memory", "thread", "mutex", "queue", "binary",
    "tree", "graph", "node", "edge", "path", "data", "file", "input",
    "output", "stream", "byte", "chunk", "block", "index", "array",
    "list", "stack", "hash", "table", "key", "value", "sort", "merge",
    "split", "join", "filter", "map", "reduce", "fold", "scan", "find",
    "match", "replace", "pattern", "performance", "benchmark", "optimize",
    "cache", "latency", "throughput", "bandwidth", "scalable", "resilient",
    "robust", "cluster", "partition", "topology", "protocol", "interface",
    "module", "function", "variable", "constant", "iterator", "pointer",
    "reference", "compiler", "debugger", "profiler", "scheduler", "kernel",
    "driver", "firmware", "middleware", "framework", "library", "package",
    "container", "instance", "object", "class", "method", "property",
    "attribute", "parameter", "argument", "exception", "handler", "callback",
    "pipeline", "workflow", "daemon", "socket", "packet", "payload",
]

# Words that contain common tokens as substrings 
TRAP_WORDS = {
    "distributed": [
        "redistributed", "undistributed", "distributedness",
        "predistributed", "nondistributed",
    ],
    "search": [
        "researching", "researcher", "searchable", "unsearchable",
    ],
    "hello": [
        "othello", "hellos", "helloed",
    ],
    "test": [
        "testing", "tested", "tester", "contest", "detest", "attest",
        "protested", "untested", "testosterone",
    ],
    "data": [
        "database", "dataset", "metadata", "datagram",
    ],
}

# Sentence starters for variety
STARTERS = [
    "The", "A", "This", "Each", "Every", "Some", "Many", "All",
    "Our", "Their", "No", "Any",
]

# Line ending punctuation
ENDINGS = [".", ".", ".", ".", "!", "?", ".", ";", "."]


def parse_args():
    parser = argparse.ArgumentParser(
        description='Generate synthetic test files for distributed MPI search benchmarking',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --size 1 10 100
  %(prog)s --size 10240 --token hello --frequency 0.05
  %(prog)s --size 1 --seed 42 --edge-cases
        """,
    )
    parser.add_argument(
        '--size', type=int, nargs='+', default=[1, 10, 100],
        help='File sizes to generate in MB (default: 1 10 100). Use 10240 for 10GB.')
    parser.add_argument(
        '--token', type=str, default='distributed',
        help='Token to plant in the text (default: distributed)')
    parser.add_argument(
        '--output-dir', type=str, default='testdata',
        help='Output directory (default: testdata/)')
    parser.add_argument(
        '--frequency', type=float, default=0.02,
        help='Probability of inserting the token per word slot (default: 0.02 = ~2%%)')
    parser.add_argument(
        '--seed', type=int, default=None,
        help='Random seed for reproducibility (default: random)')
    parser.add_argument(
        '--edge-cases', action='store_true',
        help='Include extra edge-case lines (token at boundaries, etc.)')
    parser.add_argument(
        '--trap-words', action='store_true', default=True,
        help='Include words containing the token as a substring (default: true)')
    parser.add_argument(
        '--no-trap-words', action='store_false', dest='trap_words',
        help='Disable trap words')
    parser.add_argument(
        '--write-buffer', type=int, default=1,
        help='Write buffer size in MB for batched I/O (default: 1)')

    return parser.parse_args()


def build_word_pool(token, include_traps=True):
    pool = COMMON_WORDS + TECH_WORDS

    if include_traps and token in TRAP_WORDS:
        pool.extend(TRAP_WORDS[token])

    return pool


def format_size(size_bytes):
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"


def print_progress(written, target, start_time, token_count, line_count):
    elapsed = time.time() - start_time
    pct = written / target * 100

    if elapsed > 0:
        speed = written / elapsed  # bytes per second
        remaining = (target - written) / speed if speed > 0 else 0
        speed_str = f"{format_size(int(speed))}/s"
        eta_str = format_time(remaining)
    else:
        speed_str = "..."
        eta_str = "..."

    bar_width = 40
    filled = int(bar_width * written / target)
    bar = '█' * filled + '░' * (bar_width - filled)

    sys.stdout.write(
        f"\r    [{bar}] {pct:5.1f}% | "
        f"{format_size(written)}/{format_size(target)} | "
        f"{speed_str} | ETA: {eta_str} | "
        f"{line_count:,} lines, ~{token_count:,} tokens"
    )
    sys.stdout.flush()


def generate_line(rng, word_pool, token, frequency, force_token_start=False,
                  force_token_end=False, force_multi_token=False):
    num_words = rng.randint(5, 20)
    words = []

    for i in range(num_words):
        if force_token_start and i == 0:
            words.append(token)
        elif force_token_end and i == num_words - 1:
            words.append(token)
        elif force_multi_token and i in (1, num_words - 2):
            words.append(token)
        elif rng.random() < frequency:
            words.append(token)
        else:
            words.append(rng.choice(word_pool))

    if rng.random() < 0.3:
        words[0] = rng.choice(STARTERS)

    line = ' '.join(words) + rng.choice(ENDINGS)

    return line + '\n'


def generate_edge_case_lines(token):
    lines = []

    # Token at start
    lines.append(f"{token} is a concept used in computing.\n")

    # Token at end
    lines.append(f"The system is fully {token}.\n")

    # Token alone on a line
    lines.append(f"{token}\n")

    # Multiple tokens on one line
    lines.append(f"The {token} system uses {token} computing for {token} processing.\n")

    # Token with surrounding punctuation
    lines.append(f"Is it {token}? Yes, it's {token}!\n")
    lines.append(f"({token}) [{token}] \"{token}\"\n")

    # Token adjacent to commas and periods
    lines.append(f"We use {token}, which is {token}. Also {token}; great.\n")

    # Empty line (tests newline counting)
    lines.append("\n")

    # Very long line with token in the middle
    filler = "word " * 100
    lines.append(f"{filler}{token} {filler}\n")

    # Lines with trap words (should NOT match)
    if token in TRAP_WORDS:
        for trap in TRAP_WORDS[token]:
            lines.append(f"The system was {trap} across the network.\n")

    # Token immediately after newline (tests column=1)
    lines.append(f"{token} starts this line right at column one.\n")

    return lines


def generate_file(filepath, size_mb, token, frequency, rng,
                  include_edge_cases=False, include_traps=True,
                  write_buffer_mb=1):
    target_bytes = size_mb * 1024 * 1024
    word_pool = build_word_pool(token, include_traps)
    buffer_limit = write_buffer_mb * 1024 * 1024  # flush threshold

    written = 0
    token_count = 0
    line_count = 0
    last_progress = 0

    # Determine if we should show progress (for files >= 10 MB)
    show_progress = size_mb >= 10
    progress_interval = max(target_bytes // 200, 1024 * 1024)  # Update every 0.5%

    print(f"  Generating {filepath} ({format_size(target_bytes)})...")
    start_time = time.time()

    with open(filepath, 'w', buffering=buffer_limit) as f:
        # Use a StringIO buffer for batched writes
        batch = io.StringIO()
        batch_size = 0

        # Insert edge case lines at the beginning
        if include_edge_cases:
            for line in generate_edge_case_lines(token):
                batch.write(line)
                batch_size += len(line)
                line_count += 1
                # Quick token count
                for w in line.split():
                    if w.strip('.,;:!?()[]"\'') == token:
                        token_count += 1

        # Main content generation loop
        while written + batch_size < target_bytes:
            # Every ~1000 lines, insert a special edge-case line
            if include_edge_cases and line_count % 1000 == 0 and line_count > 0:
                line = generate_line(rng, word_pool, token, frequency,
                                     force_token_start=True)
            elif include_edge_cases and line_count % 1500 == 0 and line_count > 0:
                line = generate_line(rng, word_pool, token, frequency,
                                     force_multi_token=True)
            elif rng.random() < 0.005:
                line = "\n"
            else:
                line = generate_line(rng, word_pool, token, frequency)

            batch.write(line)
            line_len = len(line)
            batch_size += line_len
            line_count += 1

            # Count tokens
            for w in line.split():
                stripped = w.strip('.,;:!?()[]"\'')
                if stripped == token:
                    token_count += 1

            # Flush batch when it reaches the buffer limit
            if batch_size >= buffer_limit:
                f.write(batch.getvalue())
                written += batch_size
                batch = io.StringIO()
                batch_size = 0

                # Print progress for large files
                if show_progress and written - last_progress >= progress_interval:
                    print_progress(written, target_bytes, start_time,
                                   token_count, line_count)
                    last_progress = written

        # Flush remaining data
        if batch_size > 0:
            f.write(batch.getvalue())
            written += batch_size

    elapsed = time.time() - start_time
    actual_size = os.path.getsize(filepath)

    # Clear progress line
    if show_progress:
        sys.stdout.write('\r' + ' ' * 120 + '\r')
        sys.stdout.flush()

    print(f"    ✓ {format_size(actual_size)} written")
    print(f"    → {line_count:,} lines, ~{token_count:,} token occurrences")
    print(f"    → Generated in {format_time(elapsed)} "
          f"({format_size(int(actual_size / elapsed))}/s)")


def main():
    args = parse_args()

    # Initialize RNG
    if args.seed is not None:
        rng = random.Random(args.seed)
        print(f"Using seed: {args.seed}")
    else:
        seed = random.randint(0, 2**32 - 1)
        rng = random.Random(seed)
        print(f"Using random seed: {seed}")

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Compute total size for time estimate
    total_mb = sum(args.size)
    total_str = format_size(total_mb * 1024 * 1024)

    print("")
    print("============================================================")
    print("  Test Data Generator — Distributed MPI Search")
    print("============================================================")
    print(f"  Token:         \"{args.token}\"")
    print(f"  Frequency:     {args.frequency:.2%} per word slot")
    print(f"  Sizes:         {[f'{s} MB' for s in args.size]}")
    print(f"  Total:         {total_str}")
    print(f"  Output dir:    {args.output_dir}")
    print(f"  Edge cases:    {'yes' if args.edge_cases else 'no'}")
    print(f"  Trap words:    {'yes' if args.trap_words else 'no'}")
    print(f"  Write buffer:  {args.write_buffer} MB")
    print("============================================================")
    print("")

    overall_start = time.time()

    for i, size_mb in enumerate(args.size):
        filename = f"test_{size_mb}mb.txt"
        filepath = os.path.join(args.output_dir, filename)

        print(f"[{i+1}/{len(args.size)}] ", end="")
        generate_file(
            filepath=filepath,
            size_mb=size_mb,
            token=args.token,
            frequency=args.frequency,
            rng=rng,
            include_edge_cases=args.edge_cases,
            include_traps=args.trap_words,
            write_buffer_mb=args.write_buffer,
        )
        print("")

    overall_elapsed = time.time() - overall_start

    print("============================================================")
    print(f"  All test files generated in {format_time(overall_elapsed)}!")
    print("============================================================")
    print("")

    # Summary table
    print(f"  {'File':<30} {'Size':>14} {'Path'}")
    print(f"  {'─' * 30} {'─' * 14} {'─' * 40}")
    for size_mb in args.size:
        filename = f"test_{size_mb}mb.txt"
        filepath = os.path.join(args.output_dir, filename)
        actual_size = os.path.getsize(filepath)
        print(f"  {filename:<30} {format_size(actual_size):>14}  {filepath}")
    print("")


if __name__ == '__main__':
    main()
