import { groupSignals } from "./signalGroups";

const sig = (id, topic, published_at, urgency = "priority") =>
  ({ id, topic_primary: topic, published_at, urgency });

test("one group per topic, most recently active first", () => {
  const groups = groupSignals([
    sig(1, "DIP_SANCTIONS", "2026-10-12T10:49:00"),
    sig(2, "DIP_SANCTIONS", "2026-10-13T02:59:00"),
    sig(3, "MIL_EXERCISE", "2026-10-13T04:36:00"),
    sig(4, "DIP_SANCTIONS", "2026-10-12T16:13:00"),
  ]);
  expect(groups.map((g) => g.topic)).toEqual(["MIL_EXERCISE", "DIP_SANCTIONS"]);
  expect(groups[1].lead.id).toBe(1);
  expect(groups[1].more.map((s) => s.id)).toEqual([4, 2]);
});

test("a flash report leads its topic even when it came later", () => {
  const [g] = groupSignals([
    sig(1, "MIL_EXERCISE", "2026-07-23T08:00:00"),
    sig(2, "MIL_EXERCISE", "2026-07-23T09:00:00", "flash"),
  ]);
  expect(g.lead.id).toBe(2);
  expect(g.more.map((s) => s.id)).toEqual([1]);
});

test("a signal without a topic stands alone; empty input is fine", () => {
  const groups = groupSignals([sig(1, null, "2026-10-13T00:00:00"), sig(2, null, "2026-10-13T01:00:00")]);
  expect(groups).toHaveLength(2);
  expect(groupSignals(undefined)).toEqual([]);
});
