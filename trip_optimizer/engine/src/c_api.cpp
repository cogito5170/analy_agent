#include "trip/c_api.h"

#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

#include "trip/optimizer.hpp"

namespace {

std::string g_error;

constexpr double kMaxExact = 9007199254740992.0;  // 2^53

bool to_int64(double v, int64_t& out) {
    if (!std::isfinite(v) || std::floor(v) != v || std::fabs(v) >= kMaxExact) return false;
    out = static_cast<int64_t>(v);
    return true;
}

}  // namespace

extern "C" {

int trip_output_size(int visits, int k) {
    return k * (4 + 1 + 6 * (visits + 1) + 1 + 4 * visits);
}

int trip_optimize(int visits, int days, int modes, const double* price, const double* minutes,
                  const double* lodging, const int* stay_min, const int* stay_max, int depart_min,
                  int depart_max, double cost_per_minute, int k, double* out, int out_len) {
    g_error.clear();
    if (visits < 1 || visits > 10 || days < 1 || modes < 1 || k < 1) {
        g_error = "visits must be 1..10, days, modes and k at least 1";
        return -1;
    }
    trip::Problem p;
    p.visits = visits;
    p.days = days;
    p.modes = modes;
    const size_t nodes = static_cast<size_t>(visits + 2);
    const size_t legs = nodes * nodes * static_cast<size_t>(days) * static_cast<size_t>(modes);
    p.price.resize(legs);
    p.minutes.resize(legs);
    for (size_t i = 0; i < legs; i++) {
        int64_t m;
        if (!to_int64(price[i], p.price[i]) || !to_int64(minutes[i], m) || m > INT32_MAX) {
            g_error = "price and minutes must be whole numbers";
            return -1;
        }
        p.minutes[i] = static_cast<int32_t>(m);
    }
    p.lodging.resize(nodes * static_cast<size_t>(days));
    for (size_t i = 0; i < p.lodging.size(); i++) {
        if (!to_int64(lodging[i], p.lodging[i])) {
            g_error = "lodging prices must be whole numbers";
            return -1;
        }
    }
    p.stay_min.assign(stay_min, stay_min + nodes);
    p.stay_max.assign(stay_max, stay_max + nodes);
    p.depart_min = depart_min;
    p.depart_max = depart_max;
    if (!to_int64(cost_per_minute, p.cost_per_minute)) {
        g_error = "cost per minute must be a whole number";
        return -1;
    }
    if (out_len < trip_output_size(visits, k)) {
        g_error = "output buffer too small";
        return -2;
    }

    // Validate here instead of catching the optimizer's exception: WebAssembly builds
    // disable C++ exception catching by default, so a throw would abort the module.
    g_error = trip::validate(p);
    if (!g_error.empty()) return -1;
    const std::vector<trip::Plan> plans = trip::optimize(p, k);

    size_t w = 0;
    auto put = [&](double v) { out[w++] = v; };
    for (const trip::Plan& plan : plans) {
        put(static_cast<double>(plan.objective));
        put(static_cast<double>(plan.transport_price));
        put(static_cast<double>(plan.lodging_price));
        put(static_cast<double>(plan.travel_minutes));
        put(static_cast<double>(plan.legs.size()));
        for (const trip::Leg& l : plan.legs) {
            put(l.from); put(l.to); put(l.day); put(l.mode);
            put(static_cast<double>(l.price)); put(l.minutes);
        }
        put(static_cast<double>(plan.stays.size()));
        for (const trip::Stay& s : plan.stays) {
            put(s.city); put(s.arrive_day); put(s.nights); put(static_cast<double>(s.lodging));
        }
    }
    return static_cast<int>(plans.size());
}

const char* trip_last_error(void) { return g_error.c_str(); }

}  // extern "C"
