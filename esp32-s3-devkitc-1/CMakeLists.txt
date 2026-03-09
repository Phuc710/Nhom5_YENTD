#
# CMakeLists.txt cap goc cua project ESP-IDF.
# File nay KHONG dang ky source .c.
# Nhiem vu cua no chi la:
# - nap he thong CMake cua ESP-IDF
# - khai bao managed components
# - khai bao ten project
#
cmake_minimum_required(VERSION 3.16.0)
set(PROJECT_VER "1.0.0")

if(EXISTS "${CMAKE_SOURCE_DIR}/managed_components")
    set(EXTRA_COMPONENT_DIRS
        ${CMAKE_SOURCE_DIR}/managed_components
    )
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32-s3-cam-firmware)
