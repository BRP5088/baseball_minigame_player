// Offline check for the injector's TIMED HOLD.
//
// Drives the real injectinput.cpp through its public API and a real FIFO, so
// the parsing, the deadline and the release are all exercised. Touches no
// console: nothing here talks to chiaki or the network.
//
// DO NOT RUN THIS BY HAND AND CALL IT WIRED IN. tests/cpp/test_injectinput_cpp.py
// compiles it, drives it, and first checks that chiaki-patch/ still matches the
// sources the application actually builds. That file is picked up by
// run_tests.sh like every other test, which is what OPEN-11 was about: for
// months these checks ran only if somebody remembered a clang++ line sitting in
// this comment, which is the same as not running at all.
//
// ---------------------------------------------------------------------------
// EVERY TIMING ASSERTION HERE IS CONDITIONAL ON A MEASURED CLOCK
//
// The first version asserted "still held" after a fixed sleep, with margins of
// 20-70ms against deadlines of 150-200ms. That is a threshold sitting inside
// one population, the shape CLAUDE.md 10.4 says has already cost this project
// four bugs: under load an observation simply arrives later, so a correctness
// regression and a busy machine produced the same FAIL, and the honest reading
// of either was a shrug.
//
// The fix is to bound the injector's deadline from BOTH sides using times this
// process can actually measure:
//
//   t_write + hold   is a LOWER bound on the deadline. The injector stamps it
//                    when it PARSES the line, which cannot be before we started
//                    writing it. So any observation that FINISHES before this
//                    is one the value must still be held at.
//   t_seen  + hold   is an UPPER bound. The parse cannot be after the first
//                    tick that saw the value applied. So any observation that
//                    STARTS after this must find the value released.
//
// Load moves observations later, so it can only reduce the number of samples a
// "still held" check gets — reported as INCONCLUSIVE, never as a pass — and can
// only delay a "released by now" check, which stays true however late it runs.
//
// Results are tagged `correctness` or `timing` and counted separately. Every
// timing check below has a load-proof correctness twin that fails on the same
// bug, so a loaded machine can never turn a regression into a shrug: the twin
// still fails.
//
// The other half of "measure, do not sleep": nothing here waits a guessed
// interval for a FIFO line to land. Lines are parsed in order, so a line is
// known to have been parsed once a MARKER written after it shows up. See
// barrier().

#include "injectinput.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>

// chiaki pumps InjectInputApply from an 8ms QTimer (streamsession.cpp), so
// ticking at the same rate evaluates the deadlines the way the real binary
// will.
static const int PUMP_MS = 8;

// The hold used by the timed scenarios. This is NOT a threshold and nothing is
// calibrated against it — every assertion below is bounded by measured times.
// It only buys the "still held" checks enough ticks to take a sample, and
// 400ms is ~50 pump ticks against a worst sleep overshoot of 2ms measured on
// this machine at load average 104.
static const long long HOLD_MS = 400;

// injectinput.cpp drops ALL injected state after INJECT_TIMEOUT_MS = 5000ms
// with no writes (its runaway guard). Past that, every "is it released yet?"
// assertion here would pass for the wrong reason — a vacuous statistic, which
// CLAUDE.md 10.12 has already been caught by once. This tripwire is half of it:
// an observation landing this long after its own write measured the runaway
// guard, not the deadline under test, and says so instead of scoring.
static const long long STALE_TRIPWIRE_MS = 2500;

// injectinput.cpp's RELEASE_MS: how long `clear` keeps transmitting the zeroed
// state before going inactive. It lives in an anonymous namespace so it cannot
// be included from here. Duplicating it is safe ONLY because it is used below
// to choose between PASS and INCONCLUSIVE, never between PASS and FAIL: if the
// real constant grows this becomes conservative, and if it shrinks the check
// goes inconclusive rather than failing wrongly.
static const long long RELEASE_MS_MIRROR = 100;

