cmake_minimum_required (VERSION 2.8)
project (kfoam C Fortran)

set (CMAKE_NO_SYSTEM_FROM_IMPORTED yes)

if( CMAKE_VERSION VERSION_GREATER "3.0" )
  cmake_policy(SET CMP0042 OLD)
  cmake_policy(SET CMP0026 OLD)
endif()

find_package(MODENA REQUIRED)
include_directories(${MODENA_INCLUDE_DIRS})

find_package(LAPACK REQUIRED)
find_package(BLAS REQUIRED)

find_package(FSON REQUIRED)
include_directories(${FSON_INCLUDE_DIRS})

set(CMAKE_BUILD_TYPE Debug)

set (CMAKE_Fortran_FLAGS "-ffree-line-length-none -O3")
set (CMAKE_Fortran_MODULE_DIRECTORY mod)
file (GLOB _sources RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} src/*.f*)
add_executable(kfoam ${_sources})
target_link_libraries(
  kfoam 
  ${LAPACK_LIBRARIES}
  ${BLAS_LIBRARIES}
  MODENA::modena
  ${FSON_LIBRARIES}
)
