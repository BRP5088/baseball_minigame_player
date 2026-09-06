// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL

#include "injectinput.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <chrono>
#include <mutex>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

// Each field carries its own "has been set" flag so a caller can drive only
// the sticks and leave the buttons to the real controller. A single global
// "injecting" flag would force all-or-nothing.
// How long `clear` keeps transmitting the zeroed state before going inactive.
// The pump runs every 8ms, so this is ~12 sends — comfortably more than the
// one that chiaki's feedback DEDUPLICATION might collapse, and far below
// INJECT_TIMEOUT_MS so it cannot be mistaken for a held input.
static const long long RELEASE_MS = 100;

struct Injected
{
	std::atomic<bool> active{false};
	std::atomic<int> left_x{0}, left_y{0}, right_x{0}, right_y{0};
	std::atomic<int> l2{-1}, r2{-1};
	std::atomic<int> buttons{-1};
	std::atomic<bool> has_left{false}, has_right{false};
	std::atomic<long long> last_ms{0};
	std::mutex stick_mutex;

	// Deadlines for a TIMED HOLD, in the same clock as last_ms. 0 = no
	// deadline, hold until told otherwise (the original behaviour).
	//
	// WHY THIS EXISTS
	// ---------------
	// A caller that wants "right stick right for 400ms" used to express it as
	// write / sleep 400ms / write zero. The duration the PS5 actually saw was
	// then the gap between two FIFO round trips, and every source of latency
	// in between landed directly on it: the driving process's sleep
	// granularity and scheduling, opening and closing the FIFO twice, this
	// reader thread waking, and the pump tick's phase at both edges.
	// Measured on a camera turn, two identical 1.0s full-stick commands
	// turned 208.6 and 201.0 degrees — 7.7 degrees apart, with no feedback
	// loop anywhere in the path to absorb it.
	//
	// With a deadline the caller sends ONE line and this side releases the
	// field itself, timed by the same steady_clock the pump runs on. The
	// release stops depending on anything outside this process, and the
	// residual error is bounded by the pump interval instead of by the
	// round trip.
	std::atomic<long long> left_until{0}, right_until{0}, buttons_until{0};
	// CLEAR MUST TRANSMIT A RELEASE BEFORE GOING INACTIVE.
	//
	// chiaki's pump is `if(InjectInputActive()) SendFeedbackState();`, so
	// setting active=false is not "release the stick", it is "STOP SENDING" —
	// the console keeps whatever state it last received. Measured against this
	// very file: 0.4s after `clear`, the PS5 still believed left_y = -9830.
	//
	// Every per-step release on the live path writes explicit zeros
	// (`left_x 0`, `left_y 0`) and is fine. `clear` is used at the END of a
	// run and in every experiment harness's `finally`, so the stick could stay
	// deflected BETWEEN trials — which attacks the trial independence every
	// A/B here assumes.
	//
	// So `clear` now zeroes the axes and stays ACTIVE until this deadline,
	// giving the 8ms pump time to transmit the zeroed state.
	std::atomic<long long> release_until{0};
};

// If nothing new is injected for this long, injection is dropped.
//
// This exists because the pump timer transmits state CONTINUOUSLY once
// something is injected, rather than only while real input events happen. That
// is the whole point of the timer, but it means a driving script that crashes
// or is killed mid-run leaves its last state — a stick at full deflection, a
// held button — being sent forever, with nobody left to send the "clear". The
// character would walk into a wall for hours.
//
// Five seconds is comfortably longer than any gap a real run produces (the
// replays send at 30-50Hz, and the slowest stepper pauses ~0.5s to capture a
// frame) while bounding a runaway to something harmless.
const long long INJECT_TIMEOUT_MS = 5000;

