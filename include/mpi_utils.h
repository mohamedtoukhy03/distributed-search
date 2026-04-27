

#ifndef DISTRIBUTED_SEARCH_MPI_UTILS_H
#define DISTRIBUTED_SEARCH_MPI_UTILS_H

#include "types.h"
#include <mpi.h>
#include <vector>
#include <string>
#include <cstdint>

using namespace std;

struct ChunkInfo {
    int64_t my_start;
    int64_t my_length;
    int64_t read_length;
    int64_t ghost_size;
};

ChunkInfo compute_chunk_info(int64_t file_size, int num_ranks,
                             int rank, int64_t token_length);

void broadcast_config(Config& config, int rank);

int64_t process_chunk(MPI_File fh, const Config& config,
                      const ChunkInfo& chunk, int rank, int nprocs);

void write_matches_csv(const vector<MatchResult>& matches,
                       const string& output_dir, int rank);
void print_matches(const vector<MatchResult>& matches,
                   const Config& config, int rank, int nprocs);

#endif 
