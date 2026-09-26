import { useMemo, useState } from "react";
import { authorizeSearchHits, matchQuery } from "../../lib/product/searchAuthz";
import type { SearchHit } from "../../lib/product/types";

type Props = {
  catalog: Array<Omit<SearchHit, "authorized">>;
  authorizedSectionIds: string[];
  role: string;
  onOpen: (hit: SearchHit) => void;
};

export function SearchPanel({ catalog, authorizedSectionIds, role, onOpen }: Props) {
  const [q, setQ] = useState("");
  const results = useMemo(
    () => authorizeSearchHits(matchQuery(q, catalog), authorizedSectionIds, role),
    [q, catalog, authorizedSectionIds, role],
  );
  return (
    <section className="panel" data-testid="learner-search">
      <h2>Search</h2>
      <label className="field-label" htmlFor="learner-search-q">
        Search your courses
      </label>
      <input
        id="learner-search-q"
        data-testid="learner-search-q"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Lessons, assignments, labs"
      />
      <ul data-testid="search-results">
        {results.map((hit) => (
          <li key={`${hit.kind}-${hit.id}`}>
            <button type="button" className="ghost" onClick={() => onOpen(hit)}>
              {hit.title}
              <span className="muted"> · {hit.kind}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
