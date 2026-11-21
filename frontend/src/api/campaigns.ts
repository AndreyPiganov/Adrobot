export type CatalogOption = {
  id: number;
  name: string;
};

export type CampaignOptions = {
  domains: CatalogOption[];
  groups: CatalogOption[];
  traffic_sources: CatalogOption[];
};

export type CampaignInput = {
  name: string;
  country_code: string;
  offer_id: number;
  domain_id: number;
  group_id: number;
  traffic_source_id: number;
};

export type CreatedCampaign = {
  id: number;
  alias: string;
};

export type FlowOffer = {
  offer_id: number;
  share: number;
  state: "active" | "disabled" | "removed";
  pinned: boolean;
};

export type EditorFlow = {
  id: number;
  name: string;
  state: string;
  offers: FlowOffer[];
  clicks_today: number | null;
};

export type CampaignEditorData = {
  campaign: CatalogOption;
  admin_url: string;
  flows: EditorFlow[];
  offers: CatalogOption[];
};

async function fetchJson<T>(path: string, fallback: string, init: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : fallback);
  }

  return response.json();
}

export function fetchCampaignOptions(signal: AbortSignal): Promise<CampaignOptions> {
  return fetchJson("/api/campaigns/options", "Не удалось загрузить справочники.", { signal });
}

export function createCampaign(data: CampaignInput): Promise<CreatedCampaign> {
  return fetchJson("/api/campaigns", "Не удалось создать кампанию. Проверьте поля формы.", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function fetchCampaignEditor(id: number): Promise<CampaignEditorData> {
  return fetchJson(`/api/campaigns/${id}/editor`, "Не удалось загрузить кампанию.", {});
}

function activeLinks(offers: FlowOffer[]) {
  return offers
    .filter(({ state }) => state !== "removed")
    .map(({ offer_id, share, state }) => ({ offer_id, share, state }));
}

export function saveFlowOffers(
  campaignId: number,
  flowId: number,
  current: FlowOffer[],
  next: FlowOffer[],
): Promise<EditorFlow> {
  return fetchJson(
    `/api/campaigns/${campaignId}/streams/${flowId}/offers`,
    "Не удалось сохранить изменения. Проверьте доли офферов.",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_offers: activeLinks(current),
        expected_pinned_offer_ids: current.filter(({ pinned }) => pinned).map(({ offer_id }) => offer_id),
        offers: activeLinks(next),
        pinned_offer_ids: next
          .filter(({ pinned, state }) => pinned && state === "active")
          .map(({ offer_id }) => offer_id),
      }),
    },
  );
}
