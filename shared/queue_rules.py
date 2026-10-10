"""Deterministic binning of exercise, poll and key-figure statement
candidates that could never be approved (Ed, 2026-10-10). Each rule is a
SQL condition on a pending row; a match is dismissed with
reviewed_by = 'rule:<name>', so every bin can be listed or reverted by its
stamp. First matching rule wins.

Measured against Ed's own past decisions on prod before going in
(2026-10-10), as rows each rule matches:

    military_exercises  no-start-date     2 of 69 approved, 323 of 1,871 dismissed
                        no-location       1 of 69 approved,  73 of 1,871 dismissed
    polls (AI rows)     unknown-pollster  1 of 55 approved or merged, 65 of 137 dismissed
                        no-sample-size +  7 of 55 between them, mostly Taiwan Brain
                        no-end-date       Trust, whose coverage rarely prints either
    key_figure_statements  not-a-quote    6 of 222 approved, 1,006 of 5,907 dismissed

A rule only ever dismisses. Key-figure statements are never approved
without the analyst (misattribution risk); binning a paraphrased "action"
cannot publish anything.

"No coordinates" was rejected as a location rule: it would have binned 23 of
the 69 approved exercises (the geocoder has no point for "waters east of
Taiwan"). The two poll completeness rules cost 7 of the 55 kept polls; Ed
took them anyway ("keep the ones I kept": rules never touch approved rows).

Rows an analyst has already edited (PATCH stamps reviewed_at) are never
binned. A poll bin keeps pending_results_json (a manual dismiss NULLs it) so
a revert gives back a usable pending row."""

STAMP = 'rule:'

RULES = {
    'military_exercises': [
        ('no-start-date', "COALESCE(TRIM(start_date), '') = ''"),
        ('no-location', "COALESCE(TRIM(location_label), '') = ''"),
    ],
    'key_figure_statements': [
        # 'action' / 'statement' rows are the model's paraphrase of what a
        # figure did, not words they said; the panel shows quotes.
        ('not-a-quote', "COALESCE(statement_kind, '') <> 'quote'"),
    ],
    'polls': [
        ('unknown-pollster',
         "source_article_id IS NOT NULL"
         " AND pollster_id IN (SELECT id FROM pollsters WHERE slug = 'unknown')"),
        ('no-sample-size', "source_article_id IS NOT NULL AND COALESCE(sample_size, 0) <= 0"),
        ('no-end-date', "source_article_id IS NOT NULL AND COALESCE(TRIM(fielded_end), '') = ''"),
    ],
}


def bin_candidates(conn, apply=False):
    """Match every rule against the pending, analyst-untouched rows.

    Returns [(table, rule, [ids])] in rule order, each id under the first
    rule it matched. With apply=True the matches are dismissed and stamped,
    and the connection is committed."""
    out = []
    for table, rules in RULES.items():
        claimed = set()
        for name, cond in rules:
            ids = [r[0] for r in conn.execute(
                f"SELECT id FROM {table} WHERE approval_status = 'pending'"
                f" AND reviewed_at IS NULL AND ({cond}) ORDER BY id")
                if r[0] not in claimed]
            claimed.update(ids)
            out.append((table, name, ids))
            if apply and ids:
                conn.executemany(
                    f"UPDATE {table} SET approval_status = 'dismissed',"
                    " reviewed_at = datetime('now'), reviewed_by = ?"
                    " WHERE id = ? AND approval_status = 'pending'",
                    [(STAMP + name, i) for i in ids])
    if apply:
        conn.commit()
    return out


def revert_bins(conn, rule=None):
    """Put rule-binned rows back in the queue (all rules, or one by name).
    Rows an analyst has since re-reviewed carry another stamp and stay put.
    Returns the number of rows restored; commits."""
    stamp = STAMP + rule if rule else STAMP + '%'
    restored = 0
    for table in RULES:
        restored += conn.execute(
            f"UPDATE {table} SET approval_status = 'pending', reviewed_at = NULL,"
            " reviewed_by = NULL WHERE approval_status = 'dismissed'"
            " AND reviewed_by LIKE ?", (stamp,)).rowcount
    conn.commit()
    return restored
