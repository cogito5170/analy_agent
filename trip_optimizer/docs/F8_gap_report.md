# F8 Day Plan Gap Report

## Requirements (SPEC 3.3)
SPEC 3.3 requires that day plans be generated for the trip, providing detailed itineraries within each destination, respecting time constraints, and balancing cost and time to propose a heuristic or exact sequence of activities.

## What Exists
Currently, there is no day plan generation logic. The optimizer only produces city-level legs and stays but does not schedule intraday visits or calculate the exact optimal route within a city.

## Proposed Measurement (Heuristic vs Exact)
We propose measuring the gap by computing both:
1. An exact optimal solution (e.g. using a brute-force approach or ILP solver) for a set of small test cases (up to 10 intra-city points).
2. The heuristic solution using the proposed fast approximation algorithm.

The gap will be measured as the average relative error in objective function value (Time Value + Cost):
`Gap = (Heuristic_Objective - Exact_Objective) / Exact_Objective`

In terms of performance, we will also report the ratio of execution times.
