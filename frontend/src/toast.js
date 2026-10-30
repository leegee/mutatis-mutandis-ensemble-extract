import { createSignal } from "solid-js";

export const [toast, setToast] = createSignal("");

let toastTimer;
export function showToast(msg) {
  setToast(msg);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => setToast(""), 1600);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
    } catch {
      /* ignore */
    }
    ta.remove();
  }
  showToast("Copied");
}

export function download(filename, text, mime) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
