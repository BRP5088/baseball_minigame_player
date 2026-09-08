// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
//
// Publish decoded video frames to a memory-mapped file.
//
// WHY
// ---
// Everything automating this game captured chiaki's WINDOW off the screen:
// find the window rect through the accessibility/window-list API, then grab
// those pixels. That works only while the window is composited on the CURRENT
// macOS Space. Switch Spaces and the window list stops reporting it —
// CGWindowListCreateImage returns nothing for a window on an inactive Space,
// because macOS does not composite it — so the capture raises, and any walk in
// progress dies. Six walks died that way inside thirty-five minutes on
// 2026-09-08, and the workaround was "do not touch the Mac while a batch runs".
//
// The frames already exist inside this process, decoded, before anything is
// drawn. Writing them to a shared mapping lets the reader take them from
// memory: no window, no Space, no compositor, and cheaper than a screen grab.
//
// OPT-IN. Nothing happens unless CHIAKI_FRAME_DUMP is set in the environment,
// naming a path to write. Unset, FrameDumpStart() returns immediately, g_map
// stays null and FrameDumpPush() is a single relaxed load and a return — the
// default behaviour is byte for byte what it was.
//
// THE FILE
// --------
// A fixed-size mapping: a 4096-byte header followed by ONE frame slot of
// FRAME_DUMP_CAPACITY bytes. The pixels are written PACKED (every plane's
// stride equals its width), so a reader can reshape the slot directly without
// unpicking the decoder's alignment.
//
// TEARING is handled by a two-counter seqlock, the scheme the reader must
// implement:
//
//     writer:  seq_before = n;  release fence;  write pixels + metadata;
//              release fence;  seq_after = n
//     reader:  a = seq_after;  copy everything;  b = seq_before;
//              the copy is consistent iff a == b (and a != 0)
//
// If the writer starts frame n+1 while the reader is copying, seq_before runs
// ahead of the seq_after the reader latched and the mismatch is caught. The
// reader retries; at FRAME_DUMP_MIN_INTERVAL_MS between writes and a copy of a
// few milliseconds, a retry is already rare and three of them is generous.
//
// COST. push_us is how long the writer's last push took, measured by the
// writer around its own work (any hardware transfer, the format checks and the
// packed copy) and stored inside the same seqlock transaction as the pixels.
// It is there so the frame thread's added cost is a number a reader can print
// rather than a claim in a comment: this push sits on the one thread between
// decode and present, and "it is cheap" was an assertion until it was measured.
//
// THROTTLE. min_interval_ms is the writer's own FRAME_DUMP_MIN_INTERVAL_MS,
// recorded rather than left for the reader to hard-code a second copy of. A
// constant mirrored by hand in two languages is this project's recorded
// RELEASE_MS bug: the mirror goes stale, and nothing fails until the day it
// matters.
//
// COLOUR. The header carries the decoder's own colorspace and color_range
// (ffmpeg's AVColorSpace / AVColorRange, verbatim). Nothing reads them yet:
// the reader converts with cv2, whose NV12/I420 paths assume BT.601 limited
// range, while a PS5 1080p stream is usually BT.709. On this game's
// near-monochrome art the difference is small but not zero, and it is measured
// against a simultaneous screen grab rather than assumed. Recording the fields
// now means a reader that wants the right matrix later does not have to guess.
//
// TIME. timestamp_ns is CLOCK_REALTIME — UNIX epoch nanoseconds, the same
// quantity Python's time.time_ns() returns, so a reader in another process can
// age the frame without either side having to agree about which monotonic
// clock this platform uses (macOS has three, and CPython has changed which one
// time.monotonic() rides more than once). mono_ns is CLOCK_MONOTONIC_RAW and
// is for diagnostics only: it is meaningful only against itself.
//
// A STALE DUMP IS NOT A FAILURE OF THIS FILE. When the session ends, or the
// stream stalls, frames simply stop arriving and the timestamp ages. That is
// exactly the signal the reader wants — "the stream is not producing frames" —
// so nothing here tears the mapping down when a session quits.
//
// THERE IS DELIBERATELY NO TEARDOWN AT ALL. The mapping is process-lifetime,
// like the injector's FIFO listener next door, and the OS reclaims it at exit.
// This file used to export a FrameDumpStop() whose comment said "for process
// shutdown" — and nothing called it, there or anywhere: a documented wiring
// that did not exist. Un-writing the claim was the honest fix, because the
// alternative was worse than dead code. FrameDumpPush() runs on the frame
// thread; a Stop that unmapped while that thread was mid-push would be a
// use-after-unmap (SIGBUS), so wiring one would mean adding real
// synchronisation to a shutdown path whose entire benefit is tidiness on a
// process that is about to exit. And a Stop hooked to SESSION end instead
// would be worse still: a reconnect would silently never resume dumping, with
// every symbol still linked and the log still clean.

