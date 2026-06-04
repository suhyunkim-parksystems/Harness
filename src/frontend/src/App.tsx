import { useState } from "react";

import { DashboardTab } from "./components/DashboardTab";
import { SearchTab } from "./components/SearchTab";

type ActiveTab = "dashboard" | "search";

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("dashboard");

  return (
    <main className="dashboard-page">
      <nav className="tab-nav" role="tablist" aria-label="메인 탭">
        <button
          type="button"
          role="tab"
          className={`tab-btn${activeTab === "dashboard" ? " tab-btn--active" : ""}`}
          aria-selected={activeTab === "dashboard"}
          onClick={() => setActiveTab("dashboard")}
        >
          대시보드
        </button>
        <button
          type="button"
          role="tab"
          className={`tab-btn${activeTab === "search" ? " tab-btn--active" : ""}`}
          aria-selected={activeTab === "search"}
          onClick={() => setActiveTab("search")}
        >
          종목검색
        </button>
      </nav>

      {activeTab === "dashboard" ? <DashboardTab /> : <SearchTab />}
    </main>
  );
}
