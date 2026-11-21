import type { FlowOffer } from "./api/campaigns";

export function redistributeShares(offers: FlowOffer[]): FlowOffer[] | null {
  const active = offers.filter(({ state }) => state === "active");
  if (active.length === 0) {
    return offers;
  }

  const fixed = active
    .filter(({ pinned }) => pinned)
    .reduce((total, { share }) => total + share, 0);
  const unpinned = active.filter(({ pinned }) => !pinned);
  const remaining = 100 - fixed;
  if (remaining < 0 || (unpinned.length === 0 && remaining !== 0)) {
    return null;
  }
  if (unpinned.length === 0) {
    return offers;
  }

  const evenShare = Math.floor(remaining / unpinned.length);
  const remainderStartsAt = unpinned.length - (remaining % unpinned.length);
  const shares = new Map(unpinned.map(({ offer_id }, index) => [
    offer_id,
    evenShare + Number(index >= remainderStartsAt),
  ]));
  return offers.map((offer) => ({ ...offer, share: shares.get(offer.offer_id) ?? offer.share }));
}
