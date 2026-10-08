// Dynamic programming over (set of visited cities, current city, arrival day).
//
// A state's value is the cost of reaching `city` on `day` having visited exactly
// `mask`. From a state we choose the number of nights s (within the city's stay
// range), depart on day + s, and pick the next unvisited city (or the return city
// once all are visited) and a transport mode. Costs are additive, so keeping the
// k best partial itineraries per state is enough to recover the k best complete
// ones (k-best dynamic programming).
#include "trip/optimizer.hpp"

#include <algorithm>
#include <stdexcept>

namespace trip {
namespace {

struct Entry {
    int64_t cost;
    int prev_state;  // -1: the leg starts at the origin
    int prev_rank;
    int nights;      // nights spent in the previous city (0 when leaving the origin)
    int day;         // departure day of the leg into this state
    int mode;
};

struct Final {
    int64_t cost;
    int state, rank, nights, day, mode;
};

bool better(const Entry& a, const Entry& b) {
    // Deterministic order: cost first, then the choice that produced the entry.
    if (a.cost != b.cost) return a.cost < b.cost;
    if (a.prev_state != b.prev_state) return a.prev_state < b.prev_state;
    if (a.prev_rank != b.prev_rank) return a.prev_rank < b.prev_rank;
    if (a.nights != b.nights) return a.nights < b.nights;
    if (a.day != b.day) return a.day < b.day;
    return a.mode < b.mode;
}

bool better_final(const Final& a, const Final& b) {
    if (a.cost != b.cost) return a.cost < b.cost;
    if (a.state != b.state) return a.state < b.state;
    if (a.rank != b.rank) return a.rank < b.rank;
    if (a.nights != b.nights) return a.nights < b.nights;
    if (a.day != b.day) return a.day < b.day;
    return a.mode < b.mode;
}

template <typename T, typename Less>
void keep_best(std::vector<T>& v, size_t k, Less less) {
    std::sort(v.begin(), v.end(), less);
    if (v.size() > k) v.resize(k);
}

// Bounded insert: keep the list from growing far beyond k between trims.
template <typename T, typename Less>
void push_bounded(std::vector<T>& v, const T& x, size_t k, Less less) {
    v.push_back(x);
    if (v.size() > 4 * k) {
        std::nth_element(v.begin(), v.begin() + static_cast<long>(k) - 1, v.end(), less);
        v.resize(k);
    }
}

class Solver {
public:
    Solver(const Problem& p, int k) : p_(p), k_(static_cast<size_t>(k)) {
        lodging_prefix_.assign(static_cast<size_t>(p.nodes()) * static_cast<size_t>(p.days + 1), 0);
        for (int c = 1; c <= p.visits; c++) {
            for (int d = 0; d < p.days; d++) {
                lodging_prefix_[pidx(c, d + 1)] = lodging_prefix_[pidx(c, d)] + p.lodging[lidx(c, d)];
            }
        }
        states_.resize((size_t{1} << p.visits) * static_cast<size_t>(p.visits) * static_cast<size_t>(p.days));
    }

    std::vector<Plan> run() {
        const int full = (1 << p_.visits) - 1;

        // First leg: origin -> city j.
        for (int d = p_.depart_min; d <= p_.depart_max; d++) {
            for (int j = 1; j <= p_.visits; j++) {
                for (int m = 0; m < p_.modes; m++) {
                    int64_t c;
                    if (!leg_cost(0, j, d, m, c)) continue;
                    push_bounded(states_[sidx(1 << (j - 1), j, d)], Entry{c, -1, 0, 0, d, m}, k_, better);
                }
            }
        }

        std::vector<Final> finals;
        for (int mask = 1; mask <= full; mask++) {
            for (int i = 1; i <= p_.visits; i++) {
                if (!(mask & (1 << (i - 1)))) continue;
                for (int t = 0; t < p_.days; t++) {
                    const int s_index = sidx(mask, i, t);
                    std::vector<Entry>& here = states_[static_cast<size_t>(s_index)];
                    if (here.empty()) continue;
                    keep_best(here, k_, better);
                    expand(mask, i, t, s_index, full, finals);
                }
            }
        }

        keep_best(finals, k_, better_final);
        std::vector<Plan> plans;
        for (const Final& f : finals) plans.push_back(rebuild(f));
        return plans;
    }

private:
    void expand(int mask, int i, int t, int s_index, int full, std::vector<Final>& finals) {
        const std::vector<Entry>& here = states_[static_cast<size_t>(s_index)];
        for (int s = p_.stay_min[static_cast<size_t>(i)]; s <= p_.stay_max[static_cast<size_t>(i)]; s++) {
            const int d = t + s;
            if (d >= p_.days) break;
            const int64_t lodge = lodging(i, t, s);
            if (mask == full) {
                const int ret = p_.visits + 1;
                for (int m = 0; m < p_.modes; m++) {
                    int64_t c;
                    if (!leg_cost(i, ret, d, m, c)) continue;
                    for (size_t r = 0; r < here.size(); r++) {
                        push_bounded(finals, Final{here[r].cost + lodge + c, s_index, static_cast<int>(r), s, d, m},
                                     k_, better_final);
                    }
                }
                continue;
            }
            for (int j = 1; j <= p_.visits; j++) {
                if (mask & (1 << (j - 1))) continue;
                for (int m = 0; m < p_.modes; m++) {
                    int64_t c;
                    if (!leg_cost(i, j, d, m, c)) continue;
                    std::vector<Entry>& next = states_[static_cast<size_t>(sidx(mask | (1 << (j - 1)), j, d))];
                    for (size_t r = 0; r < here.size(); r++) {
                        push_bounded(next, Entry{here[r].cost + lodge + c, s_index, static_cast<int>(r), s, d, m},
                                     k_, better);
                    }
                }
            }
        }
    }

