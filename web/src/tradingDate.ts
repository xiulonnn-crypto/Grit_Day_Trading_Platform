export const REVIEW_TIME_ZONE = "America/New_York";

export function getDefaultReviewDate(now = new Date()) {
  return formatDateInTimeZone(now, REVIEW_TIME_ZONE);
}

export function formatDateInTimeZone(value: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "2-digit",
    timeZone,
    year: "numeric"
  }).formatToParts(value);
  const year = findDatePart(parts, "year");
  const month = findDatePart(parts, "month");
  const day = findDatePart(parts, "day");
  return `${year}-${month}-${day}`;
}

function findDatePart(parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes) {
  const value = parts.find((part) => part.type === type)?.value;
  if (!value) {
    throw new Error(`Missing ${type} in formatted review date`);
  }
  return value;
}
