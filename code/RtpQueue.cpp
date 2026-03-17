#include "RtpQueue.h"
#include <iostream>
#include <string.h>
using namespace std;
/*
* Implements a simple RTP packet queue
*/

RtpQueueItem::RtpQueueItem() {
	used = false;
	size = 0;
	seqNr = 0;
	timeStamp = 0;
	packet = nullptr;
}


RtpQueue::RtpQueue() {
	sizeOfLastFrame = 0;
	bytesInQueue_ = 0;
	// sizeOfQueue_ = 0;
	sizeOfNextRtp_ = -1;
}

RtpQueue::~RtpQueue(){
	clear();
}

bool RtpQueue::push(void* rtpPacket, int size, uint32_t ssrc, unsigned short seqNr, bool isMark, float ts, uint32_t timeStamp) {
	std::unique_lock<std::mutex> lock(queue_operation_mutex_);
	if (queue_.size() >= kRtpQueueSize) {
		/*
		* RTP queue is full, do a drop tail i.e ignore new RTP packets
		*/
		return (false);
	}
	RtpQueueItem item;
	item.seqNr = seqNr;
	item.timeStamp = timeStamp;
	item.ssrc = ssrc;
	item.size = size;
	item.ts = ts;
	item.isMark = isMark;
	item.used = true;
	// sizeOfQueue_ += 1;
#ifndef IGNORE_PACKET
	item.packet = rtpPacket;
#endif
	queue_.push_back(item);
	bytesInQueue_ += size;
	computeSizeOfNextRtp();
	return (true);
}
bool RtpQueue::push_front(void* rtpPacket, int size, uint32_t ssrc, unsigned short seqNr, bool isMark, float ts, uint32_t timeStamp) {
    std::unique_lock<std::mutex> lock(queue_operation_mutex_);
    // If slot is occupied, queue is full
    if (queue_.size() >= kRtpQueueSize) {
        return false;
    }

    // Move tail backward to the new slot
    RtpQueueItem item;
	item.seqNr = seqNr;
	item.timeStamp = timeStamp;
	item.ssrc = ssrc;
	item.size = size;
	item.ts = ts;
	item.isMark = isMark;
	item.used = true;
#ifndef IGNORE_PACKET
    item.packet = rtpPacket;
#endif
	queue_.push_front(item);
    bytesInQueue_ += size;
    // sizeOfQueue_ += 1;

    computeSizeOfNextRtp();
    return true;
}
bool RtpQueue::pop(void** rtpPacket, int& size, uint32_t& ssrc, unsigned short& seqNr, bool& isMark, uint32_t& timeStamp)
{
	std::unique_lock<std::mutex> lock(queue_operation_mutex_);
	if (queue_.empty()) {
		*rtpPacket = NULL;
		sizeOfNextRtp_ = -1;
		return false;
	}
	RtpQueueItem &item = queue_.front();
	size = item.size;
#ifndef IGNORE_PACKET
		* rtpPacket = item.packet;
#endif
		seqNr = item.seqNr;
		timeStamp = item.timeStamp;
		ssrc = item.ssrc;
		isMark = item.isMark;
		/*
		* Thread safe update of tail to avoid that tail points outside
		*  array, which can cause e.g RtpQueue::getDelay to give a
		*  segmentation fault.
		* This should not really be needed because
		*  we use mutex to make the pop function atomic
		*/
		bytesInQueue_ -= size;
		queue_.pop_front();
		computeSizeOfNextRtp();
		return true;
}

void RtpQueue::computeSizeOfNextRtp() {
	if (queue_.empty()) {
		sizeOfNextRtp_ = -1;
	}
	else {
		sizeOfNextRtp_ = queue_.front().size;
	}
}

int RtpQueue::sizeOfNextRtp() {
	return sizeOfNextRtp_;
}

int RtpQueue::seqNrOfNextRtp() {
	if (queue_.empty()) {
		return -1;
	}
	else {
		return queue_.front().seqNr;
	}
}

int RtpQueue::seqNrOfLastRtp() {
	if (queue_.empty()) {
		return -1;
	}
	else {
		return queue_.back().seqNr;
	}
}

int RtpQueue::bytesInQueue() {
	return bytesInQueue_;
}

int RtpQueue::sizeOfQueue() {
	return queue_.size();
}

float RtpQueue::getDelay(float currTs) {
	if (queue_.empty()) {
		return 0;
	}
	else {
		return currTs - queue_.front().ts;
	}
}

bool RtpQueue::sendPacket(void** rtpPacket, int& size, uint32_t& ssrc, unsigned short& seqNr, bool& isMark, uint32_t& timeStamp) {
	if (sizeOfQueue() > 0) {
		pop(rtpPacket, size, ssrc, seqNr, isMark, timeStamp);
		return true;
	}
	return false;
}

#ifndef IGNORE_PACKET
extern void packet_free(void* buf, uint32_t ssrc);
#endif
int RtpQueue::clear() {
	uint16_t seqNr;
	uint32_t timeStamp;
	uint32_t ssrc;
	int freed = 0;
	int size;
	void* buf;
	while (sizeOfQueue() > 0) {
		bool isMark;
		pop(&buf, size, ssrc, seqNr, isMark, timeStamp);
		if (buf != NULL) {
			freed++;
#ifndef IGNORE_PACKET
			packet_free(buf, ssrc);
#endif
		}
	}
	return (freed);
}