    Plan rebuild(const Final& f) const {
        Plan plan;
        plan.objective = f.cost;
        // Walk back from the final leg, collecting legs and stays in reverse.
        int state = f.state, rank = f.rank, nights = f.nights, day = f.day, mode = f.mode;
        int to = p_.visits + 1;
        while (true) {
            const int city = city_of(state);
            const int arrive = day_of(state);
            add_leg(plan, city, to, day, mode);
            add_stay(plan, city, arrive, nights);
            const Entry& e = states_[static_cast<size_t>(state)][static_cast<size_t>(rank)];
            to = city;
            if (e.prev_state < 0) {
                add_leg(plan, 0, to, e.day, e.mode);
                break;
            }
            state = e.prev_state;
            rank = e.prev_rank;
            nights = e.nights;
            day = e.day;
            mode = e.mode;
        }
        std::reverse(plan.legs.begin(), plan.legs.end());
        std::reverse(plan.stays.begin(), plan.stays.end());
        return plan;
    }

    void add_leg(Plan& plan, int from, int to, int day, int mode) const {
        const size_t x = p_.index(from, to, day, mode);
        plan.legs.push_back(Leg{from, to, day, mode, p_.price[x], p_.minutes[x]});
        plan.transport_price += p_.price[x];
        plan.travel_minutes += p_.minutes[x];
    }

    void add_stay(Plan& plan, int city, int arrive, int nights) const {
        const int64_t l = lodging(city, arrive, nights);
        plan.stays.push_back(Stay{city, arrive, nights, l});
        plan.lodging_price += l;
    }

    bool leg_cost(int a, int b, int d, int m, int64_t& out) const {
        const size_t x = p_.index(a, b, d, m);
        if (p_.price[x] < 0) return false;
        out = p_.price[x] + p_.cost_per_minute * p_.minutes[x];
        return true;
    }

    int64_t lodging(int city, int arrive, int nights) const {
        return lodging_prefix_[pidx(city, arrive + nights)] - lodging_prefix_[pidx(city, arrive)];
    }

    int sidx(int mask, int city, int day) const {
        return (mask * p_.visits + (city - 1)) * p_.days + day;
    }
    int city_of(int s) const { return (s / p_.days) % p_.visits + 1; }
    int day_of(int s) const { return s % p_.days; }
    size_t pidx(int c, int d) const { return static_cast<size_t>(c) * static_cast<size_t>(p_.days + 1) + static_cast<size_t>(d); }
    size_t lidx(int c, int d) const { return static_cast<size_t>(c) * static_cast<size_t>(p_.days) + static_cast<size_t>(d); }

    const Problem& p_;
    size_t k_;
    std::vector<int64_t> lodging_prefix_;
    std::vector<std::vector<Entry>> states_;
};

}  // namespace

std::string validate(const Problem& p) {
    if (p.visits < 1 || p.visits > 10) return "visits must be between 1 and 10";
    if (p.days < 1) return "days must be at least 1";
    if (p.modes < 1) return "modes must be at least 1";
    const size_t legs = static_cast<size_t>(p.nodes()) * static_cast<size_t>(p.nodes()) *
                        static_cast<size_t>(p.days) * static_cast<size_t>(p.modes);
    if (p.price.size() != legs || p.minutes.size() != legs) return "price/minutes size mismatch";
    if (p.lodging.size() != static_cast<size_t>(p.nodes()) * static_cast<size_t>(p.days)) return "lodging size mismatch";
    if (p.stay_min.size() != static_cast<size_t>(p.nodes()) || p.stay_max.size() != static_cast<size_t>(p.nodes())) {
        return "stay range size mismatch";
    }
    for (int c = 1; c <= p.visits; c++) {
        const int lo = p.stay_min[static_cast<size_t>(c)], hi = p.stay_max[static_cast<size_t>(c)];
        if (lo < 0 || hi < lo) return "invalid stay range for city " + std::to_string(c);
        for (int d = 0; d < p.days; d++) {
            if (p.lodging[static_cast<size_t>(c) * static_cast<size_t>(p.days) + static_cast<size_t>(d)] < 0) {
                return "lodging prices must be >= 0";
            }
        }
    }
    for (int32_t m : p.minutes) {
        if (m < 0) return "minutes must be >= 0";
    }
    if (p.depart_min < 0 || p.depart_max < p.depart_min || p.depart_max >= p.days) return "invalid departure window";
    if (p.cost_per_minute < 0) return "cost_per_minute must be >= 0";
    return "";
}

std::vector<Plan> optimize(const Problem& p, int k) {
    const std::string err = validate(p);
    if (!err.empty()) throw std::invalid_argument(err);
    if (k < 1) throw std::invalid_argument("k must be at least 1");
    return Solver(p, k).run();
}

int64_t evaluate(const Problem& p, const Plan& plan) {
    int64_t total = 0;
    for (const Leg& l : plan.legs) {
        const size_t x = p.index(l.from, l.to, l.day, l.mode);
        total += p.price[x] + p.cost_per_minute * p.minutes[x];
    }
    for (const Stay& s : plan.stays) {
        for (int d = s.arrive_day; d < s.arrive_day + s.nights; d++) {
            total += p.lodging[static_cast<size_t>(s.city) * static_cast<size_t>(p.days) + static_cast<size_t>(d)];
        }
    }
    return total;
}

}  // namespace trip
