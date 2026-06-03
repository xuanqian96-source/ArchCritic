// 页面入口：加载独立复刻应用和统一样式。
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ProfileProvider } from "./state/profile";
import { WorkspaceProvider } from "./state/workspace";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ProfileProvider>
      <WorkspaceProvider>
        <App />
      </WorkspaceProvider>
    </ProfileProvider>
  </React.StrictMode>,
);
