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
}


RtpQueue::RtpQueue() {
	sizeOfLastFrame = 0;
	bytesInQueue_ = 0;
	sizeOfQueue_ = 0;
	sizeOfNextRtp_ = -1;
}

bool RtpQueue::push(void* rtpPacket, int size, uint32_t ssrc, unsigned short seqNr, bool isMark, float ts, uint32_t timeStamp) {
	std::unique_lock<std::mutex> lock(queue_operation_mutex_);
	if ((int)items.size() >= kRtpQueueSize) {
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
#ifndef IGNORE_PACKET
	item.packet = rtpPacket;
#endif
	items.push_back(item);
	bytesInQueue_ += size;
	sizeOfQueue_ = static_cast<int>(items.size());
	computeSizeOfNextRtp();
	return (true);
}

bool RtpQueue::pushFront(void* rtpPacket, int size, uint32_t ssrc, unsigned short seqNr, bool isMark, float ts, uint32_t timeStamp) {
	std::unique_lock<std::mutex> lock(queue_operation_mutex_);
	if ((int)items.size() >= kRtpQueueSize) {
		return false;
	}
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
	items.push_front(item);
	bytesInQueue_ += size;
	sizeOfQueue_ = static_cast<int>(items.size());
	computeSizeOfNextRtp();
	return (true);
}
bool RtpQueue::pop(void** rtpPacket, int& size, uint32_t& ssrc, unsigned short& seqNr, bool& isMark, uint32_t& timeStamp)
{
	std::unique_lock<std::mutex> lock(queue_operation_mutex_);
	if (items.empty()) {
		*rtpPacket = NULL;
		sizeOfNextRtp_ = -1;
		return false;
	}
	RtpQueueItem item = items.front();
	items.pop_front();
	size = item.size;

#ifndef IGNORE_PACKET
		*rtpPacket = item.packet;
#endif
	seqNr = item.seqNr;
	timeStamp = item.timeStamp;
	ssrc = item.ssrc;
	isMark = item.isMark;
	bytesInQueue_ -= size;
	sizeOfQueue_ = static_cast<int>(items.size());
	computeSizeOfNextRtp();
	return true;
}

void RtpQueue::computeSizeOfNextRtp() {
	if (items.empty()) {
		sizeOfNextRtp_ = -1;
	}
	else {
		sizeOfNextRtp_ = items.front().size;
	}
}

int RtpQueue::sizeOfNextRtp() {
	return sizeOfNextRtp_;
}

int RtpQueue::seqNrOfNextRtp() {
	if (items.empty()) {
		return -1;
	}
	else {
		return items.front().seqNr;
	}
}

int RtpQueue::seqNrOfLastRtp() {
	if (items.empty()) {
		return -1;
	}
	else {
		return items.back().seqNr;
	}
}

int RtpQueue::bytesInQueue() {
	return bytesInQueue_;
}

int RtpQueue::sizeOfQueue() {
	return sizeOfQueue_;
}

float RtpQueue::getDelay(float currTs) {
	if (items.empty()) {
		return 0;
	}
	else {
		return currTs - items.front().ts;
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
