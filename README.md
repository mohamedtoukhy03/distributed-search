# Distributed MPI Search

A high-performance distributed text search application using MPI (Message Passing Interface) that finds all whole-word occurrences of a token in massive text files (up to 10GB).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        File (up to 10GB)                        │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│   Chunk 0    │   Chunk 1    │   Chunk 2    │     Chunk 3       │
│  + ghost ──▸ │  + ghost ──▸ │  + ghost ──▸ │   (last, no ghost)│
├──────────────┼──────────────┼──────────────┼───────────────────┤
│   Rank 0     │   Rank 1     │   Rank 2     │     Rank 3        │
│  KMP Search  │  KMP Search  │  KMP Search  │   KMP Search      │
│  Count \n    │  Count \n    │  Count \n    │   Count \n        │
├──────────────┴──────────────┴──────────────┴───────────────────┤
│              MPI_Exscan (global line offsets)                    │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│  CSV Output  │  CSV Output  │  CSV Output  │   CSV Output      │
└──────────────┴──────────────┴──────────────┴───────────────────┘
```

## Key Design Decisions

| Constraint | Solution |
|---|---|
| 10GB file ≫ RAM | MPI Parallel File I/O (`MPI_File_read_at`) |
| O(1) memory per process | Sliding window buffer (configurable, default 64MB) |
| String matching | KMP algorithm — O(n+m) time, O(m) space |
| Boundary tokens | Ghost zones of `token_len - 1` bytes overlap |
| Global line numbers | `MPI_Exscan` exclusive prefix sum (single pass) |
| Millions of matches | Per-rank CSV files (no `MPI_Gather`) |

## Quick Start

### Prerequisites

- C++17 compiler
- OpenMPI or MPICH (`mpicxx`, `mpirun`)
- Python 3 with `pandas`, `matplotlib`, `numpy` (for benchmarking/verification)

### Build

```bash
make          # Release build (-O3)
make debug    # Debug build (-g -O0)
make clean    # Remove build artifacts
```

### Run

```bash
# Basic search
mpirun -np 4 ./distributed_search \
    --file testdata/test_10240mb.txt \
    --token "distributed" \
    --output-dir ./output

# With terminal output
mpirun -np 8 ./distributed_search \
    --file testdata/test_10240mb.txt \
    --token "distributed" \
    --buffer-size 128 \
    --print-mode sample \
    --sample-size 20 \
    --output-dir ./output
```

### CLI Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--file` | `-f` | (required) | Path to input text file |
| `--token` | `-t` | (required) | Search token (whole word, no spaces) |
| `--buffer-size` | `-b` | `64` | Read buffer size in MB |
| `--print-mode` | `-p` | `none` | Output mode: `none`, `sample`, `all` |
| `--sample-size` | `-s` | `10` | Matches per rank in sample mode |
| `--output-dir` | `-o` | `./output` | Directory for CSV result files |

### Output

Each rank writes its matches to `<output-dir>/matches_rank_<id>.csv`:
```csv
global_line,column
1,15
3,42
157,8
```

## Test Data Generation

Generate synthetic text files to search through using the provided python script:

```bash
# Generate specific file sizes (e.g., 10GB file)
python3 scripts/generate_testdata.py \
    --size 10240 \
    --token "distributed" \
    --output-dir testdata/
```

## Benchmarking

```bash
# Run full benchmark suite (compiles, generates test files, runs experiments)
bash scripts/run_experiments.sh

# Generate plots from existing results
python3 scripts/generate_plots.py \
    --input results/benchmark_results.csv \
    --output-dir results/
```

## Verification

```bash
# Verify MPI output against single-threaded oracle
python3 scripts/verify_search.py \
    --file testdata/test_10240mb.txt \
    --token "distributed" \
    --mpi-output-dir output/ \
    --oracle-output results/check_results.csv
```

## Docker

You can run the entire MPI cluster on a single host using Docker Compose. The `docker-compose.yml` orchestrates a master node and two worker nodes, runs a distributed search, and verifies the output automatically.

### Network Architecture
The Docker setup utilizes two specified bridge networks:
- **`external-gateway`** (`10.10.0.0/16`): Permits external communication, accessible only by the master node.
- **`internal-backend`** (`10.20.0.0/16`, internal-only): An isolated network for private, high-speed MPI communication between the master and worker nodes via SSH and TCP. 

```bash
cd docker
docker compose build
docker compose up
```

## Project Structure

```
distributed-search/
├── include/
│   ├── types.h              # Config, MatchResult, PrintMode
│   ├── cli_parser.h         # CLI argument parsing
│   ├── kmp_search.h         # KMP algorithm interface
│   └── mpi_utils.h          # MPI utilities interface
├── src/
│   ├── main.cpp             # Entry point & orchestration
│   ├── cli_parser.cpp       # getopt_long implementation
│   ├── kmp_search.cpp       # KMP failure table + search
│   └── mpi_utils.cpp        # Chunk calc, I/O, Exscan, output
├── testdata/
│   └── (Test files generated here)
├── scripts/
│   ├── generate_testdata.py # Synthetic test file generator
│   ├── run_experiments.sh   # Benchmark automation
│   ├── generate_plots.py    # Performance visualization
│   └── verify_search.py     # Correctness oracle
├── docker/
│   ├── Dockerfile           # Multi-stage MPI build
│   └── docker-compose.yml   # Docker Compose cluster definition
├── Makefile                 # Build system
├── .gitignore
└── README.md
```

## Algorithm Details

### KMP (Knuth-Morris-Pratt) String Matching

The failure table `F[i]` stores the length of the longest proper prefix of `pattern[0..i]` that is also a suffix. On mismatch at position `j`, we jump to `F[j-1]` instead of restarting, achieving O(n) search time.

### Ghost Zone Math

For rank R with chunk starting at byte `S` and length `L`, and token length `T`:
- **Read region**: `[S, S + L + T - 1)` (clamped to EOF)
- **Ghost zone**: the last `T - 1` bytes overlap with rank R+1
- Matches at offsets `≥ L` are discarded (belong to next rank)

### Global Line Numbering

```
MPI_Exscan(&local_count, &offset, 1, MPI_LONG_LONG, MPI_SUM, ...)

Rank 0: offset = 0          → starts at line 1
Rank 1: offset = count[0]   → starts at line count[0] + 1
Rank 2: offset = count[0]+count[1] → starts at line count[0]+count[1]+1
```
