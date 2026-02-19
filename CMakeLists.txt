cmake_minimum_required(VERSION 3.18)
project(SkinCore)

set(CMAKE_CXX_STANDARD 17)

# --- Python 3.11 (Maya2026) への強制設定 ---
set(Python3_EXECUTABLE "C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe" CACHE PATH "" FORCE)
set(Python3_INCLUDE_DIR "C:/Program Files/Autodesk/Maya2026/include/Python311/Python" CACHE PATH "" FORCE)
set(Python3_LIBRARY "C:/Program Files/Autodesk/Maya2026/lib/python311.lib" CACHE PATH "" FORCE)

set(PYBIND11_FINDPYTHON ON CACHE BOOL "" FORCE)
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

# --- pybind11 の取得 ---
include(FetchContent)
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11.git
  GIT_TAG        v2.12.0
)
FetchContent_MakeAvailable(pybind11)

# --- モジュールの作成 ---
pybind11_add_module(skin_core src/main.cpp)

if(MSVC)
    target_compile_options(skin_core PRIVATE /O2 /fp:fast)
else()
    target_compile_options(skin_core PRIVATE -O3 -ffast-math)
endif()