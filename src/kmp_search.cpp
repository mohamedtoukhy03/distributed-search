

#include "kmp_search.h"

using namespace std;

vector<int> kmp_build_failure_table(const string& pattern) {
    int m = static_cast<int>(pattern.size());
    vector<int> failure(m, 0);
    int j = 0;

    for (int i = 1; i < m; i++) {
        while (j > 0 && pattern[i] != pattern[j]) {
            j = failure[j - 1];
        }
        if (pattern[i] == pattern[j]) {
            j++;
        }

        failure[i] = j;
    }

    return failure;
}

vector<int64_t> kmp_search(const char* buffer,
                                int64_t buffer_len,
                                const string& pattern,
                                const vector<int>& failure_table) {
    vector<int64_t> matches;
    int m = static_cast<int>(pattern.size());

    if (m == 0 || buffer_len == 0) {
        return matches;
    }

    int j = 0;

    for (int64_t i = 0; i < buffer_len; i++) {
        while (j > 0 && buffer[i] != pattern[j]) {
            j = failure_table[j - 1];
        }
        if (buffer[i] == pattern[j]) {
            j++;
        }
        if (j == m) {
            int64_t match_pos = i - m + 1;
            bool left_boundary  = (match_pos == 0) ||
                                  !is_word_char(buffer[match_pos - 1]);
            bool right_boundary = (match_pos + m >= buffer_len) ||
                                  !is_word_char(buffer[match_pos + m]);

            if (left_boundary && right_boundary) {
                matches.push_back(match_pos);
            }
            j = failure_table[j - 1];
        }
    }

    return matches;
}
