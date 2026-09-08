// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
//
// THE WRITER'S OWN CHECKS. Everything about framedump.cpp used to be verified
// by reading it: the throttle, the busy guard, the seqlock write ordering, the
// format refusals, and the packed layout the Python reader parses. Four mutants
// were run against the frame-dump patch on 2026-09-08 and all four mutated
// frame_dump.py -- the READER -- so a writer that packed its planes wrongly,
// published a torn frame, or ignored its own throttle would have been caught by
// nothing at all. The reader's tests build their fixtures by hand, so the two
// languages agreed with each other about a format neither of them had ever seen
// this code produce.
//
// So this file drives the REAL framedump.cpp, with real AVFrames, and reads the
// mapping back exactly the way frame_dump.py does. It is the only thing that
// checks the C++ side actually writes what both sides believe.
//
// ONE SCENARIO PER PROCESS, chosen by argv[1]. FrameDumpStart() latches
// g_started on purpose (a stray second call must not be able to re-read the
// environment and re-create the mapping), so a fresh process per scenario is
// the only honest way to test more than one -- and it makes each scenario a
// genuinely cold start rather than a state left by the one before.

#include <atomic>
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

extern "C" {
#include <libavutil/frame.h>
#include <libavutil/imgutils.h>
#include <libavutil/pixfmt.h>
}

#include "framedump.h"

static const char *CORRECT = "correctness";
static const char *TIMING = "timing";

static int n_pass = 0, n_fail = 0, n_inconc = 0;

static void result(const char *verdict, const char *kind, const char *name,
                   const std::string &detail)
{
	printf("RESULT %-6s %-11s | %-52s | %s\n", verdict, kind, name, detail.c_str());
	fflush(stdout);
}
static void pass(const char *kind, const char *name, const std::string &d)
{ n_pass++; result("PASS", kind, name, d); }
static void fail(const char *kind, const char *name, const std::string &d)
{ n_fail++; result("FAIL", kind, name, d); }
// NOT a pass. A concurrency check that never got a sample proves nothing, and
// the driver fails a run that contains one.
static void inconc(const char *name, const std::string &d)
{ n_inconc++; result("INCONC", TIMING, name, d); }

static void check(const char *kind, const char *name, bool ok, const std::string &d)
{ if(ok) pass(kind, name, d); else fail(kind, name, d); }

static std::string fmt(const char *f, ...)
{
	char buf[1024];
	va_list ap;
	va_start(ap, f);
	vsnprintf(buf, sizeof(buf), f, ap);
	va_end(ap);
	return std::string(buf);
}

// ---------------------------------------------------------------------------
// THE READER, written here from framedump.h's specification ALONE.
//
// It deliberately does not include the writer's private struct: this is a
// SECOND implementation of the layout, the same way frame_dump.py is a third.
// If it shared a definition with the writer it could not catch a layout the
// writer got wrong, which is the whole point.
// ---------------------------------------------------------------------------
struct Hdr
{
	char magic[4];
	uint32_t version;
	uint64_t seq_before, seq_after;
	uint32_t width, height, pix_fmt, n_planes;
	uint32_t stride[4], plane_offset[4];
	uint64_t frame_bytes, timestamp_ns, mono_ns, data_offset, data_capacity;
	uint32_t dropped, color_space, color_range, push_us, min_interval_ms, reserved;
};
static_assert(sizeof(Hdr) == 136, "the reader's idea of the header");

