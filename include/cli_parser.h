#ifndef DISTRIBUTED_SEARCH_CLI_PARSER_H
#define DISTRIBUTED_SEARCH_CLI_PARSER_H

#include "types.h"

using namespace std;
Config parse_arguments(int argc, char* argv[], int rank);

void print_usage(const char* program_name);

#endif 
