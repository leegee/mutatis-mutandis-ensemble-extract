import { navigate } from "../router.js";

export function NotFound() {
  return (
    <>
      <header class="top">
        <h1>Passage Search</h1>
      </header>
      <main class="panes single" style="padding-top:48px;text-align:center">
        <p class="empty" style="font-size:16px">
          No page at <code>{location.hash || "#"}</code>
        </p>
        <p>
          <button class="btn primary" type="button" onClick={() => navigate("/")}>
            Back to search
          </button>
        </p>
      </main>
    </>
  );
}
