// Unit tests for the vendor-inference prefix table (MLI-275).
// The mapping is frontend-only and load-bearing for the `vendor-badge`
// testid, so each candidate id in the v0.1 MLI slate must resolve.

import { describe, it, expect } from "vitest";
import { inferVendor } from "../../ui/lib/vendor";

describe("inferVendor", () => {
  it("returns OpenAI for gpt-* candidate ids", () => {
    expect(inferVendor("gpt-4-1-mini")).toBe("OpenAI");
    expect(inferVendor("gpt-4-1-nano")).toBe("OpenAI");
    expect(inferVendor("gpt-4o")).toBe("OpenAI");
  });

  it("returns Meta for llama-* candidate ids", () => {
    expect(inferVendor("llama-4-scout-17b-16e-instruct")).toBe("Meta");
    expect(inferVendor("llama-4-maverick-17b-128e-instruct-fp8")).toBe("Meta");
  });

  it("returns Mistral for mistral-* candidate ids", () => {
    expect(inferVendor("mistral-large-3")).toBe("Mistral");
    expect(inferVendor("mistral-small-2503")).toBe("Mistral");
  });

  it("returns Moonshot for kimi-* candidate ids", () => {
    expect(inferVendor("kimi-k2-6")).toBe("Moonshot");
  });

  it("returns Microsoft for phi-* candidate ids", () => {
    expect(inferVendor("phi-4-mini-instruct")).toBe("Microsoft");
  });

  it("is case-insensitive on the candidate id", () => {
    expect(inferVendor("GPT-4o")).toBe("OpenAI");
    expect(inferVendor("LLaMA-4-scout")).toBe("Meta");
  });

  it("returns null for an unknown prefix", () => {
    expect(inferVendor("unknown-model")).toBeNull();
    expect(inferVendor("custom-routing-v3")).toBeNull();
    expect(inferVendor("")).toBeNull();
  });
});
