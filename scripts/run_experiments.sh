set -euo pipefail

# Dynamically load MPI paths only if mpirun is not already in PATH (e.g. for Ubuntu/Debian)
if ! command -v mpirun &> /dev/null; then
    if [ -f /etc/profile.d/modules.sh ]; then
        source /etc/profile.d/modules.sh
        module load mpi/openmpi-x86_64 2>/dev/null || true
    fi
    export PATH="/usr/lib64/openmpi/bin:/usr/lib64/mpich/bin:$PATH"
fi


# ── Configuration ────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BINARY="$PROJECT_DIR/distributed_search"
TESTDATA_DIR="$PROJECT_DIR/testdata"
OUTPUT_DIR="$PROJECT_DIR/output"
RESULTS_DIR="$PROJECT_DIR/results"
RESULTS_CSV="$RESULTS_DIR/benchmark_results.csv"
TOKEN="distributed"
PROCESS_COUNTS=(2 4 8)
FILE_SIZES_MB=(10240)
REPETITIONS=5

# ── Colors for pretty output ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' 

log_info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Create directories ──────────────────────────────────────────────────────
mkdir -p "$TESTDATA_DIR" "$OUTPUT_DIR" "$RESULTS_DIR"

echo ""
echo "============================================================"
echo "  Distributed MPI Search — Benchmark Suite"
echo "============================================================"
echo ""

# Log system information
log_info "Logging system information..."

SYSINFO_FILE="$RESULTS_DIR/system_info.txt"
{
    echo "=== Date ==="
    date -Iseconds
    echo ""
    echo "=== CPU ==="
    lscpu 2>/dev/null | grep -E "^(Architecture:|Model name:|CPU\(s\):|Core\(s\) per socket:|Thread\(s\) per core:|Socket\(s\):|CPU max MHz:|CPU min MHz:|L[1-3].*cache:)" || echo "(lscpu not available)"
    echo ""
    echo "=== Memory ==="
    free -h 2>/dev/null || echo "(free not available)"
    echo ""
    echo "=== OS ==="
    grep "^PRETTY_NAME=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "(os-release not available)"
    echo ""
    echo "=== MPI Version ==="
    mpirun --version 2>/dev/null | head -n 1 || mpiexec --version 2>/dev/null | head -n 1 || echo "(MPI version not available)"
} > "$SYSINFO_FILE"

log_ok "System info saved to $SYSINFO_FILE"

# Compile the project
if [ -f /.dockerenv ]; then
    log_info "Running inside Docker. Skipping compilation, using pre-built binary."
    if [ ! -f "$BINARY" ]; then
        log_err "Pre-built binary not found: $BINARY"
        exit 1
    fi
    log_ok "Found pre-built binary: $BINARY"
else
    log_info "Compiling project with -O3 optimization..."
    cd "$PROJECT_DIR"
    make clean
    make

    if [ ! -f "$BINARY" ]; then
        log_err "Compilation failed — binary not found: $BINARY"
        exit 1
    fi
    log_ok "Compiled successfully: $BINARY"
fi

# Generate test files using standalone generator
log_info "Evaluating test files..."

# Build the --size arguments from FILE_SIZES_MB array
SIZE_ARGS=""
ALL_FILES_EXIST=true
for s in "${FILE_SIZES_MB[@]}"; do
    SIZE_ARGS="$SIZE_ARGS $s"
    if [ ! -f "$TESTDATA_DIR/test_${s}mb.txt" ]; then
        ALL_FILES_EXIST=false
    fi
done

if [ "$ALL_FILES_EXIST" = true ]; then
    log_ok "Test files already exist in $TESTDATA_DIR. Skipping generation."
else
    log_info "Some test files are missing. Generating them now..."
    python3 "$PROJECT_DIR/scripts/generate_testdata.py" \
        --size $SIZE_ARGS \
        --token "$TOKEN" \
        --output-dir "$TESTDATA_DIR" \
        --seed 42 \
        --edge-cases
    log_ok "Test files generated in $TESTDATA_DIR"
fi

# Determine network interface flags (only enforce internal-backend if inside Docker)
if [ -f /.dockerenv ]; then
    MPI_MCA="--mca btl_tcp_if_include 10.20.0.0/16"
else
    MPI_MCA=""
fi

# Run benchmark experiments
log_info "Starting benchmark experiments..."
echo ""

# CSV header
echo "num_procs,file_size_bytes,file_name,token,run_id,elapsed_time_sec,total_matches" \
    > "$RESULTS_CSV"

for size_mb in "${FILE_SIZES_MB[@]}"; do
    TEST_FILE="$TESTDATA_DIR/test_${size_mb}mb.txt"

    if [ ! -f "$TEST_FILE" ]; then
        log_warn "Test file not found: $TEST_FILE — skipping"
        continue
    fi

    FILE_BYTES=$(stat -c%s "$TEST_FILE" 2>/dev/null || stat -f%z "$TEST_FILE" 2>/dev/null)

    for nprocs in "${PROCESS_COUNTS[@]}"; do
        log_info "Testing: ${size_mb}MB file × ${nprocs} processes"

        for run_id in $(seq 1 $REPETITIONS); do
            log_info "  → Evaluating run ${run_id} from ${REPETITIONS}..."
            
            # Clean output directory for this run
            rm -rf "$OUTPUT_DIR"/matches_rank_*.csv
            OUTPUT=$(mpirun --oversubscribe --allow-run-as-root \
                ${MPI_MCA} \
                -np "$nprocs" "$BINARY" \
                --file "$TEST_FILE" \
                --token "$TOKEN" \
                --buffer-size 64 \
                --print-mode sample \
                --sample-size 1000 \
                --output-dir "$OUTPUT_DIR" 2>&1) || true
            
            echo "$OUTPUT" | grep -v "^BENCHMARK_CSV:" || true

            CSV_LINE=$(echo "$OUTPUT" | grep "^BENCHMARK_CSV:" | sed 's/^BENCHMARK_CSV://')

            if [ -n "$CSV_LINE" ]; then
                ELAPSED=$(echo "$CSV_LINE" | cut -d',' -f4)
                MATCHES=$(echo "$CSV_LINE" | cut -d',' -f5)

                echo "${nprocs},${FILE_BYTES},test_${size_mb}mb.txt,${TOKEN},${run_id},${ELAPSED},${MATCHES}" \
                    >> "$RESULTS_CSV"

                printf "    Run %d/%d: %.4f sec, %s matches\n" \
                    "$run_id" "$REPETITIONS" "$ELAPSED" "$MATCHES"
            else
                log_warn "  Run $run_id: Could not parse output"
                echo "${nprocs},${FILE_BYTES},test_${size_mb}mb.txt,${TOKEN},${run_id},-1,-1" \
                    >> "$RESULTS_CSV"
            fi
        done
        echo ""
    done
done

log_ok "Benchmark results saved to $RESULTS_CSV"

# Generate plots
log_info "Generating performance plots..."

python3 "$PROJECT_DIR/scripts/generate_plots.py" \
    --input "$RESULTS_CSV" \
    --output-dir "$RESULTS_DIR"

echo ""
echo "============================================================"
echo "  Benchmark suite complete!"
echo "============================================================"
echo "  Results CSV:  $RESULTS_CSV"
echo "  System info:  $SYSINFO_FILE"
echo "  Plots:        $RESULTS_DIR/*.png"
echo "============================================================"
echo ""
