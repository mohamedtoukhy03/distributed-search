#ifndef DISTRIBUTED_SEARCH_KMP_SEARCH_H
#define DISTRIBUTED_SEARCH_KMP_SEARCH_H

#include <vector>
#include <cstdint>
#include <string>

using namespace std;
vector<int> kmp_build_failure_table(const string& pattern);
vector<int64_t> kmp_search(const char* buffer,
                                int64_t buffer_len,
                                const string& pattern,
                                const vector<int>& failure_table);
inline bool is_word_char(char ch) {
    return (ch >= 'a' && ch <= 'z') ||
           (ch >= 'A' && ch <= 'Z') ||
           (ch >= '0' && ch <= '9') ||
           (ch == '_');
}

#endif
