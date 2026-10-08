cmake_minimum_required(VERSION 3.20)
project(bms_firmware C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(BMS_BUILD_TESTS "Build host unit tests" ON)
option(BMS_COVERAGE "Instrument for gcov coverage" OFF)

# Debug info embeds absolute source paths, so without this map two checkouts in
# different directories produce different Debug libraries. CI checks this.
add_compile_options(-Wall -Wextra -Werror -Wconversion -Wshadow
                    "-ffile-prefix-map=${CMAKE_SOURCE_DIR}=.")

add_library(bms STATIC src/bms.c)
target_include_directories(bms PUBLIC include)

if(BMS_COVERAGE)
  target_compile_options(bms PRIVATE --coverage -O0)
  target_link_options(bms PUBLIC --coverage)
endif()

if(BMS_BUILD_TESTS AND NOT CMAKE_CROSSCOMPILING)
  include(FetchContent)
  FetchContent_Declare(unity
    GIT_REPOSITORY https://github.com/ThrowTheSwitch/Unity.git
    GIT_TAG v2.6.0
    GIT_SHALLOW TRUE)
  FetchContent_MakeAvailable(unity)

  enable_testing()
  add_executable(test_bms_state test/test_bms_state.c)
  target_link_libraries(test_bms_state PRIVATE bms unity)
  add_test(NAME test_bms_state COMMAND test_bms_state)
endif()
