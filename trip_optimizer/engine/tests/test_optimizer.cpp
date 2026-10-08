#include <gtest/gtest.h>

#include <chrono>
#include <cstdio>
#include <random>
#include <set>
#include <stdexcept>

#include "brute_force.hpp"
#include "trip/optimizer.hpp"

namespace {

trip::Problem empty_problem(int visits, int days, int modes) {
    trip::Problem p;
    p.visits = visits;
    p.days = days;
    p.modes = modes;
    const size_t n = static_cast<size_t>(visits + 2);
    p.price.assign(n * n * static_cast<size_t>(days * modes), -1);
    p.minutes.assign(p.price.size(), 0);
    p.lodging.assign(n * static_cast<size_t>(days), 0);
    p.stay_min.assign(n, 1);
    p.stay_max.assign(n, 1);
    p.depart_min = 0;
    p.depart_max = 0;
    return p;
}

void set_leg(trip::Problem& p, int a, int b, int day, int mode, int64_t price, int32_t minutes = 60) {
    p.price[p.index(a, b, day, mode)] = price;
    p.minutes[p.index(a, b, day, mode)] = minutes;
}

trip::Problem random_problem(std::mt19937& rng) {
    std::uniform_int_distribution<int> visits(1, 4), days(2, 8), modes(1, 2), price(0, 500), minutes(10, 600),
        lodge(0, 100), stay(0, 2), extra(0, 2), cpm(0, 3), percent(0, 99);
    trip::Problem p = empty_problem(visits(rng), days(rng), modes(rng));
    for (size_t i = 0; i < p.price.size(); i++) {
        p.price[i] = percent(rng) < 25 ? -1 : price(rng);  // some options do not exist
        p.minutes[i] = minutes(rng);
    }
    for (size_t i = 0; i < p.lodging.size(); i++) p.lodging[i] = lodge(rng);
    for (int c = 1; c <= p.visits; c++) {
        p.stay_min[static_cast<size_t>(c)] = stay(rng);
        p.stay_max[static_cast<size_t>(c)] = p.stay_min[static_cast<size_t>(c)] + extra(rng);
    }
    p.depart_min = std::uniform_int_distribution<int>(0, p.days - 1)(rng);
    p.depart_max = std::uniform_int_distribution<int>(p.depart_min, p.days - 1)(rng);
    p.cost_per_minute = cpm(rng);
    return p;
}

// A plan must be a real itinerary, not just carry the right number.
void expect_valid_plan(const trip::Problem& p, const trip::Plan& plan) {
    ASSERT_EQ(plan.legs.size(), static_cast<size_t>(p.visits + 1));
    ASSERT_EQ(plan.stays.size(), static_cast<size_t>(p.visits));
    EXPECT_EQ(plan.legs.front().from, 0);
    EXPECT_EQ(plan.legs.back().to, p.visits + 1);
    EXPECT_GE(plan.legs.front().day, p.depart_min);
    EXPECT_LE(plan.legs.front().day, p.depart_max);
    std::set<int> seen;
    for (size_t i = 0; i < plan.stays.size(); i++) {
        const trip::Stay& s = plan.stays[i];
        EXPECT_TRUE(seen.insert(s.city).second) << "city visited twice";
        EXPECT_EQ(plan.legs[i].to, s.city);
        EXPECT_EQ(plan.legs[i + 1].from, s.city);
        EXPECT_EQ(plan.legs[i].day, s.arrive_day);
        EXPECT_EQ(plan.legs[i + 1].day, s.arrive_day + s.nights);
        EXPECT_GE(s.nights, p.stay_min[static_cast<size_t>(s.city)]);
        EXPECT_LE(s.nights, p.stay_max[static_cast<size_t>(s.city)]);
    }
    for (const trip::Leg& l : plan.legs) EXPECT_GE(l.price, 0) << "used a leg that does not exist";
    EXPECT_EQ(trip::evaluate(p, plan), plan.objective);
    EXPECT_EQ(plan.objective,
              plan.transport_price + plan.lodging_price + p.cost_per_minute * plan.travel_minutes);
}

}  // namespace

