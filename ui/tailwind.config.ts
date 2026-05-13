import type { Config } from "tailwindcss";

// Colours and font stacks resolve to CSS variables defined in app/globals.css,
// which are themselves inlined from ui/prototype/assets/colors_and_type.css.
const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      colors: {
        neutral: {
          1:  "var(--neutral-1)",
          2:  "var(--neutral-2)",
          3:  "var(--neutral-3)",
          4:  "var(--neutral-4)",
          5:  "var(--neutral-5)",
          6:  "var(--neutral-6)",
          7:  "var(--neutral-7)",
          8:  "var(--neutral-8)",
          9:  "var(--neutral-9)",
          10: "var(--neutral-10)",
          11: "var(--neutral-11)",
          12: "var(--neutral-12)",
          13: "var(--neutral-13)",
        },
        // Brand warm spectrum
        red:           "var(--red)",
        "red-orange":  "var(--red-orange)",
        orange:        "var(--orange)",
        "yellow-orange": "var(--yellow-orange)",
        yellow:        "var(--yellow)",
        // Semantic accents
        green:         "var(--green)",
        "warm-yellow": "var(--warm-yellow)",
        "warm-red":    "var(--warm-red)",
        purple:        "var(--purple)",
        // Blues
        "blue-1":      "var(--blue-1)",
        "blue-2":      "var(--blue-2)",
        // Tints (chip backgrounds)
        "light-blue":   "var(--light-blue)",
        "light-yellow": "var(--light-yellow)",
        "light-green":  "var(--light-green)",
        "light-red":    "var(--light-red)",
        "light-purple": "var(--light-purple)",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        // Tailwind already ships sm/md/lg; prefix the prototype's tokens
        // so we don't shadow them. Components opt in explicitly.
        "elev-sm": "var(--shadow-sm)",
        "elev-md": "var(--shadow-md)",
        "elev-lg": "var(--shadow-lg)",
      },
    },
  },
  plugins: [],
};

export default config;
