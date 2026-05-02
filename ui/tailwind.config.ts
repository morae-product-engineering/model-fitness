import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // Matches the prototype token: --font-sans
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        // Neutral palette lifted from prototype tokens
        neutral: {
          1:  "#0d0d0d",
          3:  "#262626",
          5:  "#595959",
          6:  "#737373",
          10: "#d9d9d9",
          11: "#e6e6e6",
          12: "#f2f2f2",
          13: "#f9f9f9",
        },
        orange: "#ff6900",
      },
    },
  },
  plugins: [],
};

export default config;
