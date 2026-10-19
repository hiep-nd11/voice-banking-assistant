const aliases = {
  home: "house",
  user: "user-round",
  transfer: "arrow-left-right",
  qr: "scan-line",
  phone: "smartphone",
  save: "piggy-bank",
  plane: "plane",
  loan: "landmark",
  fund: "chart-no-axes-combined",
  card: "credit-card",
  bill: "receipt",
  history: "history",
  more: "layout-grid",
  back: "arrow-left",
  bell: "bell",
  eye: "eye",
  mic: "mic",
  check: "check",
  close: "x",
  copy: "copy",
  shield: "shield-check",
  search: "search",
  wallet: "wallet",
  gift: "gift",
  book: "book-open",
  settings: "settings",
  chev: "chevron-right",
  upload: "upload",
  camera: "camera",
  spark: "sparkles",
  send: "send",
  info: "info",
};

const paths = {
  house: (
    <>
      <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z" />
    </>
  ),
  "arrow-left-right": (
    <>
      <path d="M8 3 4 7l4 4M4 7h16M16 21l4-4-4-4m4 4H4" />
    </>
  ),
  "scan-line": (
    <>
      <path d="M4 8V5a1 1 0 0 1 1-1h3m8 0h3a1 1 0 0 1 1 1v3M4 16v3a1 1 0 0 0 1 1h3m8 0h3a1 1 0 0 0 1-1v-3M4 12h16" />
    </>
  ),
  smartphone: (
    <>
      <rect x="6" y="2" width="12" height="20" rx="2" />
      <path d="M11 18h2" />
    </>
  ),
  "piggy-bank": (
    <>
      <path d="M19 9h2v5h-2a7 7 0 0 1-3 4v3h-3v-2H9v2H6v-4a7 7 0 0 1-2-5H2v-3h3a7 7 0 0 1 7-5h3l2-2v4a7 7 0 0 1 2 3Z" />
      <path d="M15 10h.01" />
    </>
  ),
  plane: (
    <>
      <path d="M22 2 9.5 14.5m12.5-12.5-7 19-4-8-8-4z" />
    </>
  ),
  landmark: (
    <>
      <path d="m3 10 9-7 9 7M4 10h16M6 10v9m4-9v9m4-9v9m4-9v9M3 21h18" />
    </>
  ),
  "chart-no-axes-combined": (
    <>
      <path d="M3 17 9 11l4 4 8-9M3 3v18h18" />
    </>
  ),
  "credit-card": (
    <>
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M2 10h20" />
    </>
  ),
  receipt: (
    <>
      <path d="M4 3h16v18l-4-2-4 2-4-2-4 2V3Zm4 5h8M8 12h8" />
    </>
  ),
  history: (
    <>
      <path d="M3 12a9 9 0 1 0 3-7M3 3v6h6m3-2v5l4 2" />
    </>
  ),
  "layout-grid": (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  "arrow-left": (
    <>
      <path d="m12 19-7-7 7-7M5 12h14" />
    </>
  ),
  bell: (
    <>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="2" width="6" height="13" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 17v5m-4 0h8" />
    </>
  ),
  check: (
    <>
      <path d="m4 12 5 5L20 6" />
    </>
  ),
  x: (
    <>
      <path d="M18 6 6 18M6 6l12 12" />
    </>
  ),
  copy: (
    <>
      <rect x="8" y="8" width="13" height="13" rx="2" />
      <path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" />
    </>
  ),
  "user-round": (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  "shield-check": (
    <>
      <path d="m12 22 7-4V6l-7-4-7 4v12l7 4Zm-4-10 3 3 5-6" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  wallet: (
    <>
      <rect x="2" y="5" width="20" height="16" rx="2" />
      <path d="M2 9h20m-4 6h.01" />
    </>
  ),
  gift: (
    <>
      <rect x="3" y="9" width="18" height="12" rx="1" />
      <path d="M12 9v12M2 9h20v-4H2Zm10-4c-7 0-7-6-3-6 3 0 3 6 3 6s0-6 3-6c4 0 4 6-3 6" />
    </>
  ),
  "book-open": (
    <>
      <path d="M12 7c-3-3-7-3-10-2v14c3-1 7-1 10 2 3-3 7-3 10-2V5c-3-1-7-1-10 2Zm0 0v14" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" />
    </>
  ),
  "chevron-right": (
    <>
      <path d="m9 18 6-6-6-6" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V3m-5 5 5-5 5 5M3 17v4h18v-4" />
    </>
  ),
  camera: (
    <>
      <path d="M3 7h4l2-3h6l2 3h4v13H3z" />
      <circle cx="12" cy="13" r="4" />
    </>
  ),
  sparkles: (
    <>
      <path d="m12 3 2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6ZM19 18l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2Z" />
    </>
  ),
  send: (
    <>
      <path d="m22 2-7 20-4-9-9-4 20-7ZM11 13 22 2" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 11v6m0-10h.01" />
    </>
  ),
};
export default function Icon({ name, size = 21 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[aliases[name] || name] || paths.info}
    </svg>
  );
}