long long NowMs()
{
	using namespace std::chrono;
	return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

Injected g_inject;
std::atomic<bool> g_started{false};

void Apply(const std::string &line)
{
	char key[32];
	long value = 0;
	long hold_ms = 0;
	// An optional THIRD field is the hold duration in milliseconds. Two
	// fields keeps the original meaning exactly, so every existing caller is
	// unaffected.
	int fields = sscanf(line.c_str(), "%31s %ld %ld", key, &value, &hold_ms);
	if(fields < 1)
		return;
	if(fields < 3 || hold_ms <= 0)
		hold_ms = 0;
	const long long deadline = hold_ms > 0 ? NowMs() + hold_ms : 0;

	if(!strcmp(key, "clear"))
	{
		{
			std::lock_guard<std::mutex> l(g_inject.stick_mutex);
			g_inject.left_x = 0;
			g_inject.left_y = 0;
			g_inject.right_x = 0;
			g_inject.right_y = 0;
		}
		// Keep has_left/has_right TRUE so Apply() actually writes the zeros
		// into the state the pump sends. Setting them false would make the
		// release invisible, which is the bug being fixed.
		g_inject.has_left = true;
		g_inject.has_right = true;
		g_inject.l2 = 0;
		g_inject.r2 = 0;
		g_inject.buttons = 0;
		g_inject.left_until = 0;
		g_inject.right_until = 0;
		g_inject.buttons_until = 0;
		g_inject.release_until = NowMs() + RELEASE_MS;
		g_inject.active = true;      // stay active so the zeros TRANSMIT
		return;
	}

	// Clamp rather than reject: a caller computing a value from a float will
	// land on 32768 sooner or later, and silently dropping that input is far
	// harder to debug than accepting the nearest legal value.
	auto clamp16 = [](long v) -> int {
		if(v > 32767) return 32767;
		if(v < -32768) return -32768;
		return (int)v;
	};

	// A timed write sets the deadline for its whole STICK, not just the axis:
	// "right_x 32767 400" is a request to push the right stick for 400ms, and
	// releasing x while leaving y held would be a stick position the caller
	// never asked for.
	//
	// AN UNTIMED WRITE LEAVES AN EXISTING DEADLINE ALONE. It used to clear it,
	// which read as the tidier rule until it was measured: a caller naturally
	// sets both axes in one batch —
	//
	//     right_x 32767 400
	//     right_y 0
	//
	// — and under the old rule the second line silently cancelled the hold set
	// by the first. The stick then stayed down until something else released
	// it, and a 1.0s turn came out as 1.4s. The failure was silent and the
	// measurement looked like drift.
	//
	// So a deadline is only ever set by a write that CARRIES one, and only
	// `clear` (or the hold expiring) takes it away.
	if(!strcmp(key, "left_x"))       { std::lock_guard<std::mutex> l(g_inject.stick_mutex); g_inject.left_x = clamp16(value);  g_inject.has_left = true;  if(hold_ms > 0) g_inject.left_until = deadline; }
	else if(!strcmp(key, "left_y"))  { std::lock_guard<std::mutex> l(g_inject.stick_mutex); g_inject.left_y = clamp16(value);  g_inject.has_left = true;  if(hold_ms > 0) g_inject.left_until = deadline; }
	else if(!strcmp(key, "right_x")) { std::lock_guard<std::mutex> l(g_inject.stick_mutex); g_inject.right_x = clamp16(value); g_inject.has_right = true; if(hold_ms > 0) g_inject.right_until = deadline; }
	else if(!strcmp(key, "right_y")) { std::lock_guard<std::mutex> l(g_inject.stick_mutex); g_inject.right_y = clamp16(value); g_inject.has_right = true; if(hold_ms > 0) g_inject.right_until = deadline; }
	else if(!strcmp(key, "l2"))      { g_inject.l2 = value < 0 ? 0 : (value > 255 ? 255 : (int)value); }
	else if(!strcmp(key, "r2"))      { g_inject.r2 = value < 0 ? 0 : (value > 255 ? 255 : (int)value); }
	else if(!strcmp(key, "buttons")) { g_inject.buttons = (int)value; if(hold_ms > 0) g_inject.buttons_until = deadline; }
	else return;

	g_inject.last_ms = NowMs();
	// DISARM ANY PENDING `clear` RELEASE. Without this line a write that lands
	// inside the 100ms release window sets active = true and leaves the
	// deadline armed, so InjectInputActive() then runs its release path on the
	// FRESH input: active = false, has_left = false. The pump stops sending and
	// the console keeps the last state it received — the deflection — while the
	// timed hold's own expiry happens inside this process and is never
	// transmitted. Measured (`clear` then `left_y -5000 300`, scored at
	// +800ms): 30ms gap, 12/12 still deflected; 90ms gap, 9/12 deflected and
	// 3/12 the push dropped entirely; 400ms gap, 12/12 correct.
	//
	// The window is short and every clear() on the live path is followed by a
	// capture or a log, so this was latent there — but `overnight/walk_curve.py`
	// loops `send(["clear"])` straight back into a push about 75ms later, which
	// is inside it.
	g_inject.release_until = 0;
	g_inject.active = true;
}

void Listen(std::string path)
{
	// A FIFO, so a writer can come and go without the reader noticing — the
	// automation driving this will open and close it many times over a run.
	unlink(path.c_str());
	if(mkfifo(path.c_str(), 0600) != 0)
	{
		fprintf(stderr, "[inject] cannot create fifo at %s\n", path.c_str());
		return;
	}
	fprintf(stderr, "[inject] listening on %s\n", path.c_str());

	while(true)
	{
		FILE *f = fopen(path.c_str(), "r");
		if(!f)
		{
			sleep(1);
			continue;
		}
		char buf[256];
		while(fgets(buf, sizeof(buf), f))
			Apply(buf);
		fclose(f);
	}
}

} // namespace

