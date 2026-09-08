// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL

#include "framedump.h"

#include <atomic>
#include <cerrno>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

extern "C" {
#include <libavutil/frame.h>
#include <libavutil/hwcontext.h>
#include <libavutil/imgutils.h>
#include <libavutil/pixdesc.h>
#include <libavutil/pixfmt.h>
}

namespace {

// THE ON-DISK HEADER. Every field is fixed-width and little-endian, and every
// 8-byte field sits on an 8-byte offset, so this struct has no padding on any
// platform that matters and a reader can parse it with one struct format
// string. The static_asserts below are the only thing keeping that true: adding
// a field in the middle silently moves everything after it, and the reader in
// the other process would go on parsing happily and get nonsense.
struct FrameDumpHeader
{
	char     magic[4];         //   0
	uint32_t version;          //   4
	uint64_t seq_before;       //   8  written BEFORE the pixels
	uint64_t seq_after;        //  16  written AFTER the pixels
	uint32_t width;            //  24
	uint32_t height;           //  28
	uint32_t pix_fmt;          //  32  FRAME_DUMP_FMT_*
	uint32_t n_planes;         //  36
	uint32_t stride[4];        //  40
	uint32_t plane_offset[4];  //  56  from the start of the DATA area
	uint64_t frame_bytes;      //  72  packed size of the whole frame
	uint64_t timestamp_ns;     //  80  CLOCK_REALTIME, comparable to time.time_ns()
	uint64_t mono_ns;          //  88  CLOCK_MONOTONIC_RAW, diagnostics only
	uint64_t data_offset;      //  96
	uint64_t data_capacity;    // 104
	uint32_t dropped;          // 112  frames skipped: throttled, busy or refused
	// THE COLOUR METADATA IS RECORDED EVEN THOUGH NOTHING READS IT YET.
	// cv2's NV12/I420 conversions assume BT.601 limited range; a PS5 1080p
	// stream is usually BT.709. The difference is small on this game's
	// near-monochrome art and NOT ZERO, and a reader that wants to do the
	// right matrix later must not have to guess what the decoder said. These
	// are ffmpeg's own AVColorSpace / AVColorRange values, passed through
	// verbatim -- an unset frame reports AVCOL_SPC_UNSPECIFIED (2) /
	// AVCOL_RANGE_UNSPECIFIED (0), which is honest rather than invented.
	uint32_t color_space;      // 116  AVColorSpace
	uint32_t color_range;      // 120  AVColorRange
	// HOW LONG THE LAST PUSH TOOK, measured by the writer around its own work
	// and stored inside the same seqlock transaction as the pixels it
	// describes. This push runs on the ONE thread between decode and present,
	// so its cost is the only thing that can make turning the dump on visible
	// in the video -- and "it is cheap" is a claim until somebody can print a
	// number. tools/doctor.py prints this one.
	uint32_t push_us;          // 124
	// THE WRITER'S OWN THROTTLE, so the reader does not keep a second copy of
	// it. A constant mirrored by hand across two languages is this project's
	// recorded RELEASE_MS bug: the mirror rots and nothing fails until it
	// matters.
	uint32_t min_interval_ms;  // 128
	uint32_t reserved;         // 132
};

static_assert(sizeof(FrameDumpHeader) == 136, "header layout is parsed by frame_dump.py");
static_assert(offsetof(FrameDumpHeader, seq_before) == 8, "header layout");
static_assert(offsetof(FrameDumpHeader, seq_after) == 16, "header layout");
static_assert(offsetof(FrameDumpHeader, stride) == 40, "header layout");
static_assert(offsetof(FrameDumpHeader, plane_offset) == 56, "header layout");
static_assert(offsetof(FrameDumpHeader, frame_bytes) == 72, "header layout");
static_assert(offsetof(FrameDumpHeader, timestamp_ns) == 80, "header layout");
static_assert(offsetof(FrameDumpHeader, data_offset) == 96, "header layout");
static_assert(offsetof(FrameDumpHeader, dropped) == 112, "header layout");
static_assert(offsetof(FrameDumpHeader, color_space) == 116, "header layout");
static_assert(offsetof(FrameDumpHeader, color_range) == 120, "header layout");
static_assert(offsetof(FrameDumpHeader, push_us) == 124, "header layout");
static_assert(offsetof(FrameDumpHeader, min_interval_ms) == 128, "header layout");
static_assert(FRAME_DUMP_DATA_OFFSET >= sizeof(FrameDumpHeader), "header does not fit");

const size_t FILE_BYTES = (size_t)FRAME_DUMP_DATA_OFFSET + (size_t)FRAME_DUMP_CAPACITY;

std::atomic<bool> g_started{false};
unsigned char *g_map = nullptr;
int g_fd = -1;

// Throttle and mutual exclusion. FrameDumpPush is called from ONE thread today
// (chiaki's frame thread, the only caller of chiaki_ffmpeg_decoder_pull_frame),
// but "today" is exactly the assumption that rots, and a second caller would
// interleave two frames into one slot with no symptom other than a torn image.
std::atomic<long long> g_last_ms{0};
std::atomic<bool> g_busy{false};
std::atomic<unsigned> g_dropped{0};

// Only for a HARDWARE frame, which on this rig never happens: the caller
// pushes after prepareFrameForPresentation, which has already transferred
// every VideoToolbox frame to software. It is kept for the direct-render
// platforms (Vulkan, Linux VAAPI) where the frame really is still on the GPU
// at that point. Reused across dumps so the steady state allocates nothing;
// only ever touched under g_busy.
AVFrame *g_sw_frame = nullptr;

// One-shot log flags. A frame arrives 60 times a second; a per-frame complaint
// would fill the log faster than anything else in it and hide the reason.
bool g_logged_transfer_fail = false;
int g_logged_format = -1;
bool g_logged_too_big = false;

long long NowMs()
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	return (long long)ts.tv_sec * 1000LL + ts.tv_nsec / 1000000LL;
}

