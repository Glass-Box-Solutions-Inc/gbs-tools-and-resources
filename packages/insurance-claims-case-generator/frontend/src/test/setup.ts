import "@testing-library/jest-dom";

// Polyfill ResizeObserver — required by Radix UI Slider in jsdom
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
