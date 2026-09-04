/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_HUB_URL?: string;
  readonly VITE_WAIKE_MOCK_HUB?: string;
  readonly MODE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