#ifndef CHIAKI_FRAMEDUMP_H
#define CHIAKI_FRAMEDUMP_H

#include <stddef.h>
#include <stdint.h>

struct AVFrame;

// "CHFD", little-endian, as it appears in the first four bytes.
#define FRAME_DUMP_MAGIC "CHFD"
// 2 (2026-09-08): the header grew push_us and min_interval_ms and went from
// 128 to 136 bytes. A reader written for 1 would parse everything after
// `dropped` correctly and then read four bytes of push_us as `reserved`,
// which is harmless -- and that is exactly why the version has to move: the
// mistake this catches is the one that produces plausible numbers.
#define FRAME_DUMP_VERSION 2u

// Pixel format codes written into the header. Deliberately OUR OWN small
// numbers rather than AVPixelFormat values: those are an ffmpeg internal
// enumeration that has been renumbered between major versions, and a reader in
// another language would be pinning a number nobody promised to keep.
#define FRAME_DUMP_FMT_NV12 1u    // Y plane, then interleaved CbCr, both stride=width
#define FRAME_DUMP_FMT_I420 2u    // Y, then Cb, then Cr; chroma stride=width/2

// The header is padded out to this so the pixel data starts page-aligned.
#define FRAME_DUMP_DATA_OFFSET 4096u

// One slot, sized for 1920x1080 4:2:0 (3110400 bytes) with margin. A frame
// whose packed size exceeds this is REFUSED with one log line rather than
// truncated: half a frame that reads as a frame is the failure this project
// keeps getting caught by.
#define FRAME_DUMP_CAPACITY (4u * 1024u * 1024u)

// At most one dump per this many milliseconds (~20 Hz). The readers here poll
// at a few Hz at most, so a higher rate buys nothing and every dump costs a
// GPU->CPU readback on the thread that feeds the renderer.
#define FRAME_DUMP_MIN_INTERVAL_MS 50

// Open (creating if needed) the mapping named by CHIAKI_FRAME_DUMP. Safe to
// call repeatedly; only the first call does anything. No-op when the variable
// is unset or empty.
void FrameDumpStart();

// Publish `frame` if the throttle allows and nothing else is mid-dump.
//
// The frame is NOT modified and NOT taken over. A SOFTWARE frame is copied
// straight out of its planes; a HARDWARE frame is transferred into a private
// AVFrame owned by this file. Either way the caller's frame goes on to the
// renderer untouched. Cheap and non-blocking when disabled, throttled or busy.
//
// CALL IT AFTER prepareFrameForPresentation, NOT BEFORE. That is not a style
// preference, it is the whole cost of this file on the platform it runs on.
// prepareFrameForPresentation already transfers every VideoToolbox frame to
// software (frame_can_use_direct_render answers true only for Vulkan and Linux
// VAAPI) and replaces the caller's pointer with the result. Pushing afterwards
// means the dump copies planes that are ALREADY in main memory and adds no
// readback at all; pushing before meant two independent GPU->CPU readbacks of
// the same pixels, back to back, on the one thread between decode and present.
// On a direct-render platform the frame is still hardware at that point and
// the transfer below happens, which is the only way to get pixels there.
void FrameDumpPush(AVFrame *frame);

// True when a mapping is open, i.e. CHIAKI_FRAME_DUMP was set and usable.
bool FrameDumpEnabled();

#endif // CHIAKI_FRAMEDUMP_H
