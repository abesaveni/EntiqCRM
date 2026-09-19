// The UI kit is consumed as source by Vite apps; `import.meta.env` is provided by the host bundler.
// Declared here so the package typechecks on its own without depending on vite.
interface ImportMetaEnv {
  readonly DEV: boolean;
  readonly PROD: boolean;
  readonly MODE: string;
  readonly [key: string]: string | boolean | undefined;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
