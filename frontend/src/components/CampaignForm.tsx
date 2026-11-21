import { useEffect, useState, type FormEvent } from "react";
import {
  createCampaign,
  fetchCampaignOptions,
  type CampaignOptions,
  type CatalogOption,
  type CreatedCampaign,
} from "../api/campaigns";

type CatalogState =
  | { status: "loading" }
  | { status: "ready"; options: CampaignOptions }
  | { status: "error"; message: string };

const fields = [
  { name: "domain_id", catalog: "domains", label: "Домен" },
  { name: "group_id", catalog: "groups", label: "Группа кампаний" },
  { name: "traffic_source_id", catalog: "traffic_sources", label: "Источник трафика" },
] as const;

type Submission =
  | { status: "idle" | "saving" }
  | { status: "created"; campaign: CreatedCampaign }
  | { status: "error"; message: string };

function CatalogSelect({ name, label, options }: {
  name: string;
  label: string;
  options?: CatalogOption[];
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <span className="select">
        <select name={name} defaultValue="" disabled={!options?.length} required>
          <option value="" disabled>
            {options?.length === 0 ? "Нет доступных вариантов" : "Выберите из списка"}
          </option>
          {options?.map(({ id, name }) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>
      </span>
    </label>
  );
}

export function CampaignForm() {
  const [attempt, setAttempt] = useState(0);
  const [catalog, setCatalog] = useState<CatalogState>({ status: "loading" });
  const [submission, setSubmission] = useState<Submission>({ status: "idle" });
  const options = catalog.status === "ready" ? catalog.options : undefined;
  const canSubmit = options !== undefined
    && fields.every(({ catalog }) => options[catalog].length > 0);
  const saving = submission.status === "saving";

  useEffect(() => {
    const controller = new AbortController();

    fetchCampaignOptions(controller.signal)
      .then((options) => setCatalog({ status: "ready", options }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          const message = error instanceof Error ? error.message : "Не удалось загрузить справочники.";
          setCatalog({ status: "error", message });
        }
      });

    return () => controller.abort();
  }, [attempt]);

  function retry() {
    setCatalog({ status: "loading" });
    setAttempt((value) => value + 1);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || saving) {
      return;
    }

    const form = event.currentTarget;
    const values = new FormData(form);
    setSubmission({ status: "saving" });
    try {
      const campaign = await createCampaign({
        name: String(values.get("name")).trim(),
        country_code: String(values.get("country_code")).toUpperCase(),
        offer_id: Number(values.get("offer_id")),
        domain_id: Number(values.get("domain_id")),
        group_id: Number(values.get("group_id")),
        traffic_source_id: Number(values.get("traffic_source_id")),
      });
      form.reset();
      setSubmission({ status: "created", campaign });
    } catch (error) {
      const message = error instanceof Error && !(error instanceof TypeError)
        ? error.message
        : "Связь с сервером прервалась. Перед повтором проверьте кампанию в Keitaro.";
      setSubmission({ status: "error", message });
    }
  }

  return (
    <form className="panel" onSubmit={submit} aria-busy={saving}>
      <fieldset disabled={saving}>
        <legend>Параметры кампании</legend>
        <div className="fields">
          <label className="field">
            <span>Название</span>
            <input name="name" placeholder="Название кампании" required maxLength={255} />
          </label>
          <label className="field">
            <span>Код страны</span>
            <input
              name="country_code"
              className="country-code"
              placeholder="Например, DE"
              autoCapitalize="characters"
              spellCheck={false}
              pattern="[A-Za-z]{2}"
              maxLength={2}
              required
            />
          </label>
          <label className="field">
            <span>ID оффера</span>
            <input name="offer_id" type="number" min={1} step={1} placeholder="Например, 42" required />
          </label>
        </div>
      </fieldset>
      <fieldset disabled={saving}>
        <legend>Настройки Keitaro</legend>
        <div className="fields">
          {fields.map(({ name, catalog, label }) => (
            <CatalogSelect key={name} name={name} label={label} options={options?.[catalog]} />
          ))}
        </div>
      </fieldset>
      {catalog.status === "loading" && <p className="status" role="status">Загрузка справочников…</p>}
      {catalog.status === "error" && (
        <div className="error">
          <p role="alert">{catalog.message}</p>
          <button type="button" onClick={retry}>Повторить</button>
        </div>
      )}
      <div className="form-actions">
        <button type="submit" className="primary" disabled={!canSubmit || saving}>
          {saving ? "Создаём кампанию…" : "Создать кампанию"}
        </button>
        {submission.status === "created" && (
          <p className="success" role="status">
            Кампания №{submission.campaign.id} создана. Алиас {submission.campaign.alias}.
          </p>
        )}
        {submission.status === "error" && <p className="error" role="alert">{submission.message}</p>}
      </div>
    </form>
  );
}
