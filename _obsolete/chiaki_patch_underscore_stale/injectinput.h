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

#endif // CHIAKI_INJECTINPUT_H
