import { type KeyboardEvent, useState } from "react";

import type { SearchCandidate } from "../types/market";

interface AutocompleteInputProps {
  value: string;
  onChange: (v: string) => void;
  onSelect: (candidate: SearchCandidate) => void;
  candidates: SearchCandidate[];
  isLoading: boolean;
  placeholder?: string;
}

export function AutocompleteInput({
  value,
  onChange,
  onSelect,
  candidates,
  isLoading,
  placeholder = "종목명 또는 티커 입력",
}: AutocompleteInputProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const showDropdown = isOpen && candidates.length > 0;

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!showDropdown) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, candidates.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && highlightedIndex >= 0) {
      e.preventDefault();
      onSelect(candidates[highlightedIndex]);
      setIsOpen(false);
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  }

  function handleSelect(candidate: SearchCandidate) {
    onSelect(candidate);
    setIsOpen(false);
    setHighlightedIndex(-1);
  }

  return (
    <div className="autocomplete-wrapper">
      <input
        type="text"
        role="combobox"
        aria-expanded={showDropdown}
        aria-autocomplete="list"
        aria-haspopup="listbox"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setIsOpen(true);
          setHighlightedIndex(-1);
        }}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setTimeout(() => setIsOpen(false), 150)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className="autocomplete-input"
      />
      {isLoading && (
        <div className="autocomplete-spinner" aria-label="검색 중">
          <span className="autocomplete-spinner-dot" />
        </div>
      )}
      {showDropdown && (
        <ul className="autocomplete-dropdown" role="listbox">
          {candidates.map((c, i) => (
            <li
              key={c.id}
              role="option"
              aria-selected={i === highlightedIndex}
              className={`autocomplete-item${i === highlightedIndex ? " autocomplete-item--highlighted" : ""}`}
              onMouseDown={() => handleSelect(c)}
            >
              <span className="autocomplete-symbol">{c.symbol}</span>
              <span className="autocomplete-name">{c.name}</span>
              <span className="autocomplete-exchange">
                {c.exchange} · {c.assetType}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
