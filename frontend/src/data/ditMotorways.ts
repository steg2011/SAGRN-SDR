// DIT-classified motorways for South Australia.
//
// Source: the same data.sa.gov.au 'State Maintained Roads' dataset (DIT) that backs
// ditRoads.ts. Filtering that dataset to road_type MOTORWAY / FREEWAY / EXPRESSWAY
// yields exactly five roads:
//
//   FREEWAY     South Eastern Freeway    (M1)
//   MOTORWAY    North South Motorway     (M2 - includes Northern Connector,
//                                         South Road Superway, Torrens to Torrens)
//   EXPRESSWAY  Southern Expressway      (M2)
//   EXPRESSWAY  Northern Expressway      (M2 - dual-named Max Fatchen Expressway)
//   EXPRESSWAY  Port River Expressway    (A9)
//
// Everything else DIT maintains is a HIGHWAY or ROAD (Port Wakefield Hwy, Salisbury
// Hwy and Gawler Bypass included), so they are deliberately not motorways here.
//
// Matching is name-based rather than route-number based so it also catches the forms
// Waze actually reports: "M1 - South Eastern Fwy", "M1- South Eastern Fwy",
// "M2 - North-South Mwy", "to M2 - Southern Exp to City", plus the DIT dataset's own
// on/off-ramp names ("SOUTHERN EXPRESSWAY OFF RAMP TO TONSLEY BLVD").
const MOTORWAY_PATTERNS: RegExp[] = [
  /\bSOUTH[ -]?EASTERN (FREEWAY|FWY)\b/,
  /\bNORTH[ -]?SOUTH (MOTORWAY|MWY)\b/,
  /\bSOUTHERN (EXPRESSWAY|EXPWY|EXP)\b/,
  /\bNORTHERN (EXPRESSWAY|EXPWY|EXP)\b/,
  /\bMAX FATCHEN (EXPRESSWAY|EXPWY|EXP)\b/,
  /\bPORT RIVER (EXPRESSWAY|EXPWY|EXP)\b/,
  // North-South Motorway sections Waze still signs as South Rd. The M prefix is
  // required: SA only uses 'M' on grade-separated roads, so the at-grade arterial
  // ("A2 - South Rd") is left out.
  /\bM\d+ ?- ?SOUTH RD\b/,
  // DIT names the Port Wakefield Rd interchange ramps off the plain word "MOTORWAY".
  /\bMOTORWAY (ON|OFF) RAMP\b/,
];

export function isDitMotorway(address: string | null): boolean {
  if (!address) return false;
  const name = address.trim().toUpperCase().replace(/\s+/g, ' ');
  return MOTORWAY_PATTERNS.some((pattern) => pattern.test(name));
}
