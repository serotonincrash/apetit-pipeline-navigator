import { Link } from "@tanstack/react-router";
import { PersonaSwitcher } from "@/components/PersonaSwitcher";

const LINK = "px-3 py-3 text-muted-foreground hover:text-foreground";
const ACTIVE = { className: "px-3 py-3 font-medium text-foreground border-b-2 border-primary" };

export function TopBar() {
  return (
    <header className="flex items-center justify-between border-b px-6">
      <nav aria-label="Main" className="flex items-center">
        <span className="mr-4 font-semibold">Climate and nature navigator</span>
        <Link
          to="/runs"
          className={LINK}
          activeProps={ACTIVE}
          activeOptions={{ includeSearch: false }}
        >
          Runs
        </Link>
        <Link
          to="/review/data"
          search={{ status: "open" }}
          className={LINK}
          activeProps={ACTIVE}
          activeOptions={{ includeSearch: false }}
        >
          Data review
        </Link>
        <Link
          to="/risk"
          className={LINK}
          activeProps={ACTIVE}
          activeOptions={{ includeSearch: false }}
        >
          Risk view
        </Link>
      </nav>
      <PersonaSwitcher />
    </header>
  );
}