static uint64_t realtime_ns()
{
	struct timespec ts;
	clock_gettime(CLOCK_REALTIME, &ts);
	return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static void sleep_ms(int ms)
{ std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

// A whole-file read. Not mmap: reading through a different mechanism than the
// writer used is one more thing that has to agree.
static std::vector<unsigned char> slurp(const char *path)
{
	std::vector<unsigned char> out;
	int fd = open(path, O_RDONLY);
	if(fd < 0)
		return out;
	struct stat st;
	if(fstat(fd, &st) == 0 && st.st_size > 0)
	{
		out.resize((size_t)st.st_size);
		ssize_t got = 0, want = (ssize_t)out.size();
		while(got < want)
		{
			ssize_t r = read(fd, out.data() + got, (size_t)(want - got));
			if(r <= 0)
				break;
			got += r;
		}
		out.resize((size_t)got);
	}
	close(fd);
	return out;
}

// ---------------------------------------------------------------------------
// Frames. The buffers are allocated with av_frame_get_buffer(align=64), so the
// linesizes are PADDED -- linesize[0] > width. That is on purpose: the writer
// claims it publishes every plane PACKED, and a frame whose source rows are
// already packed could not tell a real packing from a straight memcpy of the
// whole buffer.
// ---------------------------------------------------------------------------
static AVFrame *make_frame(int w, int h, AVPixelFormat pf, unsigned char seed)
{
	AVFrame *f = av_frame_alloc();
	if(!f)
		return nullptr;
	f->format = pf;
	f->width = w;
	f->height = h;
	if(av_frame_get_buffer(f, 64) < 0)
	{
		av_frame_free(&f);
		return nullptr;
	}
	// Every byte a function of (plane, x, y, seed), so a swapped plane, a row
	// off by one, or a stride taken from the source instead of the width all
	// show up as a mismatch at a named offset rather than as "the picture
	// looks wrong".
	for(int p = 0; p < 4 && f->data[p]; p++)
	{
		int ph = (p == 0) ? h : h / 2;
		int pw = f->linesize[p];
		for(int y = 0; y < ph; y++)
			for(int x = 0; x < pw; x++)
				f->data[p][(size_t)y * f->linesize[p] + x] =
						(unsigned char)(seed + p * 37 + y * 5 + x * 3);
	}
	return f;
}

// Fill every plane with ONE value, so a reader can tell a torn frame from a
// whole one without knowing which frame it caught.
static AVFrame *make_flat_frame(int w, int h, AVPixelFormat pf, unsigned char v)
{
	AVFrame *f = av_frame_alloc();
	if(!f)
		return nullptr;
	f->format = pf;
	f->width = w;
	f->height = h;
	if(av_frame_get_buffer(f, 64) < 0)
	{
		av_frame_free(&f);
		return nullptr;
	}
	for(int p = 0; p < 4 && f->data[p]; p++)
	{
		int ph = (p == 0) ? h : h / 2;
		memset(f->data[p], v, (size_t)ph * f->linesize[p]);
	}
	return f;
}

// What the packed plane SHOULD be, built from the source frame independently of
// av_image_copy_to_buffer.
static bool planes_match_packed(const AVFrame *f, const unsigned char *data,
                                const Hdr &h, std::string &why)
{
	const int w = f->width, ht = f->height;
	int nplanes = (f->format == AV_PIX_FMT_NV12) ? 2 : 3;
	for(int p = 0; p < nplanes; p++)
	{
		const int pw = (p == 0) ? w : ((f->format == AV_PIX_FMT_NV12) ? w : w / 2);
		const int ph = (p == 0) ? ht : ht / 2;
		const unsigned char *dst = data + h.plane_offset[p];
		for(int y = 0; y < ph; y++)
		{
			const unsigned char *srow = f->data[p] + (size_t)y * f->linesize[p];
			const unsigned char *drow = dst + (size_t)y * h.stride[p];
			if(memcmp(srow, drow, (size_t)pw) != 0)
			{
				why = fmt("plane %d row %d differs (stride %u, source linesize %d)",
				          p, y, h.stride[p], f->linesize[p]);
				return false;
			}
		}
	}
	return true;
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

// The claim framedump.h opens with: unset CHIAKI_FRAME_DUMP and this file is
// inert. Nothing had ever executed that path.
static void scenario_disabled(const char *path)
{
	unsetenv("CHIAKI_FRAME_DUMP");
	FrameDumpStart();
	check(CORRECT, "unset CHIAKI_FRAME_DUMP leaves the dump disabled",
	      !FrameDumpEnabled(), "FrameDumpEnabled() == false");

	AVFrame *f = make_frame(64, 64, AV_PIX_FMT_NV12, 11);
	if(!f)
	{
		fail(CORRECT, "a frame can be allocated", "av_frame_get_buffer failed");
		return;
	}
	FrameDumpPush(f);          // must be a load and a return, and must not crash
	FrameDumpPush(nullptr);    // and a null frame must not either
	av_frame_free(&f);

	struct stat st;
	check(CORRECT, "...and pushing writes no file at all",
	      stat(path, &st) != 0, fmt("stat(%s) %s", path,
	                                stat(path, &st) == 0 ? "FOUND A FILE" : "absent"));
}

// The layout contract, which is the thing frame_dump.py now trusts rather than
// re-derives.
static void scenario_roundtrip(const char *path, AVPixelFormat pf, const char *label)
{
	setenv("CHIAKI_FRAME_DUMP", path, 1);
	FrameDumpStart();
	if(!FrameDumpEnabled())
	{
		fail(CORRECT, "the mapping opens", fmt("FrameDumpEnabled() false for %s", path));
		return;
	}

	const int W = 320, H = 180;
	AVFrame *f = make_frame(W, H, pf, 7);
	if(!f)
	{
		fail(CORRECT, "a frame can be allocated", "av_frame_get_buffer failed");
		return;
	}
	const uint64_t before = realtime_ns();
	FrameDumpPush(f);
	const uint64_t after = realtime_ns();

	std::vector<unsigned char> buf = slurp(path);
	if(buf.size() < 4096)
	{
		fail(CORRECT, fmt("%s: the dump file is readable", label).c_str(),
		     fmt("%zu bytes", buf.size()));
		av_frame_free(&f);
		return;
	}
	Hdr h;
	memcpy(&h, buf.data(), sizeof(h));

	check(CORRECT, fmt("%s: magic and version", label).c_str(),
	      memcmp(h.magic, "CHFD", 4) == 0 && h.version == FRAME_DUMP_VERSION,
	      fmt("magic %.4s version %u (want %u)", h.magic, h.version, FRAME_DUMP_VERSION));
	check(CORRECT, fmt("%s: the seqlock closed on one frame", label).c_str(),
	      h.seq_before == 1 && h.seq_after == 1,
	      fmt("seq_before %llu seq_after %llu",
	          (unsigned long long)h.seq_before, (unsigned long long)h.seq_after));
	check(CORRECT, fmt("%s: geometry", label).c_str(),
	      h.width == (uint32_t)W && h.height == (uint32_t)H,
	      fmt("%ux%u", h.width, h.height));

	const uint32_t want_fmt = (pf == AV_PIX_FMT_NV12) ? FRAME_DUMP_FMT_NV12
	                                                  : FRAME_DUMP_FMT_I420;
	const uint32_t want_planes = (pf == AV_PIX_FMT_NV12) ? 2u : 3u;
	check(CORRECT, fmt("%s: format code and plane count", label).c_str(),
	      h.pix_fmt == want_fmt && h.n_planes == want_planes,
	      fmt("pix_fmt %u (want %u), n_planes %u (want %u)",
	          h.pix_fmt, want_fmt, h.n_planes, want_planes));

	// THE STRIDES AND OFFSETS THE READER IS ABOUT TO BELIEVE. framedump.h says
	// every plane is packed; if these do not say so, the reader reshaping by
	// them gets a sheared picture and no error.
	bool strides_ok, offsets_ok;
	if(pf == AV_PIX_FMT_NV12)
	{
		strides_ok = h.stride[0] == (uint32_t)W && h.stride[1] == (uint32_t)W;
		offsets_ok = h.plane_offset[0] == 0
				&& h.plane_offset[1] == (uint32_t)(W * H);
	}
	else
	{
		strides_ok = h.stride[0] == (uint32_t)W && h.stride[1] == (uint32_t)(W / 2)
				&& h.stride[2] == (uint32_t)(W / 2);
		offsets_ok = h.plane_offset[0] == 0
				&& h.plane_offset[1] == (uint32_t)(W * H)
				&& h.plane_offset[2] == (uint32_t)(W * H + (W / 2) * (H / 2));
	}
	check(CORRECT, fmt("%s: every plane stride equals its width (PACKED)", label).c_str(),
	      strides_ok, fmt("stride %u/%u/%u for %dx%d",
	                      h.stride[0], h.stride[1], h.stride[2], W, H));
	check(CORRECT, fmt("%s: plane offsets follow the packed layout", label).c_str(),
	      offsets_ok, fmt("offsets %u/%u/%u", h.plane_offset[0],
	                      h.plane_offset[1], h.plane_offset[2]));
	check(CORRECT, fmt("%s: frame_bytes is w*h*3/2", label).c_str(),
	      h.frame_bytes == (uint64_t)W * H * 3 / 2,
	      fmt("%llu (want %d)", (unsigned long long)h.frame_bytes, W * H * 3 / 2));
	check(CORRECT, fmt("%s: data_offset and capacity", label).c_str(),
	      h.data_offset == FRAME_DUMP_DATA_OFFSET
	          && h.data_capacity == FRAME_DUMP_CAPACITY,
	      fmt("offset %llu capacity %llu", (unsigned long long)h.data_offset,
	          (unsigned long long)h.data_capacity));

	// THE PIXELS. The source rows are padded; these must not be.
	std::string why;
	check(CORRECT, fmt("%s: the pixels are the frame's, packed row by row", label).c_str(),
	      planes_match_packed(f, buf.data() + FRAME_DUMP_DATA_OFFSET, h, why),
	      why.empty() ? "every plane matches byte for byte" : why);

	// The clock the Python reader ages the frame against.
	check(CORRECT, fmt("%s: timestamp_ns is CLOCK_REALTIME, taken during the push",
	                   label).c_str(),
	      h.timestamp_ns >= before && h.timestamp_ns <= after,
	      fmt("%llu, push spanned [%llu, %llu]", (unsigned long long)h.timestamp_ns,
	          (unsigned long long)before, (unsigned long long)after));

	// The two fields added in version 2.
	check(CORRECT, fmt("%s: min_interval_ms is the writer's own throttle", label).c_str(),
	      h.min_interval_ms == (uint32_t)FRAME_DUMP_MIN_INTERVAL_MS,
	      fmt("%u (want %d)", h.min_interval_ms, FRAME_DUMP_MIN_INTERVAL_MS));
	// push_us is a MEASUREMENT, so it is bounded by a clock this process took
	// itself: it cannot exceed the wall time the push actually spanned. That is
	// the honest assertion -- a fixed upper bound in microseconds would be a
	// timing threshold that fails under load and proves nothing about the code.
	const uint64_t span_us = (after - before) / 1000ULL;
	check(CORRECT, fmt("%s: push_us is bounded by the push's own wall time",
	                   label).c_str(),
	      (uint64_t)h.push_us <= span_us + 1,
	      fmt("push_us %u, wall span %llu us", h.push_us,
	          (unsigned long long)span_us));
	// AND IT IS A MEASUREMENT, NOT A CONSTANT. A push_us hard-wired to zero
	// would satisfy the bound above forever and read as a cost of nothing --
	// "a measurement that returns the same number everywhere and reads as a
	// verdict" is CLAUDE.md 10.1's own catalogue entry, and it cost this
	// project three prompt-zone runs. The lower bound is only meaningful if the
	// push took long enough to have a nonzero microsecond count at all, so when
	// it did not, this is INCONCLUSIVE rather than a pass.
	if(span_us < 2)
	{
		inconc(fmt("%s: push_us is a real measurement, not a constant",
		           label).c_str(),
		       fmt("the whole push spanned %llu us, too little to tell a real "
		           "measurement from a hard-wired zero",
		           (unsigned long long)span_us));
	}
	else
	{
		check(CORRECT, fmt("%s: push_us is a real measurement, not a constant",
		                   label).c_str(),
		      h.push_us > 0,
		      fmt("push_us %u over a %llu us push", h.push_us,
		          (unsigned long long)span_us));
	}

	av_frame_free(&f);
}

// The throttle. It is the only thing bounding what this costs the frame thread.
static void scenario_throttle(const char *path)
{
	setenv("CHIAKI_FRAME_DUMP", path, 1);
	FrameDumpStart();
	AVFrame *f = make_frame(64, 64, AV_PIX_FMT_NV12, 3);
	if(!f || !FrameDumpEnabled())
	{
		fail(CORRECT, "the throttle scenario can start", "no frame or no mapping");
		return;
	}

	FrameDumpPush(f);
	std::vector<unsigned char> buf = slurp(path);
	Hdr h;
	memcpy(&h, buf.data(), sizeof(h));
	check(CORRECT, "the first push publishes frame 1",
	      h.seq_after == 1, fmt("seq_after %llu", (unsigned long long)h.seq_after));

	// Immediately again: inside FRAME_DUMP_MIN_INTERVAL_MS, so it must be
	// dropped rather than published.
	FrameDumpPush(f);
	FrameDumpPush(f);
	buf = slurp(path);
	memcpy(&h, buf.data(), sizeof(h));
	check(CORRECT, "pushes inside the throttle window are dropped, not published",
	      h.seq_after == 1,
	      fmt("seq_after %llu after two more immediate pushes",
	          (unsigned long long)h.seq_after));

	// Past the window, the next push must go through -- otherwise "throttled"
	// and "broken" look the same, which is this project's signature failure.
	sleep_ms(FRAME_DUMP_MIN_INTERVAL_MS + 40);
	FrameDumpPush(f);
	buf = slurp(path);
	memcpy(&h, buf.data(), sizeof(h));
	check(CORRECT, "...and a push after the window publishes frame 2 (the control)",
	      h.seq_after == 2, fmt("seq_after %llu", (unsigned long long)h.seq_after));
	check(CORRECT, "the dropped counter counted the two it refused",
	      h.dropped >= 2, fmt("dropped %u", h.dropped));

	av_frame_free(&f);
}

// The refusals. Each one must leave the slot EMPTY rather than half written:
// framedump.h's own words are that half a frame which reads as a frame is the
// failure this project keeps getting caught by.
static void scenario_refusals(const char *path)
{
	setenv("CHIAKI_FRAME_DUMP", path, 1);
	FrameDumpStart();
	if(!FrameDumpEnabled())
	{
		fail(CORRECT, "the refusal scenario can start", "no mapping");
		return;
	}

	// A format that is neither NV12 nor YUV420P.
	AVFrame *rgb = make_frame(64, 64, AV_PIX_FMT_RGB24, 5);
	if(rgb)
	{
		FrameDumpPush(rgb);
		av_frame_free(&rgb);
	}
	std::vector<unsigned char> buf = slurp(path);
	Hdr h;
	memcpy(&h, buf.data(), sizeof(h));
	check(CORRECT, "a non-4:2:0 format is refused and nothing is published",
	      h.seq_after == 0 && h.seq_before == 0,
	      fmt("seq_before %llu seq_after %llu", (unsigned long long)h.seq_before,
	          (unsigned long long)h.seq_after));

	// Odd dimensions cannot be 4:2:0 and the arithmetic below would be wrong.
	AVFrame *odd = av_frame_alloc();
	if(odd)
	{
		odd->format = AV_PIX_FMT_NV12;
		odd->width = 65;
		odd->height = 33;
		if(av_frame_get_buffer(odd, 64) >= 0)
			FrameDumpPush(odd);
		av_frame_free(&odd);
	}
	buf = slurp(path);
	memcpy(&h, buf.data(), sizeof(h));
	check(CORRECT, "an odd-sized frame is refused",
	      h.seq_after == 0, fmt("seq_after %llu", (unsigned long long)h.seq_after));

	// Bigger than the slot. 4096x4096 NV12 is 25165824 bytes against a 4MiB
	// slot -- the P010 / 4K case framedump.cpp says it refuses rather than
	// truncates.
	AVFrame *big = make_flat_frame(4096, 4096, AV_PIX_FMT_NV12, 200);
	if(big)
	{
		FrameDumpPush(big);
		av_frame_free(&big);
		buf = slurp(path);
		memcpy(&h, buf.data(), sizeof(h));
		check(CORRECT, "a frame larger than the slot is refused, never truncated",
		      h.seq_after == 0, fmt("seq_after %llu", (unsigned long long)h.seq_after));
	}
	else
	{
		inconc("a frame larger than the slot is refused, never truncated",
		       "could not allocate a 4096x4096 frame to try it with");
	}

	// THE CONTROL. Every refusal above left seq at 0, which is also what a
	// FrameDumpPush that did nothing at all would leave -- so without this the
	// whole scenario would pass on a push that was simply broken.
	AVFrame *good = make_frame(64, 64, AV_PIX_FMT_NV12, 9);
	if(good)
	{
		sleep_ms(FRAME_DUMP_MIN_INTERVAL_MS + 40);
		FrameDumpPush(good);
		av_frame_free(&good);
	}
	buf = slurp(path);
	memcpy(&h, buf.data(), sizeof(h));
	check(CORRECT, "...and a good frame after them all still publishes (the control)",
	      h.seq_after == 1 && h.width == 64,
	      fmt("seq_after %llu %ux%u", (unsigned long long)h.seq_after,
	          h.width, h.height));
}

// THE SEQLOCK AND THE BUSY GUARD, under two writers and one spinning reader.
//
// Every frame is FLAT -- one value in every byte -- so a torn read is visible
// without knowing which frame was caught: two different fills in one payload
// can only be two frames spliced together. This is the check that the write
// ordering (seq_before, fence, pixels, fence, seq_after) and BusyGuard's mutual
// exclusion actually hold, rather than being read off the source.
static void scenario_concurrent(const char *path)
{
	setenv("CHIAKI_FRAME_DUMP", path, 1);
	FrameDumpStart();
	if(!FrameDumpEnabled())
	{
		fail(CORRECT, "the concurrency scenario can start", "no mapping");
		return;
	}

	const int W = 640, H = 480;
	const int SECONDS = 3;
	std::atomic<bool> stop{false};
	std::atomic<int> accepted{0}, torn{0}, retried{0};

	// The reader spins on the mapping through its own mmap, exactly as
	// frame_dump.py does: latch seq_after, copy, re-read seq_before, accept
	// only when they agree.
	std::thread reader([&]() {
		int fd = open(path, O_RDONLY);
		if(fd < 0)
			return;
		size_t bytes = (size_t)FRAME_DUMP_DATA_OFFSET + (size_t)FRAME_DUMP_CAPACITY;
		void *m = mmap(nullptr, bytes, PROT_READ, MAP_SHARED, fd, 0);
		close(fd);
		if(m == MAP_FAILED)
			return;
		const unsigned char *base = (const unsigned char *)m;
		std::vector<unsigned char> copy;
		while(!stop.load())
		{
			Hdr h;
			memcpy(&h, base, sizeof(h));
			if(memcmp(h.magic, "CHFD", 4) != 0 || h.seq_after == 0
					|| h.frame_bytes == 0 || h.frame_bytes > FRAME_DUMP_CAPACITY)
				continue;
			copy.resize((size_t)h.frame_bytes);
			memcpy(copy.data(), base + FRAME_DUMP_DATA_OFFSET, (size_t)h.frame_bytes);
			uint64_t again;
			memcpy(&again, base + 8, sizeof(again));   // seq_before
			if(again != h.seq_after)
			{
				retried.fetch_add(1);
				continue;
			}
			accepted.fetch_add(1);
			// One value everywhere, or the copy straddled two frames.
			const unsigned char v = copy[0];
			for(size_t i = 1; i < copy.size(); i++)
			{
				if(copy[i] != v)
				{
					torn.fetch_add(1);
					break;
				}
			}
		}
		munmap(m, bytes);
	});

	// Two writers, so BusyGuard is the only thing keeping them out of one
	// another's slot.
	auto writer = [&](unsigned char base_v) {
		unsigned char v = base_v;
		while(!stop.load())
		{
			AVFrame *f = make_flat_frame(W, H, AV_PIX_FMT_NV12, v);
			if(f)
			{
				FrameDumpPush(f);
				av_frame_free(&f);
			}
			v = (unsigned char)(v + 1);
			if(v == 0)
				v = 1;
			sleep_ms(5);
		}
	};
	std::thread w1(writer, 1), w2(writer, 128);

	sleep_ms(SECONDS * 1000);
	stop.store(true);
	w1.join();
	w2.join();
	reader.join();

	const int acc = accepted.load();
	// A run that never got a sample proves nothing. INCONCLUSIVE, never a pass.
	if(acc < 200)
	{
		inconc("two writers and a reader never publish a torn frame",
		       fmt("only %d accepted read(s) in %ds -- too few to conclude "
		           "anything; the machine was probably saturated", acc, SECONDS));
	}
	else
	{
		check(CORRECT, "two writers and a reader never publish a torn frame",
		      torn.load() == 0,
		      fmt("%d accepted read(s), %d torn, %d rejected by the seq re-read",
		          acc, torn.load(), retried.load()));
	}

	// THE ANTI-VACUITY CHECK. If the writers never actually published anything
	// new, the reader would read one unchanging frame forever and "no tearing"
	// would be true and meaningless.
	std::vector<unsigned char> buf = slurp(path);
	Hdr h;
	memcpy(&h, buf.data(), sizeof(h));
	const uint64_t expect_min = (uint64_t)(SECONDS * 1000 / FRAME_DUMP_MIN_INTERVAL_MS) / 2;
	check(CORRECT, "...and the writers really were publishing throughout",
	      h.seq_after >= expect_min && h.seq_after >= 5,
	      fmt("%llu frames published in %ds (throttle is %dms, so >= %llu expected)",
	          (unsigned long long)h.seq_after, SECONDS, FRAME_DUMP_MIN_INTERVAL_MS,
	          (unsigned long long)expect_min));
	// And the throttle held under two writers pushing as fast as they can: at
	// 5ms apart from each of two threads over 3s, an unthrottled writer would
	// publish ~1200 frames instead of ~60.
	check(CORRECT, "the throttle held with two threads pushing",
	      h.seq_after <= (uint64_t)(SECONDS * 1000 / FRAME_DUMP_MIN_INTERVAL_MS) + 10,
	      fmt("%llu frames, ceiling %d",
	          (unsigned long long)h.seq_after,
	          SECONDS * 1000 / FRAME_DUMP_MIN_INTERVAL_MS + 10));
}

static void summary()
{
	printf("SUMMARY pass=%d fail=%d inconc=%d total=%d\n",
	       n_pass, n_fail, n_inconc, n_pass + n_fail + n_inconc);
	fflush(stdout);
}

int main(int argc, char **argv)
{
	const std::string what = argc > 1 ? argv[1] : "";
	const char *path = argc > 2 ? argv[2] : nullptr;
	if(what.empty() || !path)
	{
		fprintf(stderr, "usage: %s <scenario> <dump path>\n", argv[0]);
		return 2;
	}

	if(what == "disabled")
		scenario_disabled(path);
	else if(what == "nv12")
		scenario_roundtrip(path, AV_PIX_FMT_NV12, "NV12");
	else if(what == "i420")
		scenario_roundtrip(path, AV_PIX_FMT_YUV420P, "I420");
	else if(what == "throttle")
		scenario_throttle(path);
	else if(what == "refusals")
		scenario_refusals(path);
	else if(what == "concurrent")
		scenario_concurrent(path);
	else
	{
		fprintf(stderr, "unknown scenario %s\n", what.c_str());
		return 2;
	}

	summary();
	return n_fail ? 1 : 0;
}
