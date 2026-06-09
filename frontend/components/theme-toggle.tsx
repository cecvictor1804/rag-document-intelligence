"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { setTheme } = useTheme();

  // No mounted-guard / effect needed: both icons render, and CSS (`.dark` on
  // <html>, set by next-themes before paint) shows the right one. This avoids
  // any hydration mismatch. The current theme is read from the DOM on click.
  function toggle() {
    const isDark = document.documentElement.classList.contains("dark");
    setTheme(isDark ? "light" : "dark");
  }

  return (
    <Button variant="ghost" size="icon" aria-label="Toggle light/dark theme" onClick={toggle}>
      <Sun className="hidden size-4 transition-transform duration-200 dark:block" />
      <Moon className="block size-4 transition-transform duration-200 dark:hidden" />
    </Button>
  );
}