// The chat example: 4 cities -> 24 orders, flight prices change by date.
// Only one order is cheap, and only if the trip starts on day 1.
TEST(Optimizer, FindsTheOnlyCheapOrderAmong24) {
    trip::Problem p = empty_problem(4, 12, 1);
    for (int a = 0; a < p.nodes(); a++)
        for (int b = 0; b < p.nodes(); b++)
            for (int d = 0; d < p.days; d++) set_leg(p, a, b, d, 0, 300);
    p.depart_max = 3;
    // Cheap chain: origin -(day1)-> 3 -(day3)-> 1 -(day5)-> 4 -(day7)-> 2 -(day9)-> return
    const int chain[] = {0, 3, 1, 4, 2, 5};
    for (int i = 0; i < 5; i++) set_leg(p, chain[i], chain[i + 1], 1 + 2 * i, 0, 50);
    for (int c = 1; c <= 4; c++) p.stay_min[static_cast<size_t>(c)] = p.stay_max[static_cast<size_t>(c)] = 2;

    const auto plans = trip::optimize(p, 3);
    ASSERT_FALSE(plans.empty());
    EXPECT_EQ(plans[0].objective, 250);
    for (int i = 0; i < 5; i++) EXPECT_EQ(plans[0].legs[static_cast<size_t>(i)].to, chain[i + 1]);
    expect_valid_plan(p, plans[0]);
}

TEST(Optimizer, ValueForMoneyModeTradesPriceForTime) {
    trip::Problem p = empty_problem(1, 3, 2);  // mode 0 = cheap and slow, mode 1 = dear and fast
    for (int a : {0, 1})
        for (int d = 0; d < 3; d++) {
            set_leg(p, a, a + 1, d, 0, 100, 600);
            set_leg(p, a, a + 1, d, 1, 200, 60);
        }
    EXPECT_EQ(trip::optimize(p, 1)[0].legs[0].mode, 0);  // cheapest only
    p.cost_per_minute = 1;                               // one minute is worth 1 unit
    EXPECT_EQ(trip::optimize(p, 1)[0].legs[0].mode, 1);
}

TEST(Optimizer, InfeasibleTripReturnsNoPlans) {
    trip::Problem p = empty_problem(2, 5, 1);  // no legs exist at all
    EXPECT_TRUE(trip::optimize(p, 5).empty());
}

TEST(Optimizer, StayMustFitInsideTheWindow) {
    trip::Problem p = empty_problem(1, 3, 1);
    for (int d = 0; d < 3; d++) {
        set_leg(p, 0, 1, d, 0, 10);
        set_leg(p, 1, 2, d, 0, 10);
    }
    p.stay_min[1] = p.stay_max[1] = 3;  // 3 nights cannot fit in a 3-day window
    EXPECT_TRUE(trip::optimize(p, 1).empty());
}

TEST(Optimizer, RejectsMalformedInput) {
    trip::Problem p = empty_problem(2, 5, 1);
    p.depart_max = 9;
    EXPECT_THROW(trip::optimize(p, 1), std::invalid_argument);
    p = empty_problem(2, 5, 1);
    p.price.pop_back();
    EXPECT_THROW(trip::optimize(p, 1), std::invalid_argument);
    p = empty_problem(11, 2, 1);
    EXPECT_THROW(trip::optimize(p, 1), std::invalid_argument);
    EXPECT_THROW(trip::optimize(empty_problem(1, 2, 1), 0), std::invalid_argument);
}

// Property: on random small problems the k best objectives equal the k smallest
// values found by exhaustive enumeration, and every returned plan is a valid
// itinerary whose recomputed cost matches.
TEST(OptimizerProperty, MatchesBruteForceOnRandomProblems) {
    std::mt19937 rng(20261008);
    int feasible = 0;
    for (int trial = 0; trial < 3000; trial++) {
        const trip::Problem p = random_problem(rng);
        const int k = std::uniform_int_distribution<int>(1, 6)(rng);
        const auto plans = trip::optimize(p, k);
        const auto expected = oracle::all_costs(p);

        const size_t n = std::min(expected.size(), static_cast<size_t>(k));
        ASSERT_EQ(plans.size(), n) << "trial " << trial;
        for (size_t i = 0; i < n; i++) {
            ASSERT_EQ(plans[i].objective, expected[i]) << "trial " << trial << " rank " << i;
            expect_valid_plan(p, plans[i]);
        }
        if (!plans.empty()) feasible++;
    }
    // Guard against a generator that only makes infeasible problems (a vacuous pass).
    EXPECT_GT(feasible, 1000);
}

