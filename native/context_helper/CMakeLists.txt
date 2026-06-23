cmake_minimum_required(VERSION 3.20)
project(sayit_context_helper LANGUAGES CXX)

add_executable(sayit_context_helper
  src/main.cpp
)

target_compile_features(sayit_context_helper PRIVATE cxx_std_17)
target_compile_definitions(sayit_context_helper PRIVATE UNICODE _UNICODE NOMINMAX)
target_link_libraries(sayit_context_helper PRIVATE
  user32
  ole32
  oleaut32
  oleacc
  uiautomationcore
  psapi
)

if (MSVC)
  target_compile_options(sayit_context_helper PRIVATE /W4 /EHsc)
endif()
