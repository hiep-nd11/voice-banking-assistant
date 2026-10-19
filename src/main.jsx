import React from "react";
import { createRoot } from "react-dom/client";
import { loadAppConfig } from "./lib/config.js";
import "./styles.css";
async function start() {
  try {
    const config = await loadAppConfig();
    document.title = config.app.title;
    const { default: App } = await import("./App.jsx");
    createRoot(document.getElementById("app")).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    );
  } catch (error) {
    document.getElementById("app").textContent =
      `Không thể khởi động ứng dụng. Kiểm tra file app-config.json. ${error.message}`;
  }
}
start();
