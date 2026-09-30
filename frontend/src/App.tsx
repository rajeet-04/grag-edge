import { NavLink, Route, Routes } from "react-router-dom";
import Conflicts from "./pages/Conflicts";
import Memory from "./pages/Memory";
import Overview from "./pages/Overview";
import Search from "./pages/Search";
import Sync from "./pages/Sync";

const DESTINATIONS = [
  { to: "/", label: "Overview", end: true },
  { to: "/search", label: "Search" },
  { to: "/memory", label: "Memory" },
  { to: "/sync", label: "Sync" },
  { to: "/conflicts", label: "Conflicts" },
];

export default function App() {
  return (
    <div className="shell">
      <nav className="nav" aria-label="Primary">
        <h1>GRAG Edge</h1>
        {DESTINATIONS.map((d) => (
          <NavLink key={d.to} to={d.to} end={d.end}>{d.label}</NavLink>
        ))}
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/search" element={<Search />} />
          <Route path="/memory" element={<Memory />} />
          <Route path="/sync" element={<Sync />} />
          <Route path="/conflicts" element={<Conflicts />} />
        </Routes>
      </main>
    </div>
  );
}
