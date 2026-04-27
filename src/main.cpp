
#include "types.h"
#include "cli_parser.h"
#include "mpi_utils.h"
#include <mpi.h>
#include <iostream>
#include <iomanip>
#include <numeric>
#include <vector>

using namespace std;

int main(int argc, char* argv[]) {
    MPI_Init(&argc, &argv);

    int rank, nprocs;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &nprocs);
    Config config;
    if (rank == 0) {
        config = parse_arguments(argc, argv, rank);
    }
    broadcast_config(config, rank);
    MPI_File fh;
    int rc = MPI_File_open(MPI_COMM_WORLD,
                           config.file_path.c_str(),
                           MPI_MODE_RDONLY,
                           MPI_INFO_NULL,
                           &fh);

    if (rc != MPI_SUCCESS) {
        if (rank == 0) {
            cerr << "[ERROR] Cannot open file: " << config.file_path << "\n";
        }
        MPI_Abort(MPI_COMM_WORLD, 1);
    }
    MPI_Offset file_size_mpi;
    MPI_File_get_size(fh, &file_size_mpi);
    int64_t file_size = static_cast<int64_t>(file_size_mpi);

    if (file_size == 0) {
        if (rank == 0) {
            cout << "File is empty. No matches found.\n";
        }
        MPI_File_close(&fh);
        MPI_Finalize();
        return 0;
    }

    int64_t token_len = static_cast<int64_t>(config.token.size());
    ChunkInfo chunk = compute_chunk_info(file_size, nprocs, rank, token_len);

    if (rank == 0) {
        cout << "\n"
                  << "============================================================\n"
                  << "  Distributed MPI Search\n"
                  << "============================================================\n"
                  << "  File:        " << config.file_path << "\n"
                  << "  File size:   " << file_size << " bytes ("
                  << fixed << setprecision(2)
                  << (file_size / (1024.0 * 1024.0)) << " MB)\n"
                  << "  Token:       \"" << config.token << "\"\n"
                  << "  Processes:   " << nprocs << "\n"
                  << "  Buffer size: " << (config.buffer_size / (1024 * 1024))
                  << " MB\n"
                  << "  Output dir:  " << config.output_dir << "\n"
                  << "============================================================\n\n";
    }

    MPI_Barrier(MPI_COMM_WORLD);  
    double t_start = MPI_Wtime();
    int64_t local_matches = process_chunk(fh, config, chunk, rank, nprocs);
    MPI_Barrier(MPI_COMM_WORLD); 
    double t_end = MPI_Wtime();
    double elapsed = t_end - t_start;
    int64_t total_matches = 0;
    MPI_Reduce(&local_matches, &total_matches, 1, MPI_LONG_LONG,
               MPI_SUM, 0, MPI_COMM_WORLD);

    double max_elapsed = 0.0;
    MPI_Reduce(&elapsed, &max_elapsed, 1, MPI_DOUBLE,
               MPI_MAX, 0, MPI_COMM_WORLD);

    if (rank == 0) {
        cout << "\n"
                  << "============================================================\n"
                  << "  Results Summary\n"
                  << "============================================================\n"
                  << "  Total matches found: " << total_matches << "\n"
                  << "  Wall-clock time:     " << fixed << setprecision(6)
                  << max_elapsed << " seconds\n"
                  << "  Throughput:          " << fixed << setprecision(2)
                  << (file_size / (1024.0 * 1024.0) / max_elapsed) << " MB/s\n"
                  << "  Output files:        " << config.output_dir
                  << "/matches_rank_*.csv\n"
                  << "============================================================\n\n";

        cout << "BENCHMARK_CSV:" << nprocs << ","
                  << file_size << "," << config.token << ","
                  << fixed << setprecision(6) << max_elapsed << ","
                  << total_matches << "\n";
    }

    MPI_File_close(&fh);
    MPI_Finalize();

    return 0;
}
