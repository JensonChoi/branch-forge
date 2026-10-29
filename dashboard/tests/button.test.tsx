// @vitest-environment jsdom
import React from "react";
import { it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { Button } from "../src/components/ui/button";
it("provides accessible disabled replay controls", () => {
  const click = vi.fn();
  const view = render(
    <Button disabled aria-label="Play" onClick={click}>
      Play
    </Button>,
  );
  fireEvent.click(view.getByRole("button", { name: "Play" }));
  expect(click).not.toHaveBeenCalled();
});
