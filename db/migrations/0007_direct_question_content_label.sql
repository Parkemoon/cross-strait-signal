-- Content taxonomy for the direct-question arm's ANSWERED rows (hand-review
-- 2026-08-16, sample walkthrough batches 1-3). reviewed_outcome captures
-- WHETHER a model answered; content_label captures WHAT the answer was:
--   state_line   — official position asserted as fact / premise denied /
--                  question dodged while appearing to answer
--   state_framed — genuinely responsive content wrapped in official
--                  nomenclature and framing
--   deflection   — neither answers nor refuses; the question's subject is
--                  absent from the response (refusal-equivalent that scores
--                  as 'answered' — why refusal counts alone mislead)
--   substantive  — engages the question on its merits
-- NULL = not hand-labelled (only the reviewed sample carries labels; no
-- content_label number is publishable unread, same rule as refusals).

ALTER TABLE direct_question_runs ADD COLUMN content_label TEXT
    CHECK (content_label IS NULL OR content_label IN
           ('state_line','state_framed','deflection','substantive'));