uint64_t MonoNs()
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

uint64_t RealtimeNs()
{
	struct timespec ts;
	clock_gettime(CLOCK_REALTIME, &ts);
	return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

// Sets g_busy for its lifetime. A bare flag with a `g_busy = false` at the end
// is a guard that stops working the day someone adds an early return above it —
// which is the shape half the bugs in this project's notes have.
struct BusyGuard
{
	bool held;
	explicit BusyGuard()
	{
		bool expected = false;
		held = g_busy.compare_exchange_strong(expected, true);
	}
	~BusyGuard()
	{
		if(held)
			g_busy.store(false);
	}
};

} // namespace

void FrameDumpStart()
{
	bool expected = false;
	if(!g_started.compare_exchange_strong(expected, true))
		return;
	const char *path = getenv("CHIAKI_FRAME_DUMP");
	if(!path || !*path)
		return;

	int fd = open(path, O_RDWR | O_CREAT, 0600);
	if(fd < 0)
	{
		fprintf(stderr, "[framedump] cannot open %s: %s\n", path, strerror(errno));
		return;
	}
	if(ftruncate(fd, (off_t)FILE_BYTES) != 0)
	{
		fprintf(stderr, "[framedump] cannot size %s to %zu bytes: %s\n",
				path, FILE_BYTES, strerror(errno));
		close(fd);
		return;
	}
	void *m = mmap(nullptr, FILE_BYTES, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if(m == MAP_FAILED)
	{
		fprintf(stderr, "[framedump] cannot map %s: %s\n", path, strerror(errno));
		close(fd);
		return;
	}

	// Publish an EMPTY, well-formed header before anything can read it. A
	// reader that finds seq 0 knows no frame has been written yet; a reader
	// that finds a stale magic knows the file is not ours. Leaving the old
	// contents of a pre-existing file in place would hand the reader whatever
	// frame the last run ended on, with a timestamp that might still be fresh.
	FrameDumpHeader *h = (FrameDumpHeader *)m;
	memset(h, 0, sizeof(*h));
	memcpy(h->magic, FRAME_DUMP_MAGIC, 4);
	h->version = FRAME_DUMP_VERSION;
	h->data_offset = FRAME_DUMP_DATA_OFFSET;
	h->data_capacity = FRAME_DUMP_CAPACITY;
	std::atomic_thread_fence(std::memory_order_release);

	g_fd = fd;
	g_map = (unsigned char *)m;
	fprintf(stderr, "[framedump] frame dump -> %s (%zu bytes, one slot, >= %dms apart)\n",
			path, FILE_BYTES, FRAME_DUMP_MIN_INTERVAL_MS);
}

bool FrameDumpEnabled()
{
	return g_map != nullptr;
}

void FrameDumpPush(AVFrame *frame)
{
	if(!g_map || !frame)
		return;

	// THROTTLE FIRST, and stamp the clock before the work rather than after, so
	// the interval bounds the RATE even when a dump runs long. Stamping after
	// would let a slow readback push the next dump out by its own duration and
	// the rate would sag under exactly the load it is meant to be bounded in.
	const long long now = NowMs();
	const long long last = g_last_ms.load(std::memory_order_relaxed);
	if(last != 0 && now - last < FRAME_DUMP_MIN_INTERVAL_MS)
	{
		g_dropped.fetch_add(1, std::memory_order_relaxed);
		return;
	}

	BusyGuard busy;
	if(!busy.held)
	{
		g_dropped.fetch_add(1, std::memory_order_relaxed);
		return;
	}
	g_last_ms.store(now, std::memory_order_relaxed);

	// THE COST CLOCK STARTS HERE, before any transfer, so push_us covers
	// everything this function does on the caller's thread once it has decided
	// to dump: the hardware transfer if there is one, the format checks and the
	// packed copy. Starting it after the transfer would measure the cheap half
	// and report it as the cost.
	const uint64_t push_t0 = MonoNs();

	AVFrame *src = frame;
	if(frame->hw_frames_ctx)
	{
		// A HARDWARE FRAME LIVES ON THE GPU and has no readable planes. On
		// macOS chiaki keeps VideoToolbox frames in hardware all the way to
		// libplacebo when zero-copy is available (QmlBackend::
		// prepareFrameForPresentation returns early on direct render), so this
		// is the NORMAL path here, not a corner.
		//
		// The transfer goes into OUR OWN frame. Touching the caller's would
		// change what the renderer presents, and the whole point of this file
		// is that turning it on cannot alter the stream.
		if(!g_sw_frame)
		{
			g_sw_frame = av_frame_alloc();
			if(!g_sw_frame)
				return;
		}
		av_frame_unref(g_sw_frame);
		if(av_hwframe_transfer_data(g_sw_frame, frame, 0) < 0)
		{
			if(!g_logged_transfer_fail)
			{
				g_logged_transfer_fail = true;
				const char *n = av_get_pix_fmt_name((AVPixelFormat)frame->format);
				fprintf(stderr, "[framedump] cannot transfer hardware frames (%s) — "
						"no frames will be dumped\n", n ? n : "unknown");
			}
			g_dropped.fetch_add(1, std::memory_order_relaxed);
			return;
		}
		// av_hwframe_transfer_data moves PIXELS ONLY. Without this the
		// colour metadata recorded below would be AVCOL_*_UNSPECIFIED on
		// every hardware frame -- a field that is always the same value and
		// reads as a measurement is worse than an absent one.
		av_frame_copy_props(g_sw_frame, frame);
		src = g_sw_frame;
	}

	uint32_t code = 0;
	if(src->format == AV_PIX_FMT_NV12)
		code = FRAME_DUMP_FMT_NV12;
	else if(src->format == AV_PIX_FMT_YUV420P)
		code = FRAME_DUMP_FMT_I420;
	else
	{
		// LOUD ONCE, THEN SILENT. A 10-bit stream transfers to P010 and a
		// reader would have no way to tell that from "the stream stopped": both
		// look like a stale dump. The log line is the only thing that names the
		// real cause, so it says the format by name.
		if(g_logged_format != src->format)
		{
			g_logged_format = src->format;
			const char *n = av_get_pix_fmt_name((AVPixelFormat)src->format);
			fprintf(stderr, "[framedump] pixel format %s is not dumpable "
					"(NV12 and YUV420P only) — falling back to the screen path\n",
					n ? n : "unknown");
		}
		g_dropped.fetch_add(1, std::memory_order_relaxed);
		return;
	}

	if(src->width <= 0 || src->height <= 0 || (src->width & 1) || (src->height & 1))
	{
		g_dropped.fetch_add(1, std::memory_order_relaxed);
		return;
	}

	const int need = av_image_get_buffer_size((AVPixelFormat)src->format,
			src->width, src->height, 1);
	if(need <= 0 || (size_t)need > (size_t)FRAME_DUMP_CAPACITY)
	{
		if(!g_logged_too_big)
		{
			g_logged_too_big = true;
			fprintf(stderr, "[framedump] %dx%d needs %d bytes, slot holds %u — "
					"refusing rather than truncating\n",
					src->width, src->height, need, (unsigned)FRAME_DUMP_CAPACITY);
		}
		g_dropped.fetch_add(1, std::memory_order_relaxed);
		return;
	}

	FrameDumpHeader *h = (FrameDumpHeader *)g_map;
	const uint64_t s = h->seq_after + 1;

	h->seq_before = s;
	std::atomic_thread_fence(std::memory_order_release);

	const uint32_t w = (uint32_t)src->width, ht = (uint32_t)src->height;
	h->width = w;
	h->height = ht;
	h->pix_fmt = code;
	memset(h->stride, 0, sizeof(h->stride));
	memset(h->plane_offset, 0, sizeof(h->plane_offset));
	// align=1 in the copy below means every plane is written PACKED, so these
	// follow from the format alone. They are recorded anyway: a reader that
	// derives them instead of reading them is a second copy of this arithmetic
	// that nothing keeps in step.
	if(code == FRAME_DUMP_FMT_NV12)
	{
		h->n_planes = 2;
		h->stride[0] = w;          h->plane_offset[0] = 0;
		h->stride[1] = w;          h->plane_offset[1] = w * ht;
	}
	else
	{
		h->n_planes = 3;
		h->stride[0] = w;          h->plane_offset[0] = 0;
		h->stride[1] = w / 2;      h->plane_offset[1] = w * ht;
		h->stride[2] = w / 2;      h->plane_offset[2] = w * ht + (w / 2) * (ht / 2);
	}
	h->frame_bytes = (uint64_t)need;
	h->timestamp_ns = RealtimeNs();
	h->mono_ns = MonoNs();
	h->dropped = g_dropped.load(std::memory_order_relaxed);
	h->color_space = (uint32_t)src->colorspace;
	h->color_range = (uint32_t)src->color_range;
	h->min_interval_ms = (uint32_t)FRAME_DUMP_MIN_INTERVAL_MS;

	av_image_copy_to_buffer(g_map + FRAME_DUMP_DATA_OFFSET, (int)FRAME_DUMP_CAPACITY,
			(const uint8_t *const *)src->data, src->linesize,
			(AVPixelFormat)src->format, src->width, src->height, 1);

	// INSIDE THE TRANSACTION, and it has to be: push_us is part of the header
	// the reader copies between latching seq_after and re-reading seq_before,
	// so writing it after the fence below would be a field that can tear while
	// every other field is protected. Written last because its value is not
	// known until the copy above is done.
	h->push_us = (uint32_t)((MonoNs() - push_t0) / 1000ULL);

	std::atomic_thread_fence(std::memory_order_release);
	h->seq_after = s;
}

// THERE IS NO FrameDumpStop. There was one, and nothing called it, while
// framedump.h told the reader it existed "for process shutdown" -- a wiring
// that was documented and absent, which is the shape half this project's notes
// are about. See the long note in the header for why the fix was to delete it
// rather than to call it: the mapping is process-lifetime, the OS reclaims it,
// and unmapping underneath a frame thread that is mid-push is a SIGBUS, not a
// tidy-up.
