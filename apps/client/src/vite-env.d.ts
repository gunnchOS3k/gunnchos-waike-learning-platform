/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_HUB_URL?: string;
  readonly VITE_WAIKE_MOCK_HUB?: string;
  readonly VITE_PIXEL_PILOT?: string;
  readonly VITE_GUNNCHOS_PORTAL_URL?: string;
  readonly MODE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
