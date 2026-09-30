import { diffSummary } from "./diff";

test("trims shared prefix and suffix and keeps only the diverging words", () => {
  expect(diffSummary("Pump P-41 seal replaced by ROBOT-01 today", "Pump P-41 seal replaced with type B today"))
    .toEqual({ same: false, a: "by ROBOT-01", b: "with type B" });
});
test("identical text is reported as same; one-sided additions stay one-sided", () => {
  expect(diffSummary("a b", "a  b").same).toBe(true);
  expect(diffSummary("a b", "a b c")).toEqual({ same: false, a: "", b: "c" });
});
test("long divergences are clipped", () => {
  expect(diffSummary("x", "y ".repeat(200)).b.length).toBeLessThanOrEqual(140);
});
