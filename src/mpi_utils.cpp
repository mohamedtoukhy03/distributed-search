#include "mpi_utils.h"
#include "kmp_search.h"
#include <iostream>
#include <fstream>
#include <algorithm>
#include <cstring>
#include <sys/stat.h>

using namespace std;

ChunkInfo compute_chunk_info(int64_t file_size, int num_ranks,
                             int rank, int64_t token_length) {
    ChunkInfo info;

    int64_t base = file_size / num_ranks;
    int64_t rem  = file_size % num_ranks;

    if (rank < static_cast<int>(rem)) {
        info.my_start  = rank * (base + 1);
        info.my_length = base + 1;
    } else {
        info.my_start  = rem * (base + 1) + (rank - rem) * base;
        info.my_length = base;
    }

    int64_t bytes_after = file_size - info.my_start - info.my_length;
    info.ghost_size  = min(token_length, max(bytes_after, (int64_t)0));
    info.read_length = info.my_length + info.ghost_size;

    return info;
}

void broadcast_config(Config& config, int rank) {
    int64_t nums[4];
    if (rank == 0) {
        nums[0] = config.buffer_size;
        nums[1] = static_cast<int64_t>(config.print_mode);
        nums[2] = config.sample_size;
        nums[3] = 0;
    }
    MPI_Bcast(nums, 4, MPI_LONG_LONG, 0, MPI_COMM_WORLD);
    if (rank != 0) {
        config.buffer_size = nums[0];
        config.print_mode  = static_cast<PrintMode>(nums[1]);
        config.sample_size = static_cast<int>(nums[2]);
    }

    auto bcast_str = [&](string& s) {
        int len = (rank == 0) ? static_cast<int>(s.size()) : 0;
        MPI_Bcast(&len, 1, MPI_INT, 0, MPI_COMM_WORLD);
        if (rank != 0) s.resize(len);
        if (len > 0) MPI_Bcast(&s[0], len, MPI_CHAR, 0, MPI_COMM_WORLD);
    };

    bcast_str(config.file_path);
    bcast_str(config.token);
    bcast_str(config.output_dir);
}

void write_matches_csv(const vector<MatchResult>& matches,
                       const string& output_dir, int rank) {
    mkdir(output_dir.c_str(), 0755);

    string filename = output_dir + "/matches_rank_"
                         + to_string(rank) + ".csv";

    ofstream ofs(filename);
    if (!ofs.is_open()) {
        cerr << "[Rank " << rank << "] ERROR: Cannot open "
                  << filename << " for writing.\n";
        return;
    }

    ofs << "global_line,column\n";
    for (const auto& m : matches) {
        ofs << m.global_line << "," << m.column << "\n";
    }
    ofs.close();
}

void print_matches(const vector<MatchResult>& matches,
                   const Config& config, int rank, int nprocs) {
    if (config.print_mode == PrintMode::NONE) return;

    int64_t count = static_cast<int64_t>(matches.size());
    if (config.print_mode == PrintMode::SAMPLE) {
        count = min(count, static_cast<int64_t>(config.sample_size));
    }

    for (int r = 0; r < nprocs; r++) {
        MPI_Barrier(MPI_COMM_WORLD);
        if (r == rank && count > 0) {
            cout << "--- Rank " << rank << " ("
                      << matches.size() << " total matches";
            if (config.print_mode == PrintMode::SAMPLE &&
                static_cast<int64_t>(matches.size()) > count) {
                cout << ", showing " << count;
            }
            cout << ") ---\n";
            for (int64_t i = 0; i < count; i++) {
                cout << "  Line " << matches[i].global_line
                          << ", Column " << matches[i].column << "\n";
            }
            cout << flush;
        }
    }
}

