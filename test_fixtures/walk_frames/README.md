# Gameplay frames — every 20th of demos/walk3_full_20260828_050731

Copied 2026-09-17. `demos/` is GITIGNORED, so these frames do not exist on a fresh
clone and the tests reading them could not run for anyone but the machine that
recorded them. Measured by hiding demos/: test_reticle_scaling and test_turn_control
both FAILED -- honest, but unrunnable.

They are a SAMPLE, and the stride is already applied here: the tests take these as
they are. Re-applying `[::20]` would leave two frames.

    test_reticle_scaling   in_gameplay() must hold at 1400 / 1920 / 2000 px
    test_turn_control      the positive half of the in_gameplay gate