TEST(OptimizerProperty, SameInputSameOutput) {
    std::mt19937 rng(7);
    for (int trial = 0; trial < 200; trial++) {
        const trip::Problem p = random_problem(rng);
        const auto a = trip::optimize(p, 5), b = trip::optimize(p, 5);
        ASSERT_EQ(a.size(), b.size());
        for (size_t i = 0; i < a.size(); i++) {
            ASSERT_EQ(a[i].objective, b[i].objective);
            for (size_t j = 0; j < a[i].legs.size(); j++) {
                ASSERT_EQ(a[i].legs[j].to, b[i].legs[j].to);
                ASSERT_EQ(a[i].legs[j].day, b[i].legs[j].day);
                ASSERT_EQ(a[i].legs[j].mode, b[i].legs[j].mode);
            }
        }
    }
}

// Spec V4 target size: 8 cities, 30-day window, 3 modes, top 5. Prints the time;
// the budget is fixed after this first measurement, so only a loose bound here.
TEST(OptimizerPerformance, EightCitiesThirtyDays) {
    std::mt19937 rng(1);
    trip::Problem p = empty_problem(8, 30, 3);
    std::uniform_int_distribution<int> price(50, 900), minutes(30, 900);
    for (size_t i = 0; i < p.price.size(); i++) {
        p.price[i] = price(rng);
        p.minutes[i] = minutes(rng);
    }
    for (int c = 1; c <= 8; c++) {
        p.stay_min[static_cast<size_t>(c)] = 1;
        p.stay_max[static_cast<size_t>(c)] = 4;
    }
    p.depart_max = 7;
    const auto t0 = std::chrono::steady_clock::now();
    const auto plans = trip::optimize(p, 5);
    const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    std::printf("[perf] 8 cities, 30 days, 3 modes, k=5: %.1f ms\n", ms);
    ASSERT_EQ(plans.size(), 5u);
    for (const auto& plan : plans) expect_valid_plan(p, plan);
    EXPECT_LT(ms, 10000.0);
}

// The C interface used by WebAssembly must return exactly what the C++ API returns.
#include "trip/c_api.h"

TEST(CApi, MatchesCppApiOnRandomProblems) {
    std::mt19937 rng(99);
    for (int trial = 0; trial < 300; trial++) {
        const trip::Problem p = random_problem(rng);
        const int k = 4;
        const std::vector<double> price(p.price.begin(), p.price.end());
        const std::vector<double> minutes(p.minutes.begin(), p.minutes.end());
        const std::vector<double> lodging(p.lodging.begin(), p.lodging.end());
        std::vector<double> out(static_cast<size_t>(trip_output_size(p.visits, k)));
        const int n = trip_optimize(p.visits, p.days, p.modes, price.data(), minutes.data(), lodging.data(),
                                    p.stay_min.data(), p.stay_max.data(), p.depart_min, p.depart_max,
                                    static_cast<double>(p.cost_per_minute), k, out.data(),
                                    static_cast<int>(out.size()));
        const auto plans = trip::optimize(p, k);
        ASSERT_EQ(n, static_cast<int>(plans.size())) << trip_last_error();
        size_t r = 0;
        for (const auto& plan : plans) {
            ASSERT_EQ(out[r], static_cast<double>(plan.objective));
            r += 4;
            const size_t legs = static_cast<size_t>(out[r++]);
            ASSERT_EQ(legs, plan.legs.size());
            for (const auto& l : plan.legs) {
                ASSERT_EQ(out[r], l.from);
                ASSERT_EQ(out[r + 1], l.to);
                ASSERT_EQ(out[r + 2], l.day);
                ASSERT_EQ(out[r + 3], l.mode);
                r += 6;
            }
            r += 1 + 4 * static_cast<size_t>(out[r]);
        }
    }
}

TEST(CApi, RejectsNonIntegerMoneyAndSmallBuffers) {
    trip::Problem p = empty_problem(1, 2, 1);
    std::vector<double> price(p.price.begin(), p.price.end()), minutes(p.minutes.begin(), p.minutes.end()),
        lodging(p.lodging.begin(), p.lodging.end());
    std::vector<double> out(static_cast<size_t>(trip_output_size(1, 1)));
    price[0] = 10.5;
    EXPECT_EQ(trip_optimize(1, 2, 1, price.data(), minutes.data(), lodging.data(), p.stay_min.data(),
                            p.stay_max.data(), 0, 0, 0, 1, out.data(), static_cast<int>(out.size())), -1);
    price[0] = -1;
    EXPECT_EQ(trip_optimize(1, 2, 1, price.data(), minutes.data(), lodging.data(), p.stay_min.data(),
                            p.stay_max.data(), 0, 0, 0, 1, out.data(), 1), -2);
}
