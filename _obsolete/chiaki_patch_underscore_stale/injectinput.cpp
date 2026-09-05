// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL

#include "injectinput.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

// Each field carries its own "has been set" flag so a caller can drive only
// the sticks and leave the buttons to the real controller. A single global
// "injecting" flag would force all-or-nothing.
struct Injected
{
	std::atomic<bool> active{false};
	std::atomic<int> left_x{0}, left_y{0}, right_x{0}, right_y{0};
	std::atomic<int> l2{-1}, r2{-1};
	std::atomic<int> buttons{-1};
	std::atomic<bool> has_left{false}, has_right{false};
};

Injected g_inject;
std::atomic<bool> g_started{false};

void Apply(const std::string &line)
{
	char key[32];
	long value = 0;
	if(sscanf(line.c_str(), "%31s %ld", key, &value) < 1)
		return;

	if(!strcmp(key, "clear"))
	{
		// Zero the stored values as well as clearing the flag. Leaving stale
		// stick values behind means that if `active` is ever set again — by a
		// later partial write, or a crashed driver reconnecting — the camera
		// jumps to wherever the last replay left it. The person holding the
		// real controller feels that as the camera behaving oddly, with no
		// visible cause.
		g_inject.left_x = 0;
		g_inject.left_y = 0;
		g_inject.right_x = 0;
		g_inject.right_y = 0;
		g_inject.active = false;
		g_inject.has_left = false;
		g_inject.has_right = false;
		g_inject.l2 = -1;
		g_inject.r2 = -1;
		g_inject.buttons = -1;
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

	if(!strcmp(key, "left_x"))       { g_inject.left_x = clamp16(value);  g_inject.has_left = true; }
	else if(!strcmp(key, "left_y"))  { g_inject.left_y = clamp16(value);  g_inject.has_left = true; }
	else if(!strcmp(key, "right_x")) { g_inject.right_x = clamp16(value); g_inject.has_right = true; }
	else if(!strcmp(key, "right_y")) { g_inject.right_y = clamp16(value); g_inject.has_right = true; }
	else if(!strcmp(key, "l2"))      { g_inject.l2 = value < 0 ? 0 : (value > 255 ? 255 : (int)value); }
	else if(!strcmp(key, "r2"))      { g_inject.r2 = value < 0 ? 0 : (value > 255 ? 255 : (int)value); }
	else if(!strcmp(key, "buttons")) { g_inject.buttons = (int)value; }
	else return;

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
