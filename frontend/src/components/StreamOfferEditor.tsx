import { useState } from "react";
import {
  saveFlowOffers,
  type CatalogOption,
  type EditorFlow,
  type FlowOffer,
} from "../api/campaigns";
import { redistributeShares } from "../offerShares";

type Feedback = { tone: "success" | "error"; message: string };

type Props = {
  campaignId: number;
  flow: EditorFlow;
  catalog: CatalogOption[];
};

export function StreamOfferEditor({ campaignId, flow, catalog }: Props) {
  const [saved, setSaved] = useState(flow.offers);
  const [draft, setDraft] = useState<FlowOffer[] | null>(null);
  const [selection, setSelection] = useState("");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const offers = draft ?? saved;
  const offerNames = new Map(catalog.map(({ id, name }) => [id, name]));
  const available = catalog.filter(({ id }) => !offers.some(({ offer_id }) => offer_id === id));
  const selected = available.find(({ id }) => id === Number(selection));
  const active = offers.filter(({ state }) => state === "active");
  const total = active.reduce((sum, { share }) => sum + share, 0);

  function changeOffers(next: FlowOffer[]) {
    const balanced = redistributeShares(next);
    if (!balanced) {
      setFeedback({ tone: "error", message: "Открепите одну из долей, чтобы перераспределить трафик." });
      return false;
    }
    setDraft(balanced);
    setFeedback(null);
    return true;
  }

  function addOffer() {
    if (selected && changeOffers([...offers, { offer_id: selected.id, share: 0, state: "active", pinned: false }])) {
      setSelection("");
    }
  }

  function toggleOffer(offer: FlowOffer) {
    const state = offer.state === "removed" ? "active" : "removed";
    changeOffers(offers.map((item) => item.offer_id === offer.offer_id
      ? { ...item, state, share: 0, pinned: false }
      : item));
  }

  function togglePin(offer: FlowOffer) {
    const next = offers.map((item) => item.offer_id === offer.offer_id
      ? { ...item, pinned: !item.pinned }
      : item);
    if (draft) {
      setDraft(next);
      setFeedback(null);
    } else {
      void save(next, offer.pinned ? "Доля откреплена." : "Доля закреплена.");
    }
  }

  async function save(next: FlowOffer[], message: string) {
    if (saving) {
      return;
    }
    setSaving(true);
    setFeedback(null);
    try {
      const updated = await saveFlowOffers(campaignId, flow.id, saved, next);
      setSaved(updated.offers);
      setDraft(null);
      setFeedback({ tone: "success", message });
    } catch (error) {
      const errorMessage = error instanceof Error && !(error instanceof TypeError)
        ? error.message
        : "Связь с сервером прервалась. Проверьте состояние кампании.";
      setFeedback({ tone: "error", message: errorMessage });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="flow" aria-busy={saving}>
      <div className="flow-header">
        <h3>{flow.name}</h3>
        <p>Клики сегодня {flow.clicks_today === null ? "недоступны" : flow.clicks_today}</p>
      </div>
      {offers.length === 0 ? (
        <p className="status">В потоке пока нет офферов.</p>
      ) : (
        <div className="offer-table">
          <table>
            <thead>
              <tr><th scope="col">Оффер</th><th scope="col">Доля</th><th scope="col">Действия</th></tr>
            </thead>
            <tbody>
              {[...offers].sort((left, right) => right.share - left.share).map((offer) => {
                const name = offerNames.get(offer.offer_id) ?? `Оффер №${offer.offer_id}`;
                const removed = offer.state === "removed";
                return (
                  <tr key={offer.offer_id} className={removed ? "removed-offer" : undefined}>
                    <td>{name}{offer.state === "disabled" && <small>Выключен</small>}</td>
                    <td className="share">
                      <span>{offer.share}%</span>
                      {offer.state === "active" && (
                        <button
                          type="button"
                          className="pin"
                          aria-pressed={offer.pinned}
                          aria-label={`Закрепить долю оффера ${name}`}
                          disabled={saving}
                          onClick={() => togglePin(offer)}
                        >
                          {offer.pinned ? "Закреплена" : "Закрепить"}
                        </button>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        disabled={saving || (removed && !offerNames.has(offer.offer_id))}
                        aria-label={`${removed ? "Вернуть" : "Удалить из потока"} ${name}`}
                        onClick={() => toggleOffer(offer)}
                      >
                        {removed ? "Вернуть" : "Удалить"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {available.length > 0 && (
        <div className="campaign-lookup flow-add">
          <label className="field">
            <span>Добавить оффер</span>
            <input
              type="search"
              list={`offers-${flow.id}`}
              placeholder="Название или ID"
              value={selection}
              disabled={saving}
              onChange={(event) => setSelection(event.target.value)}
            />
            <datalist id={`offers-${flow.id}`}>
              {available.map(({ id, name }) => <option key={id} value={id} label={name} />)}
            </datalist>
          </label>
          <button type="button" disabled={!selected || saving} onClick={addOffer}>Добавить</button>
        </div>
      )}
      {draft && (
        <div className="flow-actions">
          <span>Активные доли {total}%</span>
          <button
            type="button"
            className="primary"
            disabled={saving || (active.length > 0 && total !== 100)}
            onClick={() => void save(draft, "Изменения отправлены в Keitaro.")}
          >
            {saving ? "Сохранение…" : "Отправить в Keitaro"}
          </button>
          <button type="button" disabled={saving} onClick={() => { setDraft(null); setFeedback(null); }}>
            Отмена
          </button>
        </div>
      )}
      {feedback && (
        <p className={feedback.tone} role={feedback.tone === "error" ? "alert" : "status"}>
          {feedback.message}
        </p>
      )}
    </section>
  );
}
