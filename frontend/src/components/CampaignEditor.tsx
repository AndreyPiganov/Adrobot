import { useState, type FormEvent } from "react";
import {
  fetchCampaignEditor,
  type CampaignEditorData,
} from "../api/campaigns";
import { StreamOfferEditor } from "./StreamOfferEditor";

type EditorState =
  | { status: "idle" | "loading" }
  | { status: "ready"; data: CampaignEditorData }
  | { status: "error"; message: string };

export function CampaignEditor() {
  const [editor, setEditor] = useState<EditorState>({ status: "idle" });
  const loading = editor.status === "loading";

  async function load(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) {
      return;
    }

    const id = Number(new FormData(event.currentTarget).get("campaign_id"));
    setEditor({ status: "loading" });
    try {
      const data = await fetchCampaignEditor(id);
      setEditor({ status: "ready", data });
    } catch (error) {
      const message = error instanceof Error && !(error instanceof TypeError)
        ? error.message
        : "Не удалось подключиться к серверу.";
      setEditor({ status: "error", message });
    }
  }

  return (
    <section className="panel" aria-label="Офферы кампании">
      <form className="campaign-lookup" onSubmit={load}>
        <label className="field">
          <span>ID кампании</span>
          <input name="campaign_id" type="number" min={1} step={1} required disabled={loading} />
        </label>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "Загрузка…" : "Загрузить из Keitaro"}
        </button>
      </form>
      {editor.status === "error" && <p className="error" role="alert">{editor.message}</p>}
      {editor.status === "ready" && <CampaignOffers data={editor.data} />}
    </section>
  );
}

function CampaignOffers({ data }: { data: CampaignEditorData }) {
  return (
    <div className="campaign-offers">
      <div className="campaign-title">
        <h2>{data.campaign.name}</h2>
        <a href={data.admin_url} target="_blank" rel="noreferrer">Открыть в Keitaro</a>
      </div>
      {data.flows.length === 0 && <p className="status">В этой кампании нет потоков с офферами.</p>}
      {data.flows.map((flow) => (
        <StreamOfferEditor key={flow.id} campaignId={data.campaign.id} flow={flow} catalog={data.offers} />
      ))}
    </div>
  );
}
