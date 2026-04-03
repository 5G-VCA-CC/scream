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
rtp_video_extension.cpp
scream_sender.cpp
)

SET(SRC_RECEIVER
ScreamRx.cpp
Decoder.cpp
image.cc
sdl.cc
rtp_video_extension.cpp
scream_receiver.cpp
)

set(CMAKE_BUILD_TYPE Debug)

INCLUDE_DIRECTORIES(
${screamIncludes}
)

LINK_DIRECTORIES(
${screamLink}
)

ADD_EXECUTABLE(scream_bw_test_tx ${SRC_SENDER} ${HEADERS})
ADD_EXECUTABLE(scream_bw_test_rx ${SRC_RECEIVER} ${HEADERS})

TARGET_LINK_LIBRARIES (
scream_bw_test_tx
${screamLibs} pthread vpx
)

TARGET_LINK_LIBRARIES (
scream_bw_test_rx
${screamLibs} pthread vpx SDL2
)
