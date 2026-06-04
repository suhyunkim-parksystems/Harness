import type { LucideIcon } from "lucide-react";

import type { MarketItem } from "../types/market";
import { MarketTable } from "./MarketTable";

interface MarketSectionProps {
  title: string;
  items: MarketItem[];
  icon: LucideIcon;
}

export function MarketSection({ title, items, icon: Icon }: MarketSectionProps) {
  return (
    <section className="market-section">
      <div className="section-heading">
        <Icon aria-hidden="true" size={18} />
        <h2>{title}</h2>
        <span className="section-count">{items.length}</span>
      </div>
      <MarketTable items={items} />
    </section>
  );
}
