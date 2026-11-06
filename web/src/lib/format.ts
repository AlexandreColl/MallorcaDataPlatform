// Number and date formats in Spanish (decimal comma, thousands with a dot).

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MONTHS_LONG = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

export function number(value: number, digits = 0): string {
  return value.toLocaleString("es-ES", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** 2.596.458 -> "2,6 M"; 619,5 -> "620". */
export function compact(value: number): string {
  if (Math.abs(value) >= 1e6) return `${number(value / 1e6, 1)} M`;
  if (Math.abs(value) >= 1e4) return `${number(value / 1e3, 0)} mil`;
  return number(value, value < 100 ? 1 : 0);
}

/** A signed value with an explicit plus: "+2,1", "−11,5". */
export function signed(value: number, digits = 1): string {
  const text = number(Math.abs(value), digits);
  if (value > 0) return `+${text}`;
  if (value < 0) return `−${text}`;
  return text;
}

/** "2026-08-01" -> "agosto de 2026". */
export function monthName(isoMonth: string): string {
  const [year, month] = isoMonth.split("-").map(Number);
  return `${MONTHS_LONG[(month ?? 1) - 1]} de ${year}`;
}

/** "2026-08-01" -> "ago 26". */
export function monthShort(isoMonth: string): string {
  const [year, month] = isoMonth.split("-").map(Number);
  return `${MONTHS[(month ?? 1) - 1]} ${String(year).slice(2)}`;
}

/** "2026-11-04" -> "4 nov". */
export function dayShort(isoDay: string): string {
  const [, month, day] = isoDay.slice(0, 10).split("-").map(Number);
  return `${day} ${MONTHS[(month ?? 1) - 1]}`;
}

/** "2026-11-04" -> "4 de noviembre de 2026". */
export function dayName(isoDay: string): string {
  const [year, month, day] = isoDay.slice(0, 10).split("-").map(Number);
  return `${day} de ${MONTHS_LONG[(month ?? 1) - 1]} de ${year}`;
}

/** Age of a value in words: "hace 3 h", "hace 5 días". */
export function age(hours: number): string {
  if (hours < 1) return "hace menos de 1 h";
  if (hours < 48) return `hace ${Math.round(hours)} h`;
  const days = Math.round(hours / 24);
  if (days < 60) return `hace ${days} días`;
  const months = Math.round(days / 30);
  if (months < 24) return `hace ${months} meses`;
  return `hace ${Math.round(days / 365)} años`;
}
