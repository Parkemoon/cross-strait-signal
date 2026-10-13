// Top of the Brief groups the day's escalation signals by topic: one lead
// card per topic, the other reports on it folded underneath. A big story
// (the 2026-10-12 sanctions on Paraguay and Belize ministers: 9 signals
// from 6 outlets) otherwise fills the section with near-identical cards.
// Display only: no flag changes, the escalation filter still lists every
// signal. The key is the topic code, not the event cluster, because event
// clusters split one story across several ids (14 signals on 2026-07-23
// were 8 clusters but 4 topics; ids are also regenerated every tick). The
// cost: two unrelated stories on one topic in a day share a card, the
// second one click away.

const URGENCY_RANK = { flash: 0, priority: 1, routine: 2 };

const byLead = (a, b) =>
  (URGENCY_RANK[a.urgency] ?? 3) - (URGENCY_RANK[b.urgency] ?? 3) ||
  (a.published_at || "").localeCompare(b.published_at || "");

/** -> [{ topic, lead, more, latest }], most recently active topic first.
 *  Lead = most urgent, then earliest (the outlet that broke it). */
export function groupSignals(signals) {
  const byTopic = new Map();
  for (const s of signals || []) {
    const key = s.topic_primary || `article-${s.id}`;
    if (!byTopic.has(key)) byTopic.set(key, []);
    byTopic.get(key).push(s);
  }
  return [...byTopic.entries()]
    .map(([topic, items]) => {
      const [lead, ...more] = [...items].sort(byLead);
      const latest = items.reduce((m, s) => ((s.published_at || "") > m ? s.published_at : m), "");
      return { topic, lead, more, latest };
    })
    .sort((a, b) => b.latest.localeCompare(a.latest));
}
