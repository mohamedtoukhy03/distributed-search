#include "cli_parser.h"
#include <getopt.h>
#include <iostream>
#include <cstdlib>
#include <mpi.h>

using namespace std;

void print_usage(const char* program_name) {
    cout << "\n"
              << "========================================================\n"
              << "  Distributed MPI Search — High-Performance Token Finder\n"
              << "========================================================\n\n"
              << "Usage: mpirun -np <N> " << program_name << " [OPTIONS]\n\n"
              << "Required:\n"
              << "  -f, --file <path>       Path to the input text file\n"
              << "  -t, --token <string>    Search token (whole word, no spaces)\n\n"
              << "Optional:\n"
              << "  -b, --buffer-size <MB>  Read buffer size in MB (default: 64)\n"
              << "  -p, --print-mode <mode> Output mode: none|sample|all (default: none)\n"
              << "  -s, --sample-size <N>   Matches to display per rank in sample mode (default: 10)\n"
              << "  -o, --output-dir <path> Directory for CSV output files (default: ./output)\n"
              << "  -h, --help              Show this help message and exit\n\n"
              << "Examples:\n"
              << "  mpirun -np 4 " << program_name
              << " --file data.txt --token hello\n"
              << "  mpirun -np 8 " << program_name
              << " -f big.txt -t search -b 128 -p sample -s 20\n\n";
}

Config parse_arguments(int argc, char* argv[], int rank) {
    Config config;
    static struct option long_options[] = {
        {"file",        required_argument, nullptr, 'f'},
        {"token",       required_argument, nullptr, 't'},
        {"buffer-size", required_argument, nullptr, 'b'},
        {"print-mode",  required_argument, nullptr, 'p'},
        {"sample-size", required_argument, nullptr, 's'},
        {"output-dir",  required_argument, nullptr, 'o'},
        {"help",        no_argument,       nullptr, 'h'},
        {nullptr,       0,                 nullptr,  0 }
    };
    optind = 1;

    int opt;
    while ((opt = getopt_long(argc, argv, "f:t:b:p:s:o:h", long_options, nullptr)) != -1) {
        switch (opt) {
            case 'f':
                config.file_path = optarg;
                break;

            case 't':
                config.token = optarg;
                break;

            case 'b': {
                int mb = atoi(optarg);
                if (mb <= 0) {
                    if (rank == 0) {
                        cerr << "[ERROR] --buffer-size must be a positive integer (MB).\n";
                    }
                    MPI_Abort(MPI_COMM_WORLD, 1);
                }
                config.buffer_size = static_cast<int64_t>(mb) * 1024 * 1024;
                break;
            }

            case 'p': {
                string mode(optarg);
                if (mode == "none") {
                    config.print_mode = PrintMode::NONE;
                } else if (mode == "sample") {
                    config.print_mode = PrintMode::SAMPLE;
                } else if (mode == "all") {
                    config.print_mode = PrintMode::ALL;
                } else {
                    if (rank == 0) {
                        cerr << "[ERROR] --print-mode must be one of: none, sample, all.\n";
                    }
                    MPI_Abort(MPI_COMM_WORLD, 1);
                }
                break;
            }

            case 's': {
                config.sample_size = atoi(optarg);
                if (config.sample_size <= 0) {
                    if (rank == 0) {
                        cerr << "[ERROR] --sample-size must be a positive integer.\n";
                    }
                    MPI_Abort(MPI_COMM_WORLD, 1);
                }
                break;
            }

            case 'o':
                config.output_dir = optarg;
                break;

            case 'h':
                if (rank == 0) {
                    print_usage(argv[0]);
                }
                MPI_Finalize();
                exit(0);

            default:
                if (rank == 0) {
                    print_usage(argv[0]);
                }
                MPI_Abort(MPI_COMM_WORLD, 1);
        }
    }

    if (config.file_path.empty()) {
        if (rank == 0) {
            cerr << "[ERROR] --file is required.\n";
            print_usage(argv[0]);
        }
        MPI_Abort(MPI_COMM_WORLD, 1);
    }

    if (config.token.empty()) {
        if (rank == 0) {
            cerr << "[ERROR] --token is required and must not be empty.\n";
            print_usage(argv[0]);
        }
        MPI_Abort(MPI_COMM_WORLD, 1);
    }

    if (config.token.find(' ') != string::npos) {
        if (rank == 0) {
            cerr << "[ERROR] --token must not contain spaces.\n";
        }
        MPI_Abort(MPI_COMM_WORLD, 1);
    }

    int64_t buffer_size_bytes = config.buffer_size * 1024 * 1024;
    if (config.token.size() >= static_cast<size_t>(buffer_size_bytes)) {
        if (rank == 0) {
            cerr << "[ERROR] Search token length (" << config.token.size() 
                      << " bytes) cannot exceed sliding buffer size (" 
                      << buffer_size_bytes << " bytes)." << endl;
        }
        MPI_Abort(MPI_COMM_WORLD, 1);
    }

    return config;
}
