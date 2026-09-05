# Analog input for chiaki-ng

Adds a listener that accepts real stick values, so an external program can send
0.54 deflection as the number it is. chiaki's keyboard mapping only ever sends
full deflection, and a recorded human walk sits near half — pulsing a key does
not reproduce that, because each pulse re-accelerates from a standstill.

## Files
    injectinput.{h,cpp}   the listener
    chiaki.patch          hooks it into Controller::GetState()

## Build (macOS, verified 2026-08-27)

    brew install streetpea/streetpea/chiaki-ng-qt@6 ffmpeg@7 pkgconfig opus \
      openssl cmake ninja nasm sdl2 protobuf@29 speexdsp libplacebo wget \
      python-setuptools json-c miniupnpc libevent

    git clone https://github.com/streetpea/chiaki-ng.git && cd chiaki-ng
    git submodule update --init --recursive
    git apply /path/to/chiaki.patch
    cp /path/to/injectinput.* gui/src/

    brew unlink ffmpeg          # SEE BELOW — this is not optional
    cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCHIAKI_ENABLE_CLI=OFF -DCHIAKI_ENABLE_STEAMDECK_NATIVE=OFF \
      -DCHIAKI_ENABLE_STEAM_SHORTCUT=OFF \
      -DCMAKE_PREFIX_PATH="$(brew --prefix)/opt/openssl@3;$(brew --prefix)/opt/chiaki-ng-qt@6;$(brew --prefix)/opt/protobuf@29;$(brew --prefix)/opt/libevent;$(brew --prefix)/opt/ffmpeg@7"
    ninja -C build

## The trap that cost two hours

If ffmpeg 9 is linked in Homebrew, `/opt/homebrew/include` lands ahead of
ffmpeg@7 in the include path, and chiaki compiles against ffmpeg 9's headers
while linking ffmpeg 7's libraries. `AV_CODEC_ID_HEVC` is 172 in one and 173 in
the other, so the stream asks for HEVC and the decoder hears `hnm4video`:

    [E] avcodec_get_hw_config failed (codec=hnm4video, id=172)

`brew unlink ffmpeg` removes the shadowing headers. `brew link ffmpeg` puts
them back when you are done. -I flags do NOT fix this: cmake emits INCLUDES
before FLAGS, so the wrong path still wins.

Two other local workarounds, both cosmetic: a stub AGL framework (the SDK no
longer ships AGL.tbd, but the real one still resolves from the dyld shared
cache at runtime), and -DCHIAKI_ENABLE_STEAM_SHORTCUT=OFF.

## Use

    CHIAKI_INJECT_INPUT=/tmp/chiaki_input .../chiaki.app/Contents/MacOS/chiaki
    echo "left_x 17694" > /tmp/chiaki_input     # 0.54 deflection
    echo "clear"        > /tmp/chiaki_input     # hand control back

Fields: left_x left_y right_x right_y (-32768..32767), l2 r2 (0..255),
buttons (bitmask), clear. Each is independent, so the sticks can be driven
while the real controller keeps its buttons — you can take over mid-run.

VERIFIED WORKING 2026-08-27 23:20: `left_x 17694` moved the character.
