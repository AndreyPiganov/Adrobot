import { useState } from "react";
import { CampaignEditor } from "./components/CampaignEditor";
import { CampaignForm } from "./components/CampaignForm";

export function App() {
  const [view, setView] = useState<"create" | "editor">("create");

  return (
    <>
      <header className="header">
        <div className="container navigation">
          <span className="brand">Adrobot</span>
          <nav aria-label="Кампании">
            <button type="button" aria-pressed={view === "create"} onClick={() => setView("create")}>
              Создание
            </button>
            <button type="button" aria-pressed={view === "editor"} onClick={() => setView("editor")}>
              Офферы
            </button>
          </nav>
        </div>
      </header>
      <main className="container main">
        <h1>{view === "create" ? "Новая кампания" : "Офферы кампании"}</h1>
        {view === "create" ? <CampaignForm /> : <CampaignEditor />}
      </main>
    </>
  );
}
