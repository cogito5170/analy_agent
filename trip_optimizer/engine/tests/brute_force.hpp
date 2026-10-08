// Test oracle: enumerate every itinerary (order x departure day x nights x modes)
// and return all objective values. Deliberately written differently from the
// optimizer (plain recursion, no shared helpers) so that a bug in one is unlikely
// to be repeated in the other.
#pragma once

#include <algorithm>
#include <cstdint>
#include <vector>

#include "trip/optimizer.hpp"

namespace oracle {

inline int64_t leg(const trip::Problem& p, int a, int b, int d, int m, bool& ok) {
    const int64_t price = p.price[p.index(a, b, d, m)];
    if (price < 0) {
        ok = false;
        return 0;
    }
    return price + p.cost_per_minute * p.minutes[p.index(a, b, d, m)];
}

inline void walk(const trip::Problem& p, std::vector<int>& order, size_t pos, int city, int arrive, int64_t cost,
                 std::vector<int64_t>& out) {
    const int nodes = p.visits + 2;
    for (int s = p.stay_min[static_cast<size_t>(city)]; s <= p.stay_max[static_cast<size_t>(city)]; s++) {
        const int depart = arrive + s;
        if (depart >= p.days) break;
        int64_t lodge = 0;
        for (int d = arrive; d < depart; d++) lodge += p.lodging[static_cast<size_t>(city * p.days + d)];
        const int next = pos + 1 < order.size() ? order[pos + 1] : nodes - 1;
        for (int m = 0; m < p.modes; m++) {
            bool ok = true;
            const int64_t c = leg(p, city, next, depart, m, ok);
            if (!ok) continue;
            if (next == nodes - 1) {
                out.push_back(cost + lodge + c);
            } else {
                walk(p, order, pos + 1, next, depart, cost + lodge + c, out);
            }
        }
    }
}

// All feasible objective values, sorted ascending.
inline std::vector<int64_t> all_costs(const trip::Problem& p) {
    std::vector<int> order;
    for (int c = 1; c <= p.visits; c++) order.push_back(c);
    std::vector<int64_t> out;
    do {
        for (int d0 = p.depart_min; d0 <= p.depart_max; d0++) {
            for (int m = 0; m < p.modes; m++) {
                bool ok = true;
                const int64_t c = leg(p, 0, order[0], d0, m, ok);
                if (ok) walk(p, order, 0, order[0], d0, c, out);
            }
        }
    } while (std::next_permutation(order.begin(), order.end()));
    std::sort(out.begin(), out.end());
    return out;
}

}  // namespace oracle
