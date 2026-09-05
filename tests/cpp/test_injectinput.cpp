// Offline check for the injector's TIMED HOLD.
//
// Drives the real injectinput.cpp through its public API and a real FIFO, so
// the parsing, the deadline and the release are all exercised. Touches no
// console: nothing here talks to chiaki or the network.
//
//   clang++ -std=c++17 -Ichiaki-patch -Ichiaki-ng-src/lib/include \
//       tests/cpp/test_injectinput.cpp chiaki-patch/injectinput.cpp -o /tmp/t && /tmp/t

#include "injectinput.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>
#include <unistd.h>

static int fails = 0;

static void check(const char *name, bool ok)
{
	printf("%s %s\n", ok ? "PASS" : "FAIL", name);
	if(!ok) fails++;
}

static void write_fifo(const std::string &path, const std::string &line)
{
	FILE *f = fopen(path.c_str(), "w");
	if(!f) { printf("FAIL cannot open fifo\n"); fails++; return; }
	fprintf(f, "%s\n", line.c_str());
	fclose(f);
}

static void sleep_ms(int ms)
{
	std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

// The pump calls InjectInputApply every 8ms; emulate that so deadlines are
// evaluated the way they will be in the real binary.
static ChiakiControllerState pump_for(int ms)
{
	ChiakiControllerState st{};
	auto end = std::chrono::steady_clock::now() + std::chrono::milliseconds(ms);
	do {
		st = ChiakiControllerState{};
		st.buttons = 0;
		InjectInputApply(&st);
		sleep_ms(8);
	} while(std::chrono::steady_clock::now() < end);
	return st;
}

int main()
{
	std::string path = "/tmp/chiaki_inject_test_" + std::to_string(getpid());
	setenv("CHIAKI_INJECT_INPUT", path.c_str(), 1);
	InjectInputStart();
	sleep_ms(200);                       // let the listener create the fifo

	// --- an UNTIMED write still holds indefinitely (the original behaviour)
	write_fifo(path, "right_x 32767");
	sleep_ms(50);
	ChiakiControllerState st{};
	st.buttons = 0;
	InjectInputApply(&st);
	check("untimed write is applied", st.right_x == 32767);

	st = pump_for(300);
	check("untimed write is STILL held after 300ms", st.right_x == 32767);

	write_fifo(path, "clear");
	sleep_ms(50);

	// --- a TIMED write releases itself
	write_fifo(path, "right_x 32767 200");
	sleep_ms(50);
	st = ChiakiControllerState{};
	st.buttons = 0;
	InjectInputApply(&st);
	check("timed write is applied immediately", st.right_x == 32767);

	st = pump_for(80);
	check("timed write is still held before its deadline", st.right_x == 32767);

	st = pump_for(250);
	check("timed write RELEASES itself after the deadline", st.right_x == 0);

	// --- the deadline covers the whole stick, not one axis
	write_fifo(path, "clear");
	sleep_ms(50);
	write_fifo(path, "right_y -20000 150");
	sleep_ms(50);
	st = ChiakiControllerState{};
	st.buttons = 0;
	InjectInputApply(&st);
	check("y axis is applied", st.right_y == -20000);
	st = pump_for(250);
	check("y axis releases too", st.right_y == 0 && st.right_x == 0);

	// --- a timed hold on one stick must not touch the other
	write_fifo(path, "clear");
	sleep_ms(50);
	write_fifo(path, "left_x 12345");          // untimed
	write_fifo(path, "right_x 32767 150");     // timed
	sleep_ms(50);
	st = pump_for(250);
	check("the timed stick released", st.right_x == 0);
	check("the untimed stick was NOT released", st.left_x == 12345);

	// --- buttons take a duration too
	write_fifo(path, "clear");
	sleep_ms(50);
	write_fifo(path, "buttons 8 150");
	sleep_ms(50);
	st = ChiakiControllerState{};
	st.buttons = 0;
	InjectInputApply(&st);
	check("button mask is applied", st.buttons == 8);
	st = pump_for(250);
	check("button mask releases itself", st.buttons == 0);

	// --- an untimed SIBLING AXIS must not cancel the hold.
	// This is the regression that produced a 1.4s turn from a 1.0s command:
	// the caller sets both axes in one batch and the second line killed the
	// deadline set by the first.
	write_fifo(path, "clear");
	sleep_ms(50);
	write_fifo(path, "right_x 32767 150");
	write_fifo(path, "right_y 0");             // no duration - must NOT cancel
	sleep_ms(50);
	st = pump_for(80);
	check("sibling axis does not cancel the hold (still held)", st.right_x == 32767);
	st = pump_for(250);
	check("and the hold STILL expires on time", st.right_x == 0);


	// --- `clear` MUST TRANSMIT A RELEASE, not merely stop sending -------
	//
	// chiaki's pump is `if(InjectInputActive()) SendFeedbackState();`, so
	// setting active=false is "STOP SENDING", and the console keeps the last
	// state it received. Measured against this file before the fix: 0.4s after
	// `clear`, the PS5 still believed left_y = -9830 — the stick stayed
	// deflected. Every per-step release on the live path writes explicit zeros
	// and was fine; `clear` is used at the end of a run and in every A/B
	// harness's `finally`, so the stick could stay deflected BETWEEN TRIALS.
	write_fifo(path, "left_y -9830");
	sleep_ms(60);
	{
		ChiakiControllerState st{};
		InjectInputApply(&st);
		check("a deflected stick is applied", st.left_y == -9830);
	}

	write_fifo(path, "clear");
	sleep_ms(60);
	check("clear keeps the pump ACTIVE so the release can transmit",
	      InjectInputActive());
	{
		// The console's last-known state, which the pump would otherwise keep
		// re-sending unchanged.
		ChiakiControllerState st{};
		st.left_y = -9830;
		InjectInputApply(&st);
		check("and clear writes ZERO into the state the pump sends",
		      st.left_y == 0);
	}

	sleep_ms(200);
	check("after the release window the pump genuinely goes inactive",
	      !InjectInputActive());

	write_fifo(path, "clear");
	unlink(path.c_str());
	printf(fails ? "\n%d FAIL\n" : "\nall green\n", fails);
	return fails ? 1 : 0;
}
