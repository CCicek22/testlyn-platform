/**
 * Minimal type stub for @scalar/api-reference-react.
 * Replace with the package's own types once `pnpm install` has been run.
 */
declare module "@scalar/api-reference-react" {
  import type { FC } from "react";

  export interface ApiReferenceConfiguration {
    spec?: {
      url?: string;
      content?: string;
    };
    theme?: string;
    darkMode?: boolean;
    layout?: "sidebar" | "classic";
    hideModels?: boolean;
    hideDownloadButton?: boolean;
    defaultOpenAllTags?: boolean;
    customCss?: string;
    [key: string]: unknown;
  }

  export interface ApiReferenceReactProps {
    configuration: ApiReferenceConfiguration;
  }

  export const ApiReferenceReact: FC<ApiReferenceReactProps>;
}
