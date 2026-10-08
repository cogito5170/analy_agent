#include "trip/c_api.h"
#include "trip/optimizer.hpp"
#include <iostream>
#include <fstream>
#include <random>
#include <vector>
#include <chrono>
#include <algorithm>

using namespace trip;

void print_json_array(std::ostream& os, const std::vector<double>& v) {
    os << "[";
    for (size_t i = 0; i < v.size(); i++) {
        os << v[i] << (i + 1 == v.size() ? "" : ",");
    }
    os << "]";
}
void print_json_int_array(std::ostream& os, const std::vector<int32_t>& v) {
    os << "[";
    for (size_t i = 0; i < v.size(); i++) {
        os << v[i] << (i + 1 == v.size() ? "" : ",");
    }
    os << "]";
}

Problem empty_problem(int visits, int days, int modes) {
    Problem p;
    p.visits = visits; p.days = days; p.modes = modes;
    size_t nodes = static_cast<size_t>(visits + 2);
    p.price.assign(nodes * nodes * static_cast<size_t>(days) * static_cast<size_t>(modes), -1);
    p.minutes.assign(p.price.size(), 0);
    p.lodging.assign(nodes * static_cast<size_t>(days), 0);
    p.stay_min.assign(nodes, 0);
    p.stay_max.assign(nodes, 0);
    p.depart_min = 0; p.depart_max = days - 1;
    p.cost_per_minute = 0;
    return p;
}

Problem random_v5_problem(std::mt19937& rng) {
    std::uniform_int_distribution<int> price(0, 500), minutes(10, 600),
        lodge(0, 100), stay(0, 2), extra(0, 5), cpm(0, 3), percent(0, 99);
    Problem p = empty_problem(8, 30, 3);
    for (size_t i = 0; i < p.price.size(); i++) {
        p.price[i] = percent(rng) < 25 ? -1 : price(rng);
        p.minutes[i] = minutes(rng);
    }
    for (size_t i = 0; i < p.lodging.size(); i++) p.lodging[i] = lodge(rng);
    for (int c = 1; c <= p.visits; c++) {
        p.stay_min[c] = stay(rng);
        p.stay_max[c] = p.stay_min[c] + extra(rng);
    }
    p.depart_min = std::uniform_int_distribution<int>(0, p.days - 1)(rng);
    p.depart_max = std::uniform_int_distribution<int>(p.depart_min, p.days - 1)(rng);
    p.cost_per_minute = cpm(rng);
    return p;
}

int main() {
    std::mt19937 rng(12345);
    Problem p = random_v5_problem(rng);
    
    std::ofstream out("v5_problem.json");
    out << "{\n";
    out << "  \"visits\": " << p.visits << ",\n";
    out << "  \"days\": " << p.days << ",\n";
    out << "  \"modes\": " << p.modes << ",\n";
    std::vector<double> price(p.price.begin(), p.price.end());
    std::vector<double> minutes(p.minutes.begin(), p.minutes.end());
    std::vector<double> lodging(p.lodging.begin(), p.lodging.end());
    out << "  \"price\": "; print_json_array(out, price); out << ",\n";
    out << "  \"minutes\": "; print_json_array(out, minutes); out << ",\n";
    out << "  \"lodging\": "; print_json_array(out, lodging); out << ",\n";
    out << "  \"stay_min\": "; print_json_int_array(out, p.stay_min); out << ",\n";
    out << "  \"stay_max\": "; print_json_int_array(out, p.stay_max); out << ",\n";
    out << "  \"depart_min\": " << p.depart_min << ",\n";
    out << "  \"depart_max\": " << p.depart_max << ",\n";
    out << "  \"cost_per_minute\": " << p.cost_per_minute << ",\n";
    out << "  \"k\": 5\n";
    out << "}\n";
    out.close();

    std::vector<double> times;
    int k = 5;
    // warmup
    optimize(p, k);

    for (int i = 0; i < 5; i++) {
        auto t0 = std::chrono::high_resolution_clock::now();
        std::vector<Plan> plans = optimize(p, k);
        auto t1 = std::chrono::high_resolution_clock::now();
        times.push_back(std::chrono::duration<double, std::milli>(t1 - t0).count());
    }
    std::sort(times.begin(), times.end());
    std::cout << "Native V5 median time: " << times[2] << " ms\n";
    
    return 0;
}
