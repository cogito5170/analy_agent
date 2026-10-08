#include "trip/c_api.h"
#include "trip/optimizer.hpp"
#include <iostream>
#include <random>
#include <vector>
#include <iomanip>

void print_json_array(const std::vector<double>& v) {
    std::cout << "[";
    for (size_t i = 0; i < v.size(); i++) {
        std::cout << v[i] << (i + 1 == v.size() ? "" : ",");
    }
    std::cout << "]";
}
void print_json_int_array(const std::vector<int>& v) {
    std::cout << "[";
    for (size_t i = 0; i < v.size(); i++) {
        std::cout << v[i] << (i + 1 == v.size() ? "" : ",");
    }
    std::cout << "]";
}

trip::Problem empty_problem(int visits, int days, int modes) {
    trip::Problem p;
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

trip::Problem random_problem(std::mt19937& rng) {
    std::uniform_int_distribution<int> visits(1, 8), days(2, 30), modes(1, 2), price(0, 500), minutes(10, 600),
        lodge(0, 100), stay(0, 2), extra(0, 5), cpm(0, 3), percent(0, 99);
    trip::Problem p = empty_problem(visits(rng), days(rng), modes(rng));
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

void print_problem(const trip::Problem& p, int k, int out_len_override, bool is_last, bool fractional_price = false) {
    std::vector<double> price(p.price.begin(), p.price.end());
    std::vector<double> minutes(p.minutes.begin(), p.minutes.end());
    std::vector<double> lodging(p.lodging.begin(), p.lodging.end());
    if (fractional_price && !price.empty()) price[0] = 10.5;
    
    int req_len = trip_output_size(p.visits, k);
    int actual_len = out_len_override >= 0 ? out_len_override : req_len;
    std::vector<double> out(static_cast<size_t>(actual_len));
    
    int n = trip_optimize(p.visits, p.days, p.modes, price.data(), minutes.data(), lodging.data(),
                          p.stay_min.data(), p.stay_max.data(), p.depart_min, p.depart_max,
                          static_cast<double>(p.cost_per_minute), k, out.data(), actual_len);
    
    std::cout << "  {\n";
    std::cout << "    \"visits\": " << p.visits << ",\n";
    std::cout << "    \"days\": " << p.days << ",\n";
    std::cout << "    \"modes\": " << p.modes << ",\n";
    std::cout << "    \"price\": "; print_json_array(price); std::cout << ",\n";
    std::cout << "    \"minutes\": "; print_json_array(minutes); std::cout << ",\n";
    std::cout << "    \"lodging\": "; print_json_array(lodging); std::cout << ",\n";
    std::cout << "    \"stay_min\": "; print_json_int_array(p.stay_min); std::cout << ",\n";
    std::cout << "    \"stay_max\": "; print_json_int_array(p.stay_max); std::cout << ",\n";
    std::cout << "    \"depart_min\": " << p.depart_min << ",\n";
    std::cout << "    \"depart_max\": " << p.depart_max << ",\n";
    std::cout << "    \"cost_per_minute\": " << p.cost_per_minute << ",\n";
    std::cout << "    \"k\": " << k << ",\n";
    std::cout << "    \"out_len\": " << actual_len << ",\n";
    std::cout << "    \"expected_n\": " << n << ",\n";
    if (n > 0) {
        // Output array depends on how many plans actually returned. Wait, the problem says 
        // "output array exactly", so just print the filled part, or the entire out array?
        // Let's print the entire out array up to the filled part, or the whole buffer.
        // The WASM should produce exactly the same n and we will just compare what's valid.
        // Actually, if we just slice the array up to the written parts it's better.
        // But the C api test says: r += 4 + ...
        // We'll just output the full out array we passed to C.
    }
    std::cout << "    \"expected_out\": "; print_json_array(out); std::cout << "\n";
    std::cout << "  }" << (is_last ? "" : ",") << "\n";
}

int main() {
    std::cout << std::setprecision(17);
    std::cout << "[\n";
    std::mt19937 rng(99);
    
    // Normal / infeasible random problems
    for (int i = 0; i < 1010; i++) {
        trip::Problem p = random_problem(rng);
        print_problem(p, 4, -1, false);
    }
    
    // Edge case: input error (negative price)
    trip::Problem p_err = empty_problem(1, 2, 1);
    print_problem(p_err, 1, -1, false, true);
    
    // Edge case: buffer too small
    trip::Problem p_buf = empty_problem(1, 2, 1);
    print_problem(p_buf, 1, 1, true); // out_len = 1
    
    std::cout << "]\n";
    return 0;
}
