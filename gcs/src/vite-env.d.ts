/// <reference types="vite/client" />

interface EoDesktop {
  platform: string;
}

interface Window {
  eoDesktop?: EoDesktop;
}
