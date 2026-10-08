cmake_minimum_required(VERSION 3.20)
project(trip_engine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(TRIP_BUILD_TESTS "Build native tests" ON)

add_library(trip_engine STATIC src/optimizer.cpp src/c_api.cpp)
target_include_directories(trip_engine PUBLIC include)
target_compile_options(trip_engine PRIVATE -Wall -Wextra -Werror -Wconversion -Wshadow)

if(TRIP_BUILD_TESTS AND NOT EMSCRIPTEN)
  include(FetchContent)
  FetchContent_Declare(googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.15.2
    GIT_SHALLOW TRUE)
  set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  enable_testing()
  add_executable(trip_tests tests/test_optimizer.cpp)
  target_link_libraries(trip_tests PRIVATE trip_engine GTest::gtest_main)
  include(GoogleTest)
  gtest_discover_tests(trip_tests)
endif()
