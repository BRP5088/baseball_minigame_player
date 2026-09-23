# i70_slightly fixtures

I-70: a power disc PARTLY covered by the next card in the fan reads nothing under
the ungated reader (score 0.53-0.78 against MIN_SCORE 0.80), though a human can
still read it. Fixed by `local_hand._left_masked_digit_search` (see LEFT_MASK_COLS
in local_hand.py). These three PNGs are copied byte-for-byte from the (gitignored)
`diagnostics/deal_frames/` dump, same convention as `test_fixtures/hand_reads/`.

  slightly_slot0_digit5.png  diagnostics/deal_frames/dropped_1790055478311185000/hand.png
      user_truth/20260923_c20-26/labels.json q26: slot 0, power 5, verdict "slightly".
      Recovers under the shipped reader (score 0.979 in agent_progress/issues/I-70
      measurement).

  covered_slot0_digit4.png  diagnostics/deal_frames/dropped_1790171828873351000/hand.png
      user_truth/20260923_c27-30/labels.json q03: slot 0, power 4, verdict "covered"
      ("I can read it but I don't think you would be able to"). A bonus recovery,
      not required -- included as a case where the true power IS known even though
      the user's verdict says "covered", so a wrong digit here would be caught.

  covered_slot1_digit4.png  diagnostics/deal_frames/dropped_1790173536235015000/hand.png
      user_truth/20260923_c27-30/labels.json q16: slot 1, power 4, verdict "covered"
      ("I can barely read the power"). SAFETY case: whatever the shipped reader does
      here (abstain or recover), it must never claim a digit other than 4.

See agent_progress/issues/I-70/progress.md for the full measurement this fix is
based on -- 27/28 certain-power "slightly" slots across three label sets, plus a
23-frame and a 200-frame FALSE-population check, both zero wrong.
