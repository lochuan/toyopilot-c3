import { describe, expect, it } from "vitest";
import { containRect } from "../src/lib/splash";

describe("containRect", () => {
  it("fills the screen when the aspect matches", () => {
    expect(containRect(4320, 2160, 2160, 1080)).toEqual({ x: 0, y: 0, width: 2160, height: 1080 });
  });

  it("letterboxes left and right for a square image", () => {
    expect(containRect(1000, 1000, 2160, 1080)).toEqual({ x: 540, y: 0, width: 1080, height: 1080 });
  });

  it("letterboxes top and bottom for a wide image", () => {
    expect(containRect(4000, 1000, 2160, 1080)).toEqual({ x: 0, y: 270, width: 2160, height: 540 });
  });
});
