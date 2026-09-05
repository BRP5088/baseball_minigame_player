// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
//
// External analog input for chiaki-ng.
//
// WHY
// ---
// chiaki's keyboard mapping sends fixed, full-deflection stick values — there
// is no analog channel for a key. Anything driving chiaki programmatically
// (automation, playback of a recorded session, accessibility hardware) can
// therefore only ever send "fully pushed" or "not pushed", which is not how a
// person plays: a recorded human walk sits around half deflection.
//
// This adds a listener that accepts real stick values and overlays them onto
// the controller state, so an external process can express 0.54 as the number
// it is rather than approximating it by pulsing a key.
//
// OPT-IN. Nothing happens unless CHIAKI_INJECT_INPUT is set in the
// environment, naming a path to listen on. A normal launch is unaffected and
// pays only a single atomic read per GetState().
//
// PROTOCOL — newline-delimited text, one field per line:
//      left_x <-32768..32767>
//      left_y <-32768..32767>
//      right_x <...>
//      right_y <...>
//      l2 <0..255>
//      r2 <0..255>
//      buttons <bitmask>
//      clear                  stop overlaying; hand control back
//
// Any of the above may carry an OPTIONAL THIRD FIELD, a hold time in
// milliseconds, after which this side releases the field by itself:
//      right_x 32767 400      push right stick right for 400ms, then centre
//      buttons 8 80           hold triangle for 80ms, then release
//
// This exists because a caller timing the hold itself has to send a second
// line to end it, and the duration the console sees is then the gap between
// two FIFO round trips — sleep granularity, two opens and closes, this
// reader thread waking, and the pump phase at both edges all land on it.
// Measured: two identical 1.0s full-stick camera turns came out 7.7 degrees
// apart. A deadline is timed here, on the same clock the pump runs on, so
// the release no longer depends on anything outside this process.
//
// Omitting the third field keeps the original behaviour exactly: the value
// is held until something changes it.
//
// Text so it can be driven from a shell or any language without bindings:
//      echo "left_x 17694" > $CHIAKI_INJECT_INPUT

#ifndef CHIAKI_INJECTINPUT_H
#define CHIAKI_INJECTINPUT_H

#include <chiaki/controller.h>

// Start the listener if CHIAKI_INJECT_INPUT is set. Safe to call repeatedly;
// only the first call does anything.
void InjectInputStart();

// Overlay any injected values onto `state`. No-op when nothing is injected,
// so this stays cheap on the normal path.
void InjectInputApply(ChiakiControllerState *state);

// True once anything has been injected and not cleared.
//
// StreamSession needs this because its send path is entirely
// EVENT-DRIVEN: SendFeedbackState runs on a controller StateChanged
// signal, or a keyboard/mouse/touch event, and nothing else. With no
// controller connected and nobody typing, it is never called, so
// injected state is never transmitted no matter where it is applied.
// A connected controller hid this by pumping the path constantly.
bool InjectInputActive();

#endif // CHIAKI_INJECTINPUT_H
