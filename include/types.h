#ifndef DISTRIBUTED_SEARCH_TYPES_H
#define DISTRIBUTED_SEARCH_TYPES_H

#include <string>
#include <cstdint>

using namespace std;
enum class PrintMode {
    NONE,
    SAMPLE,
    ALL
};
struct Config {
    string file_path;
    string token;
    int64_t     buffer_size  = 64LL * 1024 * 1024;   
    PrintMode   print_mode   = PrintMode::NONE;
    int         sample_size  = 10;
    string output_dir   = "./output";
};

struct MatchResult {
    int64_t global_line;
    int64_t column;
};

#endif 
