cmake_minimum_required(VERSION 3.20)
project(trip_engine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(TRIP_BUILD_TESTS "Build native tests" ON)

add_library(trip_engine STATIC src/optimizer.cpp src/c_api.cpp)
target_include_directories(trip_engine PUBLIC include)
target_compile_options(trip_engine PRIVATE -Wall -Wextra -Werror -Wconversion -Wshadow)

if(EMSCRIPTEN)
  add_executable(engine src/c_api.cpp)
  target_link_libraries(engine PRIVATE trip_engine)
  set_target_properties(engine PROPERTIES SUFFIX ".mjs")
  target_link_options(engine PRIVATE "-sEXPORTED_FUNCTIONS=_trip_optimize,_trip_last_error,_trip_output_size,_malloc,_free" "-sMODULARIZE=1" "-sEXPORT_ES6=1" "-sALLOW_MEMORY_GROWTH=1" "-sENVIRONMENT=web,worker,node" "-sEXPORTED_RUNTIME_METHODS=UTF8ToString")
endif()

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

  add_executable(v4_gen tests/v4_gen.cpp)
  target_link_libraries(v4_gen PRIVATE trip_engine)
endif()