int64_t process_chunk(MPI_File fh, const Config& config,
                      const ChunkInfo& chunk, int rank, int nprocs) {

    const int64_t token_len  = static_cast<int64_t>(config.token.size());
    const int64_t carry_size = token_len + 1;
    const int64_t buf_cap    = config.buffer_size;
    const int64_t left_ghost = (chunk.my_start > 0) ? 1 : 0;
    
    int64_t actual_read_start  = chunk.my_start - left_ghost;
    int64_t actual_read_length = left_ghost + chunk.read_length;

    vector<int> failure = kmp_build_failure_table(config.token);
    vector<char> buffer(carry_size + buf_cap);
    vector<MatchResult> all_matches;

    int64_t current_line      = 0;  
    int64_t last_newline_coff = -1;                

    if (chunk.my_start > 0) {
        int64_t search_pos = chunk.my_start - 1;
        bool found = false;
        while (search_pos >= 0 && !found) {
            int64_t read_start = max((int64_t)0, search_pos - 1024 + 1);
            int64_t want = search_pos - read_start + 1;
            vector<char> back_buf(want);
            MPI_Status st;
            MPI_File_read_at(fh, read_start, back_buf.data(), static_cast<int>(want), MPI_CHAR, &st);
            int got = 0;
            MPI_Get_count(&st, MPI_CHAR, &got);
            if (got <= 0) break;
            for (int64_t idx = got - 1; idx >= 0; idx--) {
                if (back_buf[idx] == '\n') {
                    last_newline_coff = (read_start + idx) - chunk.my_start;
                    found = true;
                    break;
                }
            }
            search_pos = read_start - 1;
        }
        if (!found) {
            last_newline_coff = -1 - chunk.my_start;
        }
    }

    int64_t bytes_consumed = 0;   
    int64_t carry_used     = 0;   

    while (bytes_consumed < actual_read_length) {
        int64_t to_read = min(buf_cap, actual_read_length - bytes_consumed);

        MPI_Status st;
        MPI_File_read_at(fh,
                         actual_read_start + bytes_consumed,
                         buffer.data() + carry_used,
                         static_cast<int>(to_read),
                         MPI_CHAR, &st);

        int got = 0;
        MPI_Get_count(&st, MPI_CHAR, &got);
        if (got <= 0) break;

        int64_t window_size = carry_used + got;
        bool is_last_window = ((bytes_consumed + got) >= actual_read_length);

        struct NLInfo {
            int64_t buf_pos;
            int64_t chunk_offset;
        };
        vector<NLInfo> new_newlines;

        for (int64_t k = carry_used; k < window_size; k++) {
            if (buffer[k] == '\n') {
                int64_t coff = bytes_consumed + (k - carry_used) - left_ghost;
                if (coff < 0) {
                    last_newline_coff = coff;
                } else if (coff < chunk.my_length) {
                    new_newlines.push_back({k, coff});
                }
            }
        }

        vector<int64_t> hits = kmp_search(buffer.data(), window_size, config.token, failure);

        for (int64_t buf_pos : hits) {
            int64_t coff = bytes_consumed - carry_used + buf_pos - left_ghost;

            if (coff < 0 || coff >= chunk.my_length) continue;
            if (!is_last_window && buf_pos + token_len >= window_size) continue;
            if (carry_used > 0 && buf_pos == 0) continue;

            int64_t nl_count = 0;
            int64_t lo = 0, hi = static_cast<int64_t>(new_newlines.size());
            while (lo < hi) {
                int64_t mid = (lo + hi) / 2;
                if (new_newlines[mid].buf_pos < buf_pos) lo = mid + 1;
                else hi = mid;
            }
            nl_count = lo;

            int64_t match_line = current_line + nl_count + 1; 

            int64_t last_nl;
            if (nl_count > 0) last_nl = new_newlines[nl_count - 1].chunk_offset;
            else last_nl = last_newline_coff;

            int64_t column = coff - last_nl;
            all_matches.push_back({match_line, column});
        }

        current_line += static_cast<int64_t>(new_newlines.size());
        if (!new_newlines.empty()) {
            last_newline_coff = new_newlines.back().chunk_offset;
        }

        bytes_consumed += got;

        if (bytes_consumed < actual_read_length && carry_size > 0) {
            int64_t actual_carry = min(carry_size, window_size);
            memmove(buffer.data(),
                         buffer.data() + window_size - actual_carry,
                         actual_carry);
            carry_used = actual_carry;
        } else {
            carry_used = 0;
        }
    }

    int64_t local_newline_count = current_line;
    int64_t global_line_offset = 0;
    MPI_Exscan(&local_newline_count, &global_line_offset,
               1, MPI_LONG_LONG, MPI_SUM, MPI_COMM_WORLD);
    if (rank == 0) global_line_offset = 0;

    for (auto& match : all_matches) {
        match.global_line += global_line_offset;
    }

    write_matches_csv(all_matches, config.output_dir, rank);
    print_matches(all_matches, config, rank, nprocs);

    return static_cast<int64_t>(all_matches.size());
}
