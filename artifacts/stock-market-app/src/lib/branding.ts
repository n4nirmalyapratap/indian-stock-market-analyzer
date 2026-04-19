export const BRAND_NAME = "Nifty Node";
export const BRAND_LOGO_PATH = "/niftynodes-logo-transparent.png";
export const BRAND_FALLBACK_ICON_PATH = "/favicon.svg";

function ensureFaviconLink(): HTMLLinkElement {
  const existing = document.querySelector("link[rel='icon']");
  if (existing instanceof HTMLLinkElement) return existing;

  const link = document.createElement("link");
  link.rel = "icon";
  document.head.appendChild(link);
  return link;
}

export function applyBrandFavicon() {
  if (typeof document === "undefined") return;

  const favicon = ensureFaviconLink();
  const probe = new Image();

  probe.onload = () => {
    favicon.href = BRAND_LOGO_PATH;
    favicon.type = "image/png";
  };

  probe.onerror = () => {
    favicon.href = BRAND_FALLBACK_ICON_PATH;
    favicon.type = "image/svg+xml";
  };

  probe.src = BRAND_LOGO_PATH;
}
