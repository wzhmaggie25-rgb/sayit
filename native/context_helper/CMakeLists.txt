cmake_minimum_required(VERSION 3.20)
project(sayit_context_helper LANGUAGES CXX)

# EXE target (stdin/stdout JSON-RPC server, legacy fallback)
add_executable(sayit_context_helper
  src/main.cpp
)

# DLL target (in-process UIA via koffi FFI)
add_library(sayit_context_helper_dll SHARED
  src/main.cpp
)

# Keyboard helper DLL (WH_KEYBOARD_LL hook, Typeless architecture)
add_library(sayit_keyboard_helper SHARED
  src/keyboard_helper.cpp
)

target_compile_definitions(sayit_context_helper_dll PRIVATE BUILD_DLL)

foreach(tgt sayit_context_helper sayit_context_helper_dll sayit_keyboard_helper)
  target_compile_features(${tgt} PRIVATE cxx_std_17)
  target_compile_definitions(${tgt} PRIVATE UNICODE _UNICODE NOMINMAX)
  target_link_libraries(${tgt} PRIVATE
    user32
    ole32
    oleaut32
    oleacc
    uiautomationcore
    psapi
  )
  if (MSVC)
    target_compile_options(${tgt} PRIVATE /W4 /EHsc)
  endif()
endforeach()