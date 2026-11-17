import { ca } from "./ca";
import { en } from "./en";
import { es, type Messages } from "./es";
import { type Locale, locale } from "./locale";

export * from "./locale";
export type { Messages };

/** Every language's texts. They are small, so all three go in the bundle and no language waits for a download. */
export const MESSAGES: Record<Locale, Messages> = { es, ca, en };

/** The texts in the language of the page. */
export function messages(): Messages {
  return MESSAGES[locale()];
}
