# source files

SET(HEADERS
ScreamRx.h
ScreamTx.h
RtpQueue.h
)

SET(SRC_SENDER
ScreamTx.cpp
ScreamV2Tx.cpp
ScreamV2TxStream.cpp
RtpQueue.cpp
Encoder.cpp
scream_sender.cpp
Encoder.cpp
)

SET(SRC_RECEIVER
ScreamRx.cpp
Decoder.cpp
image.cc
sdl.cc
scream_receiver.cpp
	sdl.cc
Decoder.cpp
)

set(CMAKE_BUILD_TYPE Debug)

INCLUDE_DIRECTORIES(
${screamIncludes}
)

LINK_DIRECTORIES(
${screamLink}
)

ADD_EXECUTABLE(scream_bw_test_tx ${SRC_SENDER} ${HEADERS})
find_package(PkgConfig)
pkg_check_modules(VPX REQUIRED vpx)
if (VPX_FOUND)
	target_include_directories(scream_bw_test_tx PRIVATE ${VPX_INCLUDE_DIRS})
	target_link_libraries(scream_bw_test_tx ${VPX_LIBRARIES})
endif()
ADD_EXECUTABLE(scream_bw_test_rx ${SRC_RECEIVER} ${HEADERS})
find_package(SDL2 REQUIRED)
if (SDL2_FOUND)
	target_include_directories(scream_bw_test_rx PRIVATE ${SDL2_INCLUDE_DIRS})
	target_link_libraries(scream_bw_test_rx ${SDL2_LIBRARIES})
endif()
pkg_check_modules(VPX_REQUIRED vpx)
if (VPX_REQUIRED_FOUND)
	target_include_directories(scream_bw_test_rx PRIVATE ${VPX_REQUIRED_INCLUDE_DIRS})
	target_link_libraries(scream_bw_test_rx ${VPX_REQUIRED_LIBRARIES})
else()
	# try linking generic vpx lib if pkg-config name not found
	target_link_libraries(scream_bw_test_rx vpx)
endif()

TARGET_LINK_LIBRARIES (
scream_bw_test_tx
${screamLibs} pthread vpx
)

TARGET_LINK_LIBRARIES (
scream_bw_test_rx
${screamLibs} pthread vpx SDL2
)
