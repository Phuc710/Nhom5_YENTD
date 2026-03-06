cmake_minimum_required(VERSION 3.16.0)

set(EXTRA_COMPONENT_DIRS
    ${CMAKE_SOURCE_DIR}/managed_components
)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32-s3-cam-firmware)