static const char *CORRECT = "correctness";
static const char *TIMING = "timing";

static int n_pass = 0, n_fail = 0, n_inconc = 0;

// One machine-readable line per check, split on '|' by the Python driver. It is
// also readable as-is, because on a failure the suite prints this output and
// that is the only thing anyone ever sees.
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

// NOT a pass. A timing sample that could not be taken proves nothing, and the
// driver treats a run containing one as a failure with a message that says so —
// loudly, because a skip that reads as a pass is the shape this project keeps
// getting caught by.
static void inconc(const char *name, const std::string &d)
{ n_inconc++; result("INCONC", "timing", name, d); }

static long long now_ms()
{
	using namespace std::chrono;
	return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

static void sleep_ms(int ms)
{
	std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

static long long g_last_write = 0;

// ONE writer, held open for the whole run — which is also what production does.
//
// The reader in injectinput.cpp is `fopen / fgets until EOF / fclose / repeat`,
// so every writer that CLOSES makes it tear down and re-open, and a line written
// into that gap is either lost outright or kills the writer with SIGPIPE.
// Measured here: with per-line open/close and no sleeps between writes, 3 runs
// in 20 died that way — one SIGPIPE, two with a marker line silently swallowed.
// The old version of this file hid the race behind a 50ms sleep after every
// write, which is the same sleep the timing rework removed.
//
// analog_replay.open_stream() already holds the pipe open for a whole replay for
// exactly this reason ("at 50Hz it raised BrokenPipeError outright"), so a
// persistent writer is the production shape, not a test convenience.
static FILE *g_fifo = nullptr;

// Returns the moment the write STARTED — a guaranteed lower bound on the moment
// the injector parsed the line, because it cannot parse what has not been sent.
static long long write_fifo(const std::string &line)
{
	long long t0 = now_ms();
	fprintf(g_fifo, "%s\n", line.c_str());
	fflush(g_fifo);
	g_last_write = now_ms();
	return t0;
}

struct Sample
{
	long long before, after;
	ChiakiControllerState st;
};

// One pump tick. `seed` is what the real controller state would hold before the
// overlay runs, so seeding it with a stale value is how "did the injector
// actually WRITE this field?" is distinguished from "the field happened to
// already be zero".
static Sample tick(ChiakiControllerState seed)
{
	Sample s;
	s.st = seed;
	s.before = now_ms();
	InjectInputApply(&s.st);
	s.after = now_ms();
	return s;
}

typedef long long (*Get)(const ChiakiControllerState &);
static long long get_left_x(const ChiakiControllerState &s) { return s.left_x; }
static long long get_left_y(const ChiakiControllerState &s) { return s.left_y; }
static long long get_right_x(const ChiakiControllerState &s) { return s.right_x; }
static long long get_right_y(const ChiakiControllerState &s) { return s.right_y; }
static long long get_buttons(const ChiakiControllerState &s) { return (long long)s.buttons; }
static long long get_l2(const ChiakiControllerState &s) { return (long long)s.l2_state; }

struct Await
{
	bool ok;
	Sample s;
};

// Poll until the field reads `want`, or until `give_up`. Polls at 1ms rather
// than at the pump rate because the question is "has it landed yet", and a
// coarse poll would blur the answer with the pump interval.
static Await await_value(Get get, long long want, long long give_up,
                         ChiakiControllerState seed = ChiakiControllerState{})
{
	Await a;
	while(true)
	{
		a.s = tick(seed);
		if(get(a.s.st) == want) { a.ok = true; return a; }
		if(a.s.after >= give_up) { a.ok = false; return a; }
		sleep_ms(1);
	}
}

// Prove a FIFO line has been parsed instead of sleeping a guessed interval to
// "let it land" — the guessed sleep is exactly what made the old version
// load-sensitive. The reader parses lines in order, so a marker written after
// the line of interest cannot appear before that line has been parsed.
//
// l2 is the marker because nothing else in this file asserts on it, and because
// a fresh l2 value also refreshes the injector's runaway timer.
static int g_marker = 0;
static bool barrier()
{
	g_marker = (g_marker % 200) + 1;              // 1..200, never 0, always fresh
	write_fifo("l2 " + std::to_string(g_marker));
	Await a = await_value(get_l2, g_marker, now_ms() + 3000);
	if(!a.ok)
		fail(CORRECT, "the fifo reader keeps up with writes",
		     "marker l2 " + std::to_string(g_marker) + " never arrived in 3s");
	return a.ok;
}

// Reset between scenarios. `clear` also arms injectinput's release window, so
// nothing may call InjectInputActive() until the clear scenarios at the end:
// that call is what expires the window, and expiring it would also drop the
// state a following write had set.
static void reset()
{
	write_fifo("clear");
	barrier();
}

// Assert the field keeps `want` on every tick that PROVABLY finished before
// `bound`, a lower bound on the injector's deadline. Ticks after the bound are
// not samples and are not asserted on — which is what stops load manufacturing
// a failure. Zero samples is INCONCLUSIVE, never a pass.
static void hold_check(const char *kind, const char *name, Get get, long long want,
                       long long bound)
{
	int samples = 0;
	bool broke = false;
	long long broke_at = 0, broke_val = 0;
	while(true)
	{
		Sample s = tick(ChiakiControllerState{});
		if(s.after < bound)
		{
			samples++;
			if(!broke && get(s.st) != want)
			{
				broke = true;
				broke_at = s.after;
				broke_val = get(s.st);
			}
		}
		if(now_ms() >= bound)
			break;
		sleep_ms(PUMP_MS);
	}

	if(broke)
	{
		long long late = broke_at - g_last_write;
		if(late >= STALE_TRIPWIRE_MS)
			inconc(name, "the value went away " + std::to_string(late) +
			             "ms after the last write, which is injectinput's runaway "
			             "guard rather than the deadline under test — this machine "
			             "stalled mid-check and nothing was measured");
		else
			fail(kind, name, "released at least " + std::to_string(bound - broke_at) +
			                 "ms EARLY (read " + std::to_string(broke_val) +
			                 ", wanted " + std::to_string(want) + ")");
	}
	else if(samples == 0)
	{
		inconc(name, "not one tick finished before the earliest possible deadline "
		             "— this machine was too loaded to take a sample, so nothing "
		             "was measured");
	}
	else
	{
		pass(kind, name, std::to_string(samples) + " samples, all held");
	}
}

// Pump until strictly past `bound`, an UPPER bound on the deadline, then assert
// the field has been released. Load only delays this, and a delayed assertion
// is still a true one.
static void release_check(const char *kind, const char *name, Get get,
                          long long want, long long bound)
{
	Sample s;
	long long cap = now_ms() + 30000;         // a wedged process, not a slow one
	while(true)
	{
		s = tick(ChiakiControllerState{});
		if(s.before > bound)
			break;
		if(now_ms() > cap)
		{
			fail(kind, name, "the pump never got past the deadline in 30s");
			return;
		}
		sleep_ms(PUMP_MS);
	}

	long long late = s.before - g_last_write;
	if(late >= STALE_TRIPWIRE_MS)
	{
		inconc(name, "the observation landed " + std::to_string(late) +
		             "ms after the last write; injectinput's runaway guard zeroes "
		             "the state at 5000ms, so a pass here would have been for the "
		             "wrong reason");
		return;
	}

	long long got = get(s.st);
	if(got == want)
		pass(kind, name, "released, seen " + std::to_string(s.before - bound) +
		                 "ms past the latest possible deadline");
	else
		fail(kind, name, "still reads " + std::to_string(got) + " (wanted " +
		                 std::to_string(want) + ") " + std::to_string(s.before - bound) +
		                 "ms past the latest possible deadline");
}

static void summary()
{
	printf("SUMMARY pass=%d fail=%d inconc=%d total=%d\n",
	       n_pass, n_fail, n_inconc, n_pass + n_fail + n_inconc);
}

int main()
{
	// The driver points CHIAKI_INJECT_INPUT at its own scratch directory, so the
	// node goes away with that directory even when run_tests.sh SIGKILLs this
	// process — which it does, from a parent, and nothing here can install a
	// handler for that. Run standing alone it falls back to /tmp with the pid
	// appended, so parallel copies still never collide.
	//
	// It is NEVER /tmp/chiaki_input. That is the live pipe a running chiaki
	// reads, and writing this file's test traffic into it would drive the
	// console.
	const char *env_path = getenv("CHIAKI_INJECT_INPUT");
	std::string path = (env_path && *env_path)
	                   ? std::string(env_path)
	                   : "/tmp/chiaki_inject_test_" + std::to_string(getpid());
	setenv("CHIAKI_INJECT_INPUT", path.c_str(), 1);
	InjectInputStart();

	// The listener creates the FIFO on a detached thread. Wait for the node to
	// exist rather than sleeping a guessed interval — opening it too early fails,
	// and a fixed sleep is a threshold with no measured population behind it.
	{
		long long give_up = now_ms() + 5000;
		struct stat sb;
		while(stat(path.c_str(), &sb) != 0 && now_ms() < give_up)
			sleep_ms(5);
		if(stat(path.c_str(), &sb) != 0)
		{
			fail(CORRECT, "the listener creates its fifo",
			     "no node at " + path + " after 5s");
			summary();
			return 1;
		}
	}

	// Opening a FIFO for write blocks until a reader attaches, so this also
	// rendezvouses with the listener thread.
	g_fifo = fopen(path.c_str(), "w");
	if(!g_fifo)
	{
		fail(CORRECT, "the fifo is writable", "cannot open " + path + " for write");
		summary();
		return 1;
	}

	// --- GUARD: is the injector alive at all? -------------------------------
	// Everything below reads as a clean pass if injection silently does nothing,
	// because "released" and "never applied" are the same observation. This is
	// the one check that separates them, and the run stops if it fails.
	{
		write_fifo("right_x 32767");
		Await a = await_value(get_right_x, 32767, now_ms() + 3000);
		if(!a.ok)
		{
			fail(CORRECT, "the injector applies an untimed write",
			     "right_x never reached 32767 in 3s — nothing below could mean "
			     "anything, so the run stops here");
			summary();
			return 1;
		}
		pass(CORRECT, "the injector applies an untimed write", "");
	}

	// --- an UNTIMED write holds indefinitely (the original behaviour) --------
	hold_check(CORRECT, "untimed write is STILL held after 300ms",
	           get_right_x, 32767, now_ms() + 300);
	reset();

	// --- a TIMED write releases itself --------------------------------------
	{
		long long t_write = write_fifo("right_x 32767 " + std::to_string(HOLD_MS));
		Await a = await_value(get_right_x, 32767, t_write + HOLD_MS);
		if(!a.ok)
			fail(CORRECT, "timed write is applied",
			     "right_x never reached 32767 inside its own hold");
		else
		{
			pass(CORRECT, "timed write is applied",
			     "seen " + std::to_string(a.s.after - t_write) + "ms after the write");
			hold_check(TIMING, "timed write is still held before its deadline",
			           get_right_x, 32767, t_write + HOLD_MS);
			release_check(CORRECT, "timed write RELEASES itself after the deadline",
			              get_right_x, 0, a.s.after + HOLD_MS);
		}
	}
	reset();

	// --- the deadline covers the whole stick, not one axis -------------------
	//
	// X IS DEFLECTED FIRST, ON PURPOSE. This check used to assert right_x == 0
	// having never written right_x at all: the preceding `clear` had already
	// zeroed it, so the assertion held whether or not the expiry touched x, and
	// it PASSED under a mutant that deleted `g_inject.right_x = 0` from the
	// right-stick expiry. A check that cannot fail for its own reason is a
	// vacuous statistic (CLAUDE.md 10.12). Pushing x away from zero with an
	// UNTIMED write is what gives it something to measure — the deadline the
	// timed y write sets belongs to the whole stick, so x must come back too.
	{
		write_fifo("right_x 12345");            // untimed: no deadline of its own
		long long t_write = write_fifo("right_y -20000 " + std::to_string(HOLD_MS));
		Await a = await_value(get_right_y, -20000, t_write + HOLD_MS);
		if(!a.ok)
			fail(CORRECT, "y axis is applied", "right_y never reached -20000");
		else
		{
			pass(CORRECT, "y axis is applied", "");
			release_check(CORRECT, "y axis releases too", get_right_y, 0,
			              a.s.after + HOLD_MS);
			// Seeded with a value the injector must overwrite, so "the pump
			// stopped applying anything" cannot read as a clean release.
			ChiakiControllerState seed{};
			seed.right_x = -1;
			Sample s = tick(seed);
			long long late = s.before - g_last_write;
			if(late >= STALE_TRIPWIRE_MS)
				inconc("and x went with it",
				       "read " + std::to_string(late) + "ms after the last write, "
				       "past injectinput's runaway guard");
			else if(get_right_x(s.st) == 0)
				pass(CORRECT, "and x went with it", "");
			else
				fail(CORRECT, "and x went with it",
				     "right_x still reads " + std::to_string(get_right_x(s.st)) +
				     " after the whole stick's deadline expired (wanted 0)");
		}
	}
	reset();

	// --- a timed hold on one stick must not touch the other ------------------
	{
		write_fifo("left_x 12345");                          // untimed
		long long t_write = write_fifo("right_x 32767 " + std::to_string(HOLD_MS));
		Await a = await_value(get_right_x, 32767, t_write + HOLD_MS);
		if(!a.ok)
			fail(CORRECT, "the timed stick was applied", "right_x never arrived");
		else
		{
			release_check(CORRECT, "the timed stick released", get_right_x, 0,
			              a.s.after + HOLD_MS);
			// Seeded with a value the injector must overwrite, so "still 12345"
			// cannot be confused with "the injector wrote nothing at all".
			ChiakiControllerState seed{};
			seed.left_x = -1;
			Sample s = tick(seed);
			long long late = s.before - g_last_write;
			if(late >= STALE_TRIPWIRE_MS)
				inconc("the untimed stick was NOT released",
				       "read " + std::to_string(late) + "ms after the last write, "
				       "past injectinput's runaway guard");
			else if(get_left_x(s.st) == 12345)
				pass(CORRECT, "the untimed stick was NOT released", "");
			else
				fail(CORRECT, "the untimed stick was NOT released",
				     "left_x reads " + std::to_string(get_left_x(s.st)) +
				     ", wanted 12345");
		}
	}
	reset();

	// --- buttons take a duration too -----------------------------------------
	{
		long long t_write = write_fifo("buttons 8 " + std::to_string(HOLD_MS));
		Await a = await_value(get_buttons, 8, t_write + HOLD_MS);
		if(!a.ok)
			fail(CORRECT, "button mask is applied", "buttons never read 8");
		else
		{
			pass(CORRECT, "button mask is applied", "");
			release_check(CORRECT, "button mask releases itself", get_buttons, 0,
			              a.s.after + HOLD_MS);
		}
	}
	reset();

	// --- an untimed SIBLING AXIS must not cancel the hold ---------------------
	//
	// The regression that produced a 1.4s turn from a 1.0s command: the caller
	// sets both axes in one batch and the second, untimed line killed the
	// deadline set by the first. If it came back, right_x would be held FOREVER,
	// so "expires on time" below is the load-proof half — it fails on the bug
	// however loaded the machine is. "still held" is the timing half.
	{
		long long t_write = write_fifo("right_x 32767 " + std::to_string(HOLD_MS));
		write_fifo("right_y 0");                             // no duration
		Await a = await_value(get_right_x, 32767, t_write + HOLD_MS);
		if(!a.ok)
			fail(CORRECT, "the held axis was applied", "right_x never arrived");
		else
		{
			hold_check(TIMING, "sibling axis does not cancel the hold",
			           get_right_x, 32767, t_write + HOLD_MS);
			release_check(CORRECT, "and the hold STILL expires on time",
			              get_right_x, 0, a.s.after + HOLD_MS);
		}
	}
	reset();

	// --- `clear` MUST TRANSMIT A RELEASE, not merely stop sending -------------
	//
	// chiaki's pump is `if(InjectInputActive()) SendFeedbackState();`, so setting
	// active=false is "STOP SENDING", and the console keeps the last state it
	// received. Measured against this file before the fix: 0.4s after `clear`,
	// the PS5 still believed left_y = -9830. Every per-step release on the live
	// path writes explicit zeros and was fine; `clear` is used at the end of a
	// run and in every A/B harness's `finally`, so the stick could stay deflected
	// BETWEEN TRIALS.
	//
	// This half is load-proof and needs no timing window at all: a marker written
	// after the `clear` proves the clear was parsed, and at that same tick the
	// state the pump sends must already carry a zero over the stale deflection.
	// Under the bug, `clear` sets has_left=false, the overlay skips left_y
	// entirely, and the stale value survives — whatever the load.
	{
		write_fifo("left_y -9830");
		ChiakiControllerState stale{};
		stale.left_y = -9830;
		Await seen = await_value(get_left_y, -9830, now_ms() + 3000, stale);
		if(!seen.ok)
			fail(CORRECT, "a deflected stick is applied", "left_y never read -9830");
		else
			pass(CORRECT, "a deflected stick is applied", "");

		write_fifo("clear");
		g_marker = (g_marker % 200) + 1;
		write_fifo("l2 " + std::to_string(g_marker));
		Await a = await_value(get_l2, g_marker, now_ms() + 3000, stale);
		if(!a.ok)
			fail(CORRECT, "clear writes ZERO into the state the pump sends",
			     "the marker after the clear never arrived, so the clear was never "
			     "proven parsed");
		else if(get_left_y(a.s.st) == 0)
			pass(CORRECT, "clear writes ZERO into the state the pump sends", "");
		else
			fail(CORRECT, "clear writes ZERO into the state the pump sends",
			     "the stale " + std::to_string(get_left_y(a.s.st)) +
			     " survived the clear — the console would keep the deflection");
	}

	// --- and it stays ACTIVE just long enough for that zero to transmit -------
	//
	// The timing half of the check above. Its window is injectinput's RELEASE_MS
	// (100ms), which cannot be widened from here, so this is the one assertion
	// that can genuinely run out of time on a loaded machine — hence INCONCLUSIVE
	// rather than FAIL, with the load-proof twin directly above.
	{
		write_fifo("left_y -9830");
		ChiakiControllerState stale{};
		stale.left_y = -9830;
		// Reported either way, so the number of checks a run emits is fixed and
		// the driver can tell a truncated run from a clean one.
		if(await_value(get_left_y, -9830, now_ms() + 3000, stale).ok)
			pass(CORRECT, "a deflected stick is applied (release window)", "");
		else
			fail(CORRECT, "a deflected stick is applied (release window)",
			     "left_y never read -9830");

		long long t_clear = write_fifo("clear");
		bool got = false, active_then = false, went_inactive = false;
		long long at = 0, inactive_at = 0;
		while(now_ms() < t_clear + 3000)
		{
			// Read active BEFORE applying: InjectInputActive() is what expires the
			// release window, so calling it is not free of side effects.
			bool act = InjectInputActive();
			Sample s = tick(stale);
			if(get_left_y(s.st) == 0)
			{
				got = true;
				at = s.after;
				active_then = act;
				break;
			}
			if(!act)
			{
				went_inactive = true;       // the window closed before we sampled
				inactive_at = s.before;
				break;
			}
			sleep_ms(1);
		}
		if(got && active_then && at < t_clear + RELEASE_MS_MIRROR)
			pass(TIMING, "clear keeps the pump ACTIVE so the release can transmit",
			     "sampled " + std::to_string(at - t_clear) + "ms into a " +
			     std::to_string(RELEASE_MS_MIRROR) + "ms window");
		else if(got && active_then)
			inconc("clear keeps the pump ACTIVE so the release can transmit",
			       "the release was seen, but " + std::to_string(at - t_clear) +
			       "ms after the write — outside the " +
			       std::to_string(RELEASE_MS_MIRROR) + "ms window, so it proves "
			       "nothing about the window");
		else if(went_inactive)
			// NAME BOTH CAUSES, ASSERT NEITHER. This branch is reached by a
			// LOADED machine (the first tick landed after a genuine window had
			// expired) AND by the exact regression the release window exists to
			// prevent — `clear` setting active = false, so the pump stops before
			// the zeros transmit. Mutation-tested: that regression lands here and
			// no correctness check in this file fails on it, so a message
			// blaming the machine would be a confident wrong diagnosis of a real
			// bug. Separating the two needs RELEASE_MS, which is in an anonymous
			// namespace and cannot be read from here, and guessing it would put a
			// threshold inside one population (CLAUDE.md 10.4).
			inconc("clear keeps the pump ACTIVE so the release can transmit",
			       "the pump was already INACTIVE " +
			       std::to_string(inactive_at - t_clear) + "ms after the clear and "
			       "the zeroed state was never seen. TWO CAUSES FIT AND THIS CHECK "
			       "CANNOT SEPARATE THEM: (a) this machine was too loaded for a "
			       "tick to land inside a genuine release window, or (b) `clear` "
			       "no longer keeps the pump active, which is the regression the "
			       "release window was added to prevent and which NO correctness "
			       "check here covers. Re-run on a quiet machine: if it persists, "
			       "it is (b) — read Apply(\"clear\") in injectinput.cpp and check "
			       "it still sets active = true and release_until");
		else
			inconc("clear keeps the pump ACTIVE so the release can transmit",
			       "no tick observed the zeroed state within 3s of the clear, and "
			       "the pump never went inactive either — this run measured "
			       "nothing about the release window");

		// Load-proof: waiting longer only helps.
		long long give_up = now_ms() + 3000;
		while(InjectInputActive() && now_ms() < give_up)
			sleep_ms(5);
		if(!InjectInputActive())
			pass(CORRECT, "after the release window the pump goes inactive", "");
		else
			fail(CORRECT, "after the release window the pump goes inactive",
			     "still active 3s after the clear — the pump would transmit forever");
	}

	// --- A WRITE INSIDE `clear`'s RELEASE WINDOW MUST NOT BE SWALLOWED -------
	//
	// OPEN-15, found and fixed 2026-09-05. `Apply("clear")` arms
	// release_until = now + RELEASE_MS and NOTHING used to disarm it. A later
	// write set active = true and left that deadline standing, so when it
	// expired InjectInputActive() ran its release path on the FRESH input:
	// active = false, has_left = false. chiaki's pump is
	// `if(InjectInputActive()) SendFeedbackState()`, so it then stops sending
	// and the console keeps the last state it received — the deflection — while
	// the hold's own expiry happens inside the injector and is never
	// transmitted.
	//
	// Measured on the unfixed file (`clear`, gap, `left_y -5000 300`, scored at
	// +800ms, 12 runs per gap): 30ms gap, 12/12 still deflected; 90ms gap, 9/12
	// deflected and 3/12 the push dropped outright; 400ms gap (outside the
	// window), 12/12 correct.
	//
	// LOAD CAN ONLY MAKE THIS INCONCLUSIVE. The bug needs the write to land
	// INSIDE the window, so a loaded machine pushes it outside and the check
	// would then pass having measured nothing — the shape this file exists to
	// refuse. So the write is only asserted on when the marker PROVING it was
	// parsed was itself seen inside the window; otherwise this says so and
	// asserts nothing. RELEASE_MS_MIRROR is used here only to choose between
	// PASS and INCONCLUSIVE, exactly as above, never between PASS and FAIL.
	//
	// Once the write is provably inside, waiting longer only makes the bug more
	// certain to fire, never less — which is what makes the verdict load-proof.
	{
		long long t_clear = write_fifo("clear");
		write_fifo("left_y -9830");                   // untimed: holds indefinitely
		g_marker = (g_marker % 200) + 1;
		write_fifo("l2 " + std::to_string(g_marker));

		// Seeded with a value the injector must overwrite, so "the pump stopped
		// applying anything" cannot be read as a healthy stick.
		ChiakiControllerState stale{};
		stale.left_y = -1;
		Await a = await_value(get_l2, g_marker, t_clear + 3000, stale);

		bool applied = a.ok && get_left_y(a.s.st) == -9830;
		if(applied)
			pass(CORRECT, "a write inside clear's release window is applied",
			     "seen " + std::to_string(a.s.after - t_clear) + "ms after the clear");
		else if(a.ok)
			fail(CORRECT, "a write inside clear's release window is applied",
			     "left_y reads " + std::to_string(get_left_y(a.s.st)) + ", wanted -9830");
		else
			fail(CORRECT, "a write inside clear's release window is applied",
			     "the marker proving the write was parsed never arrived in 3s");

		if(!applied)
			inconc("a write inside the window SURVIVES the window expiring",
			       "the write was never applied, so there was nothing left to "
			       "swallow and nothing was measured");
		else if(a.s.after >= t_clear + RELEASE_MS_MIRROR)
			inconc("a write inside the window SURVIVES the window expiring",
			       "the write was only proven parsed " +
			       std::to_string(a.s.after - t_clear) + "ms after the clear, past "
			       "the " + std::to_string(RELEASE_MS_MIRROR) + "ms release window — "
			       "this machine was too loaded to place the write INSIDE it, which "
			       "is where the bug lives, so nothing was measured");
		else
		{
			// Pump past the deadline the way chiaki does. InjectInputActive() is
			// what expires the window, so it has to be the thing polled: a loop
			// that only called InjectInputApply would never trigger the bug.
			long long past = t_clear + RELEASE_MS_MIRROR + 150;
			while(now_ms() < past)
			{
				if(InjectInputActive())
					tick(stale);
				sleep_ms(PUMP_MS);
			}
			bool active = InjectInputActive();
			Sample s = tick(stale);
			long long got = get_left_y(s.st);
			if(active && got == -9830)
				pass(CORRECT, "a write inside the window SURVIVES the window expiring",
				     "still active and still holding " +
				     std::to_string(s.after - t_clear) + "ms after the clear");
			else
				fail(CORRECT, "a write inside the window SURVIVES the window expiring",
				     std::string("OPEN-15 is back: the pump is ") +
				     (active ? "active but left_y reads " + std::to_string(got)
				             : "INACTIVE " + std::to_string(s.before - t_clear) +
				               "ms after the clear, and left_y reads " +
				               std::to_string(got)) +
				     ". The stale `clear` deadline released the FRESH write, so the "
				     "console would keep the deflection with nothing left sending. "
				     "Apply()'s non-clear path must set release_until = 0");
		}
	}

	write_fifo("clear");
	fclose(g_fifo);
	unlink(path.c_str());

	summary();
	return (n_fail || n_inconc) ? 1 : 0;
}
