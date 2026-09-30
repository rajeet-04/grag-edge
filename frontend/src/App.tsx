import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { BrandMark } from "./components/Icons";
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
  const { pathname } = useLocation();
  return (
    <div className="shell">
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to main content</a>
      <nav className="nav" aria-label="Primary">
        <h1><BrandMark />GRAG Edge</h1>
        {DESTINATIONS.map((d) => (
          <NavLink key={d.to} to={d.to} end={d.end}>{d.label}</NavLink>
        ))}
      </nav>
      <main id="main" tabIndex={-1}>
        <span className="route-bar" key={"bar" + pathname} aria-hidden="true" />
        <div className="route" key={pathname}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/search" element={<Search />} />
          <Route path="/memory" element={<Memory />} />
          <Route path="/sync" element={<Sync />} />
          <Route path="/conflicts" element={<Conflicts />} />
        </Routes>
        </div>
      </main>
    </div>
  );
}
