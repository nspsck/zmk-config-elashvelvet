# SPDX-License-Identifier: MIT
if(CONFIG_ZMK_VELVET_DRAGON_DISPLAY)
  zephyr_library()
  zephyr_library_include_directories(${CMAKE_SOURCE_DIR}/include config)
  zephyr_library_sources(
    src/display/status_screen.c
    src/display/velvet_display.c
    src/display/dragon_assets.c
  )
endif()
