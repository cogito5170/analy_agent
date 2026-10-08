// Trip optimizer: chooses the visiting order, nights per city, and transport mode
// per leg that minimise the total cost of a multi-city trip, where transport and
// lodging prices depend on the date.
//
// Nodes: 0 = origin, 1..visits = cities to visit (each exactly once),
// visits + 1 = return city (may be the same place as the origin; the engine does
// not care). Days are indices into the planning window [0, days).
//
// All money and time values are integers so that results are exact and identical
// on every platform (native and WebAssembly).
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace trip {

struct Problem {
    int visits = 0;  // number of cities to visit
    int days = 0;    // length of the planning window
    int modes = 1;   // transport modes per leg (e.g. flight, train)

    // price[a][b][day][mode] and minutes[a][b][day][mode], flattened with
    // index(a, b, day, mode). A negative price means "no such option".
    std::vector<int64_t> price;
    std::vector<int32_t> minutes;

    // lodging[city][day]: price of the night starting on `day` in `city`.
    // Only rows 1..visits are used. Must be >= 0.
    std::vector<int64_t> lodging;

    std::vector<int32_t> stay_min;  // nights per city, indexed by node (1..visits)
    std::vector<int32_t> stay_max;

    int depart_min = 0;  // earliest / latest day to leave the origin
    int depart_max = 0;

    // "Value for money" weight: cost of one minute of travel time. 0 = cheapest only.
    int64_t cost_per_minute = 0;

    int nodes() const { return visits + 2; }
    size_t index(int a, int b, int day, int mode) const {
        return ((static_cast<size_t>(a) * static_cast<size_t>(nodes()) + static_cast<size_t>(b)) *
                    static_cast<size_t>(days) + static_cast<size_t>(day)) *
                   static_cast<size_t>(modes) + static_cast<size_t>(mode);
    }
};

struct Leg {
    int from, to, day, mode;
    int64_t price;
    int32_t minutes;
};

struct Stay {
    int city, arrive_day, nights;
    int64_t lodging;
};

struct Plan {
    int64_t objective = 0;  // price + lodging + cost_per_minute * minutes
    int64_t transport_price = 0;
    int64_t lodging_price = 0;
    int64_t travel_minutes = 0;
    std::vector<Leg> legs;    // visits + 1 legs, in travel order
    std::vector<Stay> stays;  // one per visited city, in travel order
};

// Returns an empty string if the problem is well formed, else what is wrong.
std::string validate(const Problem& p);

// The k cheapest itineraries by objective, cheapest first. Fewer than k if fewer
// exist; empty if none is feasible. Throws std::invalid_argument on a malformed
// problem. Supports up to 10 cities to visit (the state table grows as 2^visits).
std::vector<Plan> optimize(const Problem& p, int k);

// Recomputes a plan's objective from the problem data; used to check plans.
int64_t evaluate(const Problem& p, const Plan& plan);

}  // namespace trip
