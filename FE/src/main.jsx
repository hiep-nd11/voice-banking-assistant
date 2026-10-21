import React from "react";
import { createRoot } from "react-dom/client";
import { loadAppConfig } from "./lib/config.js";
import { loadBankingData } from "./lib/banking.js";
import "./styles.css";
async function start() {
  try {
    const config = await loadBankingData(await loadAppConfig());
    document.title = config.app.title;
    const { default: App } = await import("./App.jsx");
    createRoot(document.getElementById("app")).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    );
  } catch (error) {
    document.getElementById("app").textContent =
      `Không thể tải ứng dụng. ${error.message} Hãy kiểm tra kết nối và tải lại trang.`;
  }
}
start();
