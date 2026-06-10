import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { BetSlipProvider } from "./bet/BetSlipContext";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <BetSlipProvider>
          <App />
        </BetSlipProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
