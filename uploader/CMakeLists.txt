cmake_minimum_required(VERSION 3.15)

project(uploader VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIERD ON)
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

FetchContent_MakeAvailable(httplib json)

add_library(parser src/parser.cpp)
target_include_directories(parser PUBLIC include)

add_library(client src/client.cpp)
target_include_directories(client PUBLIC include)
target_link_libraries(client PUBLIC httplib::httplib nlohmann_json::nlohmann_json)

add_executable(app src/main.cpp)
target_link_libraries(app PRIVATE parser)
target_link_libraries(app PRIVATE client)