void InjectInputStart()
{
	bool expected = false;
	if(!g_started.compare_exchange_strong(expected, true))
		return;
	const char *path = getenv("CHIAKI_INJECT_INPUT");
	if(!path || !*path)
		return;
	std::thread(Listen, std::string(path)).detach();
}

void InjectInputApply(ChiakiControllerState *state)
{
	if(!g_inject.active.load(std::memory_order_relaxed))
		return;
	if(NowMs() - g_inject.last_ms.load() > INJECT_TIMEOUT_MS)
	{
		// The writer went away without clearing. Drop everything rather than
		// keep transmitting a stale stick forever.
		fprintf(stderr, "[inject] no input for %lldms — releasing\n", INJECT_TIMEOUT_MS);
		g_inject.active = false;
		g_inject.has_left = false;
		g_inject.has_right = false;
		g_inject.l2 = -1;
		g_inject.r2 = -1;
		g_inject.buttons = -1;
		g_inject.left_until = 0;
		g_inject.right_until = 0;
		g_inject.buttons_until = 0;
		return;
	}
	// Both components of a stick are read under one lock. They are stored as
	// separate atomics, so reading them independently can catch the pair
	// half-updated — left_x from the new sample and left_y from the old one —
	// producing a stick vector that was never actually sent. The window is
	// microseconds against an 8ms tick, so it is rare rather than harmless:
	// a single torn sample points the character somewhere it was never told
	// to go, and this replay has no position feedback to notice.
	// Expire timed holds FIRST, so the state written below is already the
	// released one. An expired stick is centred rather than handed back to
	// the real controller: the caller asked for a bounded push, and the
	// defined end of that push is neutral. Handing it back would also make
	// the result depend on whether a pad happens to be plugged in.
	const long long now = NowMs();
	{
		std::lock_guard<std::mutex> lock(g_inject.stick_mutex);
		long long until = g_inject.left_until.load();
		if(until && now >= until)
		{
			g_inject.left_x = 0;
			g_inject.left_y = 0;
			g_inject.left_until = 0;
		}
		until = g_inject.right_until.load();
		if(until && now >= until)
		{
			g_inject.right_x = 0;
			g_inject.right_y = 0;
			g_inject.right_until = 0;
		}
	}
	long long btn_until = g_inject.buttons_until.load();
	if(btn_until && now >= btn_until)
	{
		g_inject.buttons = 0;
		g_inject.buttons_until = 0;
	}

	{
		std::lock_guard<std::mutex> lock(g_inject.stick_mutex);
		if(g_inject.has_left)
		{
			state->left_x = (int16_t)g_inject.left_x.load();
			state->left_y = (int16_t)g_inject.left_y.load();
		}
		if(g_inject.has_right)
		{
			state->right_x = (int16_t)g_inject.right_x.load();
			state->right_y = (int16_t)g_inject.right_y.load();
		}
	}
	int l2 = g_inject.l2.load();
	if(l2 >= 0)
		state->l2_state = (uint8_t)l2;
	int r2 = g_inject.r2.load();
	if(r2 >= 0)
		state->r2_state = (uint8_t)r2;
	int buttons = g_inject.buttons.load();
	if(buttons >= 0)
		state->buttons = (uint32_t)buttons;
}

bool InjectInputActive()
{
	// A scheduled release keeps the pump running just long enough for the
	// zeroed state to reach the console, then genuinely goes inactive.
	long long until = g_inject.release_until.load(std::memory_order_relaxed);
	if(until != 0 && NowMs() >= until)
	{
		g_inject.release_until = 0;
		g_inject.active = false;
		g_inject.has_left = false;
		g_inject.has_right = false;
		g_inject.l2 = -1;
		g_inject.r2 = -1;
		g_inject.buttons = -1;
	}
	return g_inject.active.load(std::memory_order_relaxed);
}
