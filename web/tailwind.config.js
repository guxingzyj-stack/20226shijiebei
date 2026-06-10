/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        pitch: "#0D3826",
        pitch2: "#14513A",
        paper: "#F2F0E4",
        gold: "#E8B33C",
        danger: "#D94A38",
      },
      boxShadow: {
        soft: "0 18px 50px rgba(0,0,0,0.22)",
      },
    },
  },
  plugins: [],
};
