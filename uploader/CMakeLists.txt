cmake_minimum_required(VERSION 3.15)

project(uploader VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

include(FetchContent)

FetchContent_Declare(
    httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
    GIT_TAG v0.18.3
)

FetchContent_Declare(
    json
    URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
)

FetchContent_Declare(
    doctest
    GIT_REPOSITORY https://github.com/doctest/doctest.git
    GIT_TAG v2.4.11
    SOURCE_SUBDIR do-not-build-doctest
)

FetchContent_MakeAvailable(httplib json doctest)

add_library(doctest_header INTERFACE)
target_include_directories(doctest_header INTERFACE ${doctest_SOURCE_DIR})

add_library(parser src/parser.cpp)
target_include_directories(parser PUBLIC include)

add_library(client src/client.cpp)
target_include_directories(client PUBLIC include)
target_link_libraries(client PUBLIC httplib::httplib nlohmann_json::nlohmann_json)

add_executable(app src/main.cpp)
target_link_libraries(app PRIVATE parser client)

enable_testing()
add_executable(tests tests/test_parser.cpp)
target_link_libraries(tests PRIVATE parser doctest_header)
add_test(NAME tests COMMAND tests)
